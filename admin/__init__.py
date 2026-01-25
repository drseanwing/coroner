"""
Patient Safety Monitor - Admin Dashboard Package

FastAPI-based admin interface for reviewing and publishing patient safety findings.

Modules:
    main: FastAPI application entry point
    routes: API and page routes
    auth: Authentication middleware
    dependencies: Shared dependencies
"""

from admin.main import app, create_app

__all__ = [
    "app",
    "create_app",
]
