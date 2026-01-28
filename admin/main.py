"""
Patient Safety Monitor - Admin Dashboard Application

FastAPI application providing a web interface for:
- Reviewing AI-generated blog posts
- Approving/rejecting content
- Managing data sources
- Viewing analytics

Uses HTMX for dynamic interactions without a JavaScript framework.
"""

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordBearer

from config.settings import get_settings
from config.logging import setup_logging, get_logger
from database.connection import init_database, get_session
from scrapers.scheduler import ScraperScheduler


logger = get_logger(__name__)

# =============================================================================
# Application Factory
# =============================================================================

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    settings = get_settings()
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler for startup/shutdown."""
        logger.info("=" * 60)
        logger.info("Patient Safety Monitor - Admin Dashboard Starting")
        logger.info("=" * 60)

        # Initialize database connection
        if not init_database():
            logger.error("Failed to initialize database connection")
            raise RuntimeError("Database initialization failed")

        # Initialize scraper scheduler (for manual triggers only, not auto-scheduling)
        scheduler = ScraperScheduler()
        app.state.scheduler = scheduler
        logger.info("ScraperScheduler initialized for manual triggers")

        logger.info("Admin dashboard ready")
        yield

        logger.info("Admin dashboard shutting down")
    
    app = FastAPI(
        title="Patient Safety Monitor Admin",
        description="Admin dashboard for reviewing and publishing patient safety findings",
        version="1.0.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # Mount static files
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")
    
    # Setup templates
    templates_path = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=templates_path)
    app.state.templates = templates
    
    # Add custom template filters
    templates.env.filters["datetime"] = format_datetime
    templates.env.filters["truncate_words"] = truncate_words
    
    # Include routes
    from admin.routes import router as admin_router
    from admin.api import router as api_router
    
    app.include_router(admin_router)
    app.include_router(api_router, prefix="/api")
    
    return app


# =============================================================================
# Template Filters
# =============================================================================

def format_datetime(value: Optional[datetime], format_str: str = "%Y-%m-%d %H:%M") -> str:
    """Format datetime for display in templates."""
    if value is None:
        return "—"
    return value.strftime(format_str)


def truncate_words(value: str, num_words: int = 30) -> str:
    """Truncate text to a specified number of words."""
    if not value:
        return ""
    words = value.split()
    if len(words) <= num_words:
        return value
    return " ".join(words[:num_words]) + "..."


# =============================================================================
# Authentication
# =============================================================================

security = HTTPBasic()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """
    Validate HTTP Basic Auth credentials using bcrypt.

    Supports both bcrypt hashed passwords (recommended) and plain text passwords
    (for backward compatibility during migration).

    Args:
        credentials: HTTP Basic Auth credentials

    Returns:
        Username if valid

    Raises:
        HTTPException: If credentials are invalid
    """
    settings = get_settings()

    # Constant-time comparison for username to prevent timing attacks
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        settings.admin_username.encode("utf8"),
    )

    # Password verification with bcrypt support
    password_hash = settings.admin_password_hash
    correct_password = False

    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        # Bcrypt hash - use bcrypt.checkpw()
        try:
            correct_password = bcrypt.checkpw(
                credentials.password.encode("utf8"),
                password_hash.encode("utf8"),
            )
        except (ValueError, AttributeError) as e:
            logger.error(f"Bcrypt verification error: {e}")
            correct_password = False
    else:
        # Backward compatibility: plain text password (deprecated)
        logger.warning(
            "Using plain text password comparison (deprecated). "
            "Please migrate to bcrypt hashed passwords."
        )
        correct_password = secrets.compare_digest(
            credentials.password.encode("utf8"),
            password_hash.encode("utf8"),
        )

    if not (correct_username and correct_password):
        logger.warning(
            "Failed login attempt",
            extra={"username": credentials.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.debug(f"User authenticated: {credentials.username}")
    return credentials.username


def get_current_user_jwt(
    token: Optional[str] = Depends(oauth2_scheme),
) -> str:
    """
    Validate JWT token and return the current user.

    Args:
        token: JWT token from Authorization header

    Returns:
        Username if token is valid

    Raises:
        HTTPException: If token is invalid or missing
    """
    from admin.auth import verify_token
    from jose import JWTError

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_data = verify_token(token)
        if token_data.username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.debug(f"JWT authenticated user: {token_data.username}")
        return token_data.username
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> str:
    """
    Get current user from either JWT token or HTTP Basic auth.
    Tries JWT first, falls back to Basic auth.

    This provides backward compatibility while migrating to JWT.

    Args:
        token: JWT token (optional)
        credentials: HTTP Basic credentials (optional)

    Returns:
        Username if authentication successful

    Raises:
        HTTPException: If neither authentication method succeeds
    """
    from admin.auth import verify_token
    from jose import JWTError

    # Try JWT authentication first
    if token:
        try:
            token_data = verify_token(token)
            if token_data.username:
                logger.debug(f"User authenticated via JWT: {token_data.username}")
                return token_data.username
        except JWTError:
            pass  # Fall through to Basic auth

    # Fall back to HTTP Basic authentication
    if credentials:
        try:
            return get_current_user(credentials)
        except HTTPException:
            pass  # Re-raise below

    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer, Basic"},
    )


# =============================================================================
# Health Check
# =============================================================================

app = create_app()


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "admin-dashboard",
    }


@app.get("/")
async def root():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard", status_code=302)


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors with a custom page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "error_code": 404,
            "error_message": "Page not found",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    """Handle 500 errors with a custom page."""
    logger.exception("Internal server error", extra={"path": request.url.path})
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "error_code": 500,
            "error_message": "Internal server error",
        },
        status_code=500,
    )


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    setup_logging()
    settings = get_settings()
    
    uvicorn.run(
        "admin.main:app",
        host="0.0.0.0",
        port=7410,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
