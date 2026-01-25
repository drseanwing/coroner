"""
Patient Safety Monitor - Admin Dashboard Routes

Page routes for the admin dashboard using Jinja2 templates and HTMX.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from config.settings import get_settings
from config.logging import get_logger
from database.connection import get_session
from database.models import Post, Finding, Source, Analysis, PostStatus, FindingStatus
from database.repository import (
    PostRepository,
    FindingRepository,
    SourceRepository,
    AnalysisRepository,
)
from admin.main import get_current_user


logger = get_logger(__name__)
router = APIRouter()


# =============================================================================
# Dashboard
# =============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: str = Depends(get_current_user),
):
    """
    Main dashboard showing overview statistics.
    """
    templates = request.app.state.templates
    
    with get_session() as session:
        post_repo = PostRepository(session)
        finding_repo = FindingRepository(session)
        source_repo = SourceRepository(session)
        
        # Gather statistics
        stats = {
            "pending_review": len(post_repo.get_by_status(PostStatus.PENDING_REVIEW)),
            "published_posts": len(post_repo.get_by_status(PostStatus.PUBLISHED)),
            "total_findings": finding_repo.count(),
            "healthcare_findings": len(finding_repo.get_healthcare_findings()),
            "active_sources": len(source_repo.get_active_sources()),
            "new_findings": len(finding_repo.get_by_status(FindingStatus.NEW)),
        }
        
        # Recent activity
        recent_posts = post_repo.get_recent(limit=5)
        recent_findings = finding_repo.get_recent(limit=5)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_posts": recent_posts,
            "recent_findings": recent_findings,
            "page_title": "Dashboard",
        },
    )


# =============================================================================
# Review Queue
# =============================================================================

@router.get("/review", response_class=HTMLResponse)
async def review_queue(
    request: Request,
    user: str = Depends(get_current_user),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    """
    Review queue showing posts awaiting review.
    """
    templates = request.app.state.templates
    
    per_page = 20
    offset = (page - 1) * per_page
    
    with get_session() as session:
        post_repo = PostRepository(session)
        
        # Filter by status if provided
        if status:
            try:
                post_status = PostStatus(status)
                posts = post_repo.get_by_status(post_status, limit=per_page, offset=offset)
                total = post_repo.count_by_status(post_status)
            except ValueError:
                posts = post_repo.get_pending_review(limit=per_page, offset=offset)
                total = post_repo.count_by_status(PostStatus.PENDING_REVIEW)
        else:
            posts = post_repo.get_pending_review(limit=per_page, offset=offset)
            total = post_repo.count_by_status(PostStatus.PENDING_REVIEW)
        
        total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse(
        "review_queue.html",
        {
            "request": request,
            "user": user,
            "posts": posts,
            "current_status": status or "pending_review",
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "page_title": "Review Queue",
        },
    )


@router.get("/review/{post_id}", response_class=HTMLResponse)
async def review_post(
    request: Request,
    post_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Review a single post with side-by-side comparison to source.
    """
    templates = request.app.state.templates
    
    with get_session() as session:
        post_repo = PostRepository(session)
        post = post_repo.get_by_id(post_id)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Get related analysis and finding
        analysis = post.analysis
        finding = analysis.finding if analysis else None
        source = finding.source if finding else None
    
    return templates.TemplateResponse(
        "review_post.html",
        {
            "request": request,
            "user": user,
            "post": post,
            "analysis": analysis,
            "finding": finding,
            "source": source,
            "page_title": f"Review: {post.title[:50]}...",
        },
    )


# =============================================================================
# Post Actions (HTMX endpoints)
# =============================================================================

@router.post("/review/{post_id}/approve", response_class=HTMLResponse)
async def approve_post(
    request: Request,
    post_id: UUID,
    user: str = Depends(get_current_user),
    publish_now: bool = Form(False),
    notes: str = Form(""),
):
    """
    Approve a post (HTMX endpoint).
    """
    with get_session() as session:
        post_repo = PostRepository(session)
        
        post = post_repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        post_repo.approve(
            post_id,
            reviewed_by=user,
            notes=notes if notes else None,
            publish_now=publish_now,
        )
        session.commit()
        
        logger.info(
            "Post approved",
            extra={
                "post_id": str(post_id),
                "publish_now": publish_now,
                "reviewed_by": user,
            },
        )
    
    # Return HTMX response
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/post_status.html",
        {
            "request": request,
            "status": "published" if publish_now else "approved",
            "message": "Post published!" if publish_now else "Post approved!",
        },
    )


@router.post("/review/{post_id}/reject", response_class=HTMLResponse)
async def reject_post(
    request: Request,
    post_id: UUID,
    user: str = Depends(get_current_user),
    reason: str = Form(...),
):
    """
    Reject a post (HTMX endpoint).
    """
    with get_session() as session:
        post_repo = PostRepository(session)
        
        post = post_repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        post_repo.reject(
            post_id,
            reviewed_by=user,
            reason=reason,
        )
        session.commit()
        
        logger.info(
            "Post rejected",
            extra={
                "post_id": str(post_id),
                "reason": reason[:100],
                "reviewed_by": user,
            },
        )
    
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/post_status.html",
        {
            "request": request,
            "status": "rejected",
            "message": "Post rejected",
        },
    )


@router.post("/review/{post_id}/edit", response_class=HTMLResponse)
async def edit_post(
    request: Request,
    post_id: UUID,
    user: str = Depends(get_current_user),
    title: str = Form(...),
    content_markdown: str = Form(...),
    tags: str = Form(""),
):
    """
    Edit post content (HTMX endpoint).
    """
    with get_session() as session:
        post_repo = PostRepository(session)
        
        post = post_repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        
        post_repo.update(
            post_id,
            title=title,
            content_markdown=content_markdown,
            tags=tag_list,
        )
        session.commit()
        
        logger.info(
            "Post edited",
            extra={
                "post_id": str(post_id),
                "edited_by": user,
            },
        )
    
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/post_status.html",
        {
            "request": request,
            "status": "saved",
            "message": "Changes saved",
        },
    )


# =============================================================================
# Findings
# =============================================================================

@router.get("/findings", response_class=HTMLResponse)
async def findings_list(
    request: Request,
    user: str = Depends(get_current_user),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    """
    List all findings with filtering.
    """
    templates = request.app.state.templates
    
    per_page = 25
    offset = (page - 1) * per_page
    
    with get_session() as session:
        finding_repo = FindingRepository(session)
        source_repo = SourceRepository(session)
        
        # Get all sources for filter dropdown
        all_sources = source_repo.get_all()
        
        # Apply filters
        filters = {}
        if status:
            try:
                filters["status"] = FindingStatus(status)
            except ValueError:
                pass
        if source:
            source_obj = source_repo.get_by_code(source)
            if source_obj:
                filters["source_id"] = source_obj.id
        
        findings = finding_repo.get_filtered(
            limit=per_page,
            offset=offset,
            **filters,
        )
        total = finding_repo.count_filtered(**filters)
        total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse(
        "findings.html",
        {
            "request": request,
            "user": user,
            "findings": findings,
            "sources": all_sources,
            "current_status": status,
            "current_source": source,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "page_title": "Findings",
        },
    )


@router.get("/findings/{finding_id}", response_class=HTMLResponse)
async def finding_detail(
    request: Request,
    finding_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    View a single finding with all details.
    """
    templates = request.app.state.templates
    
    with get_session() as session:
        finding_repo = FindingRepository(session)
        analysis_repo = AnalysisRepository(session)
        
        finding = finding_repo.get_by_id(finding_id)
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")
        
        # Get related analyses
        analyses = analysis_repo.get_by_finding(finding_id)
    
    return templates.TemplateResponse(
        "finding_detail.html",
        {
            "request": request,
            "user": user,
            "finding": finding,
            "analyses": analyses,
            "page_title": f"Finding: {finding.title[:50]}...",
        },
    )


# =============================================================================
# Sources
# =============================================================================

@router.get("/sources", response_class=HTMLResponse)
async def sources_list(
    request: Request,
    user: str = Depends(get_current_user),
):
    """
    List all configured data sources.
    """
    templates = request.app.state.templates
    
    with get_session() as session:
        source_repo = SourceRepository(session)
        finding_repo = FindingRepository(session)
        
        sources = source_repo.get_all()
        
        # Get counts for each source
        source_counts = {}
        for source in sources:
            source_counts[source.id] = finding_repo.count_by_source(source.id)
    
    return templates.TemplateResponse(
        "sources.html",
        {
            "request": request,
            "user": user,
            "sources": sources,
            "source_counts": source_counts,
            "page_title": "Data Sources",
        },
    )


@router.post("/sources/{source_id}/toggle", response_class=HTMLResponse)
async def toggle_source(
    request: Request,
    source_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Toggle source active status (HTMX endpoint).
    """
    with get_session() as session:
        source_repo = SourceRepository(session)
        
        source = source_repo.get_by_id(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        source_repo.toggle_active(source_id)
        session.commit()
        
        # Refresh to get new status
        session.refresh(source)
        
        logger.info(
            "Source toggled",
            extra={
                "source_code": source.code,
                "is_active": source.is_active,
                "toggled_by": user,
            },
        )
    
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/source_status.html",
        {
            "request": request,
            "source": source,
        },
    )


@router.post("/sources/{source_id}/trigger", response_class=HTMLResponse)
async def trigger_scrape(
    request: Request,
    source_id: UUID,
    user: str = Depends(get_current_user),
):
    """
    Manually trigger a scrape for a source (HTMX endpoint).
    """
    templates = request.app.state.templates

    # Get the source to retrieve the source code
    with get_session() as session:
        source_repo = SourceRepository(session)
        source = source_repo.get_by_id(source_id)

        if not source:
            logger.error(f"Source not found: {source_id}")
            return templates.TemplateResponse(
                "partials/trigger_status.html",
                {
                    "request": request,
                    "status": "error",
                    "message": "Source not found",
                },
            )

        if not source.is_active:
            logger.warning(
                "Attempted to trigger inactive source",
                extra={
                    "source_id": str(source_id),
                    "source_code": source.code,
                    "triggered_by": user,
                },
            )
            return templates.TemplateResponse(
                "partials/trigger_status.html",
                {
                    "request": request,
                    "status": "error",
                    "message": "Source is inactive",
                },
            )

        source_code = source.code

    # Get scheduler from app state
    scheduler = request.app.state.scheduler

    # Trigger the scraper in the background
    try:
        asyncio.create_task(scheduler.trigger_scraper(source_code))

        logger.info(
            "Manual scrape triggered",
            extra={
                "source_id": str(source_id),
                "source_code": source_code,
                "triggered_by": user,
            },
        )

        return templates.TemplateResponse(
            "partials/trigger_status.html",
            {
                "request": request,
                "status": "triggered",
                "message": f"Scrape started for {source.name}",
            },
        )
    except Exception as e:
        logger.exception(
            "Failed to trigger scraper",
            extra={
                "source_id": str(source_id),
                "source_code": source_code,
                "error": str(e),
            },
        )
        return templates.TemplateResponse(
            "partials/trigger_status.html",
            {
                "request": request,
                "status": "error",
                "message": f"Failed to start scraper: {str(e)}",
            },
        )


# =============================================================================
# Analytics
# =============================================================================

@router.get("/analytics", response_class=HTMLResponse)
async def analytics(
    request: Request,
    user: str = Depends(get_current_user),
):
    """
    Analytics dashboard showing processing statistics.
    """
    templates = request.app.state.templates
    
    with get_session() as session:
        post_repo = PostRepository(session)
        finding_repo = FindingRepository(session)
        analysis_repo = AnalysisRepository(session)
        source_repo = SourceRepository(session)
        
        # Gather comprehensive stats
        stats = {
            "posts": {
                "total": post_repo.count(),
                "published": post_repo.count_by_status(PostStatus.PUBLISHED),
                "pending": post_repo.count_by_status(PostStatus.PENDING_REVIEW),
                "rejected": post_repo.count_by_status(PostStatus.REJECTED),
            },
            "findings": {
                "total": finding_repo.count(),
                "new": len(finding_repo.get_by_status(FindingStatus.NEW)),
                "classified": len(finding_repo.get_by_status(FindingStatus.CLASSIFIED)),
                "analysed": len(finding_repo.get_by_status(FindingStatus.ANALYSED)),
                "healthcare": len(finding_repo.get_healthcare_findings()),
            },
            "analyses": {
                "total": analysis_repo.count(),
                "total_cost": analysis_repo.get_total_cost(),
                "total_tokens": analysis_repo.get_total_tokens(),
            },
            "sources": {
                "total": source_repo.count(),
                "active": len(source_repo.get_active_sources()),
            },
        }
        
        # Get source breakdown
        sources = source_repo.get_all()
        source_stats = []
        for source in sources:
            count = finding_repo.count_by_source(source.id)
            source_stats.append({
                "code": source.code,
                "name": source.name,
                "count": count,
                "last_scraped": source.last_scraped_at,
                "is_active": source.is_active,
            })
    
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "source_stats": source_stats,
            "page_title": "Analytics",
        },
    )
