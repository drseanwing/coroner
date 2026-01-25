"""
Patient Safety Monitor - Publishing Package

Static site generation and deployment for the patient safety blog.

Modules:
    generator: Static HTML generation from approved posts
    deployer: FTP deployment to Hostinger
    templates: Jinja2 blog templates
    
Usage:
    from publishing import BlogGenerator, BlogDeployer
    
    # Generate static site
    generator = BlogGenerator()
    generator.generate_all()
    
    # Deploy to Hostinger
    deployer = BlogDeployer()
    deployer.deploy()
"""

from publishing.generator import BlogGenerator
from publishing.deployer import BlogDeployer

__all__ = [
    "BlogGenerator",
    "BlogDeployer",
]
