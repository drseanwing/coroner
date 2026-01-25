"""
Patient Safety Monitor - Admin API Routes

RESTful API endpoints for programmatic access to the admin functionality.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from config.logging import get_logger
from config.settings import get_settings
from database.connection import get_session
from database.models import PostStatus, FindingStatus
from database.repository import (
    PostRepository,
    FindingRepository,
    SourceRepository,
    AnalysisRepository,
)
from admin.main import get_current_user, get_current_user_jwt
from admin.auth import (
    Token,
    TokenData,
    User,
    create_access_token,
    verify_token,
    verify_password,
    get_token_expiration,
)


logger = get_logger(__name__)
router = APIRouter(tags=["api"])


# =============================================================================
# Response Models
# =============================================================================

class SourceResponse(BaseModel):
    """Source data response model."""
    id: UUID
    code: str
    name: str
    country: str
    region: Optional[str]
    base_url: str
    is_active: bool
    last_scraped_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class FindingSummary(BaseModel):
    """Finding summary response model."""
    id: UUID
    external_id: str
    title: str
    source_url: str
    date_of_finding: Optional[datetime]
    status: str
    is_healthcare: Optional[bool]
    healthcare_confidence: Optional[float]
    
    class Config:
        from_attributes = True


class PostSummary(BaseModel):
    """Post summary response model."""
    id: UUID
    slug: str
    title: str
    excerpt: Optional[str]
    status: str
    tags: Optional[list[str]]
    published_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class PostDetail(BaseModel):
    """Detailed post response model."""
    id: UUID
    slug: str
    title: str
    content_markdown: str
    content_html: Optional[str]
    excerpt: Optional[str]
    status: str
    tags: Optional[list[str]]
    reviewer_notes: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PostUpdate(BaseModel):
    """Post update request model."""
    title: Optional[str] = None
    content_markdown: Optional[str] = None
    tags: Optional[list[str]] = None


class ApprovalRequest(BaseModel):
    """Post approval request model."""
    publish_now: bool = False
    notes: Optional[str] = None


class RejectionRequest(BaseModel):
    """Post rejection request model."""
    reason: str = Field(..., min_length=1)


class StatsResponse(BaseModel):
    """Dashboard statistics response model."""
    posts_pending: int
    posts_published: int
    findings_total: int
    findings_healthcare: int
    sources_active: int
    total_cost_usd: float


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: list
    total: int
    page: int
    per_page: int
    total_pages: int


class UserInfo(BaseModel):
    """Current user information."""
    username: str
    role: str


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.post("/auth/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    OAuth2 login endpoint - exchange username/password for JWT token.

    Args:
        form_data: OAuth2 password grant form data

    Returns:
        Token with access_token, token_type, and expiration

    Raises:
        HTTPException: If credentials are invalid
    """
    settings = get_settings()

    # Validate username (constant-time comparison)
    import secrets
    correct_username = secrets.compare_digest(
        form_data.username.encode("utf8"),
        settings.admin_username.encode("utf8"),
    )

    # Validate password
    correct_password = verify_password(
        form_data.password,
        settings.admin_password_hash,
    )

    if not (correct_username and correct_password):
        logger.warning(
            "Failed JWT login attempt",
            extra={"username": form_data.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        data={
            "sub": form_data.username,
            "role": "admin",
        }
    )

    expires_at = get_token_expiration()

    logger.info(
        "JWT login successful",
        extra={
            "username": form_data.username,
            "expires_at": expires_at.isoformat(),
        },
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_at=expires_at,
    )


@router.post("/auth/refresh", response_model=Token)
async def refresh_token(
    user: str = Depends(get_current_user_jwt),
):
    """
    Refresh an existing JWT token.

    Args:
        user: Current authenticated user (from JWT)

    Returns:
        New token with extended expiration
    """
    # Create new token
    access_token = create_access_token(
        data={
            "sub": user,
            "role": "admin",
        }
    )

    expires_at = get_token_expiration()

    logger.info(
        "JWT token refreshed",
        extra={
            "username": user,
            "expires_at": expires_at.isoformat(),
        },
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_at=expires_at,
    )


@router.post("/auth/logout")
async def logout(
    user: str = Depends(get_current_user_jwt),
):
    """
    Logout endpoint (for JWT, this is mostly informational).

    Since JWT is stateless, actual token invalidation happens client-side
    by deleting the token. This endpoint logs the logout event.

    Args:
        user: Current authenticated user

    Returns:
        Success message
    """
    logger.info(
        "User logged out",
        extra={"username": user},
    )

    return {
        "status": "success",
        "message": "Logged out successfully",
    }


@router.get("/auth/me", response_model=UserInfo)
async def get_current_user_info(
    user: str = Depends(get_current_user_jwt),
):
    """
    Get current user information.

    Args:
        user: Current authenticated user

    Returns:
        User information including username and role
    """
    return UserInfo(
        username=user,
        role="admin",
    )


# =============================================================================
# Stats Endpoint
# =============================================================================

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    user: str = Depends(get_current_user),
):
    """
    Get dashboard statistics.
    """
    with get_session() as session:
        post_repo = PostRepository(session)
        finding_repo = FindingRepository(session)
        source_repo = SourceRepository(session)
        analysis_repo = AnalysisRepository(session)
        
        return StatsResponse(
            posts_pending=post_repo.count_by_status(PostStatus.PENDING_REVIEW),
            posts_published=post_repo.count_by_status(PostStatus.PUBLISHED),
            findings_total=finding_repo.count(),
            findings_healthcare=len(finding_repo.get_healthcare_findings()),
            sources_active=len(source_repo.get_active_sources()),
            total_cost_usd=float(analysis_repo.get_total_cost() or 0),
        )


# =============================================================================
# Sources Endpoints
# =============================================================================

@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    user: str = Depends(get_current_user),
    active_only: bool = Query(False),
):
    """
    List all configured data sources.
    """
    with get_session() as session:
        repo = SourceRepository(session)
        
        if active_only:
            sources = repo.get_active_sources()
        else:
            sources = repo.get_all()
        
        return [SourceResponse.model_validate(s) for s in sources]


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Get a single source by ID.
    """
    with get_session() as session:
        repo = SourceRepository(session)
        source = repo.get_by_id(source_id)
        
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        return SourceResponse.model_validate(source)


@router.post("/sources/{source_id}/trigger")
async def trigger_source_scrape(
    source_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Trigger a manual scrape for a source.
    """
    with get_session() as session:
        repo = SourceRepository(session)
        source = repo.get_by_code(str(source_id))
        
        # Note: In production, this would queue a job to the scheduler
        logger.info(
            "Manual scrape triggered via API",
            extra={
                "source_id": str(source_id),
                "triggered_by": user,
            },
        )
        
        return {
            "status": "queued",
            "message": f"Scrape job queued for source {source_id}",
        }


# =============================================================================
# Findings Endpoints
# =============================================================================

@router.get("/findings")
async def list_findings(
    user: str = Depends(get_current_user),
    status: Optional[str] = Query(None),
    source_id: Optional[UUID] = Query(None),
    healthcare_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    List findings with optional filtering.
    """
    with get_session() as session:
        repo = FindingRepository(session)
        
        offset = (page - 1) * per_page
        
        filters = {}
        if status:
            try:
                filters["status"] = FindingStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if source_id:
            filters["source_id"] = source_id
        
        if healthcare_only:
            filters["is_healthcare"] = True
        
        findings = repo.get_filtered(limit=per_page, offset=offset, **filters)
        total = repo.count_filtered(**filters)
        
        return {
            "items": [FindingSummary.model_validate(f) for f in findings],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }


@router.get("/findings/{finding_id}", response_model=FindingSummary)
async def get_finding(
    finding_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Get a single finding by ID.
    """
    with get_session() as session:
        repo = FindingRepository(session)
        finding = repo.get_by_id(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")
        
        return FindingSummary.model_validate(finding)


# =============================================================================
# Posts Endpoints
# =============================================================================

@router.get("/posts")
async def list_posts(
    user: str = Depends(get_current_user),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    List posts with optional filtering.
    """
    with get_session() as session:
        repo = PostRepository(session)
        
        offset = (page - 1) * per_page
        
        if status:
            try:
                post_status = PostStatus(status)
                posts = repo.get_by_status(post_status, limit=per_page, offset=offset)
                total = repo.count_by_status(post_status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        else:
            posts = repo.get_all(limit=per_page, offset=offset)
            total = repo.count()
        
        return {
            "items": [PostSummary.model_validate(p) for p in posts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }


@router.get("/posts/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Get a single post by ID.
    """
    with get_session() as session:
        repo = PostRepository(session)
        post = repo.get_by_id(post_id)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        return PostDetail.model_validate(post)


@router.patch("/posts/{post_id}", response_model=PostDetail)
async def update_post(
    post_id: UUID,
    update: PostUpdate,
    user: str = Depends(get_current_user),
):
    """
    Update a post's content.
    """
    with get_session() as session:
        repo = PostRepository(session)
        
        post = repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Apply updates
        update_data = update.model_dump(exclude_unset=True)
        if update_data:
            repo.update(post_id, **update_data)
            session.commit()
            session.refresh(post)
        
        logger.info(
            "Post updated via API",
            extra={
                "post_id": str(post_id),
                "updated_by": user,
                "fields": list(update_data.keys()),
            },
        )
        
        return PostDetail.model_validate(post)


@router.post("/posts/{post_id}/approve", response_model=PostDetail)
async def approve_post(
    post_id: UUID,
    approval: ApprovalRequest,
    user: str = Depends(get_current_user),
):
    """
    Approve a post for publication.
    """
    with get_session() as session:
        repo = PostRepository(session)
        
        post = repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        repo.approve(
            post_id,
            reviewed_by=user,
            notes=approval.notes,
            publish_now=approval.publish_now,
        )
        session.commit()
        session.refresh(post)
        
        logger.info(
            "Post approved via API",
            extra={
                "post_id": str(post_id),
                "publish_now": approval.publish_now,
                "reviewed_by": user,
            },
        )
        
        return PostDetail.model_validate(post)


@router.post("/posts/{post_id}/reject", response_model=PostDetail)
async def reject_post(
    post_id: UUID,
    rejection: RejectionRequest,
    user: str = Depends(get_current_user),
):
    """
    Reject a post.
    """
    with get_session() as session:
        repo = PostRepository(session)
        
        post = repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        repo.reject(
            post_id,
            reviewed_by=user,
            reason=rejection.reason,
        )
        session.commit()
        session.refresh(post)
        
        logger.info(
            "Post rejected via API",
            extra={
                "post_id": str(post_id),
                "reason": rejection.reason[:100],
                "reviewed_by": user,
            },
        )
        
        return PostDetail.model_validate(post)
