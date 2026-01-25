"""
Patient Safety Monitor - Static Blog Generator

Generates static HTML files from published posts for deployment.

Features:
- Markdown to HTML conversion
- Jinja2 templates for consistent styling
- RSS feed generation
- Sitemap generation
- Tag and source index pages

Usage:
    generator = BlogGenerator()
    generator.generate_all()
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import get_settings
from config.logging import get_logger
from database.connection import get_session
from database.models import Post, PostStatus
from database.repository import PostRepository


logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """Result of static site generation."""
    
    posts_generated: int = 0
    index_pages_generated: int = 0
    tag_pages_generated: int = 0
    source_pages_generated: int = 0
    rss_generated: bool = False
    sitemap_generated: bool = False
    errors: list[str] = field(default_factory=list)
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class BlogGenerator:
    """
    Static site generator for the patient safety blog.
    
    Generates HTML files from published posts using Jinja2 templates,
    including index pages, tag pages, RSS feed, and sitemap.
    """
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
    ):
        """
        Initialize the blog generator.
        
        Args:
            output_dir: Directory for generated files (default: data/public_html)
            templates_dir: Directory containing Jinja2 templates
        """
        self.settings = get_settings()
        
        # Output directory for generated files
        self.output_dir = output_dir or Path("data/public_html")
        
        # Templates directory
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        
        # Markdown converter with extensions
        self.md = markdown.Markdown(
            extensions=[
                "extra",          # Tables, fenced code, etc.
                "meta",           # Metadata support
                "toc",            # Table of contents
                "codehilite",     # Syntax highlighting
                "smarty",         # Smart quotes
            ],
            extension_configs={
                "codehilite": {
                    "css_class": "highlight",
                    "linenums": False,
                },
            },
        )
        
        # Initialize Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        
        # Add custom filters
        self.jinja_env.filters["datetime"] = self._format_datetime
        self.jinja_env.filters["truncate_words"] = self._truncate_words
        self.jinja_env.filters["markdown"] = self._render_markdown
        
        # Site configuration
        self.site_config = {
            "title": "Patient Safety Monitor",
            "description": "Learnings from coronial investigations and patient safety incidents",
            "base_url": self.settings.blog_base_url or "https://patientsafetymonitor.org",
            "author": "Patient Safety Monitor",
            "language": "en",
        }
    
    def generate_all(self) -> GenerationResult:
        """
        Generate the complete static site.
        
        Returns:
            GenerationResult with statistics
        """
        result = GenerationResult()
        
        logger.info("Starting static site generation")
        
        try:
            # Ensure output directory exists
            self._setup_output_dir()
            
            # Load published posts
            with get_session() as session:
                repo = PostRepository(session)
                posts = repo.get_by_status(PostStatus.PUBLISHED)
                
                logger.info(f"Found {len(posts)} published posts")
                
                # Generate individual post pages
                for post in posts:
                    try:
                        self._generate_post(post)
                        result.posts_generated += 1
                    except Exception as e:
                        logger.error(f"Failed to generate post {post.slug}: {e}")
                        result.errors.append(f"Post {post.slug}: {e}")
                
                # Generate index pages
                self._generate_index(posts)
                self._generate_archive(posts)
                result.index_pages_generated += 2
                
                # Generate tag pages
                tags = self._collect_tags(posts)
                for tag, tag_posts in tags.items():
                    try:
                        self._generate_tag_page(tag, tag_posts)
                        result.tag_pages_generated += 1
                    except Exception as e:
                        logger.error(f"Failed to generate tag page {tag}: {e}")
                        result.errors.append(f"Tag {tag}: {e}")
                
                # Generate static pages
                self._generate_about_page()
                result.index_pages_generated += 1
                
                # Generate RSS feed
                self._generate_rss(posts)
                result.rss_generated = True
                
                # Generate sitemap
                self._generate_sitemap(posts, tags.keys())
                result.sitemap_generated = True
                
                # Copy static assets
                self._copy_assets()
            
        except Exception as e:
            logger.exception(f"Site generation failed: {e}")
            result.errors.append(f"Fatal error: {e}")
        
        result.completed_at = datetime.utcnow()
        
        logger.info(
            "Static site generation complete",
            extra={
                "posts": result.posts_generated,
                "index_pages": result.index_pages_generated,
                "tag_pages": result.tag_pages_generated,
                "duration_seconds": result.duration_seconds,
                "errors": len(result.errors),
            },
        )
        
        return result
    
    def generate_single_post(self, post: Post) -> bool:
        """
        Generate a single post page.
        
        Args:
            post: Post to generate
            
        Returns:
            True if successful
        """
        try:
            self._generate_post(post)
            return True
        except Exception as e:
            logger.error(f"Failed to generate post {post.slug}: {e}")
            return False
    
    # =========================================================================
    # Generation Methods
    # =========================================================================
    
    def _setup_output_dir(self) -> None:
        """Create output directory structure."""
        directories = [
            self.output_dir,
            self.output_dir / "posts",
            self.output_dir / "tags",
            self.output_dir / "sources",
            self.output_dir / "about",
            self.output_dir / "assets" / "css",
            self.output_dir / "assets" / "js",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"Output directory structure created: {self.output_dir}")
    
    def _generate_post(self, post: Post) -> None:
        """Generate a single post HTML page."""
        template = self.jinja_env.get_template("post.html")
        
        # Convert markdown to HTML
        self.md.reset()
        content_html = self.md.convert(post.content_markdown)
        
        # Get analysis data for human factors display
        analysis = post.analysis if hasattr(post, 'analysis') else None
        finding = analysis.finding if analysis else None
        
        # Render template
        html = template.render(
            site=self.site_config,
            post=post,
            content_html=content_html,
            analysis=analysis,
            finding=finding,
            generated_at=datetime.utcnow(),
        )
        
        # Write to file
        post_dir = self.output_dir / "posts" / post.slug
        post_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = post_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        
        logger.debug(f"Generated post: {post.slug}")
    
    def _generate_index(self, posts: list[Post]) -> None:
        """Generate the homepage with recent posts."""
        template = self.jinja_env.get_template("index.html")
        
        # Sort by publication date, newest first
        sorted_posts = sorted(
            posts,
            key=lambda p: p.published_at or p.created_at,
            reverse=True,
        )
        
        # Take first 10 for homepage
        recent_posts = sorted_posts[:10]
        
        html = template.render(
            site=self.site_config,
            posts=recent_posts,
            total_posts=len(posts),
            generated_at=datetime.utcnow(),
        )
        
        output_path = self.output_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        
        logger.debug("Generated index page")
    
    def _generate_archive(self, posts: list[Post]) -> None:
        """Generate the archive page with all posts."""
        template = self.jinja_env.get_template("archive.html")
        
        # Sort by publication date, newest first
        sorted_posts = sorted(
            posts,
            key=lambda p: p.published_at or p.created_at,
            reverse=True,
        )
        
        # Group by year-month
        grouped = {}
        for post in sorted_posts:
            date = post.published_at or post.created_at
            key = date.strftime("%Y-%m")
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(post)
        
        html = template.render(
            site=self.site_config,
            grouped_posts=grouped,
            total_posts=len(posts),
            generated_at=datetime.utcnow(),
        )
        
        # Create posts index
        post_index_dir = self.output_dir / "posts"
        post_index_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = post_index_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        
        logger.debug("Generated archive page")
    
    def _generate_tag_page(self, tag: str, posts: list[Post]) -> None:
        """Generate a tag listing page."""
        template = self.jinja_env.get_template("tag.html")
        
        # Sort posts by date
        sorted_posts = sorted(
            posts,
            key=lambda p: p.published_at or p.created_at,
            reverse=True,
        )
        
        html = template.render(
            site=self.site_config,
            tag=tag,
            posts=sorted_posts,
            generated_at=datetime.utcnow(),
        )
        
        # Create tag directory
        tag_slug = self._slugify(tag)
        tag_dir = self.output_dir / "tags" / tag_slug
        tag_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = tag_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        
        logger.debug(f"Generated tag page: {tag}")
    
    def _generate_about_page(self) -> None:
        """Generate the about page."""
        template = self.jinja_env.get_template("about.html")
        
        html = template.render(
            site=self.site_config,
            generated_at=datetime.utcnow(),
        )
        
        output_path = self.output_dir / "about" / "index.html"
        output_path.write_text(html, encoding="utf-8")
        
        logger.debug("Generated about page")
    
    def _generate_rss(self, posts: list[Post]) -> None:
        """Generate RSS feed."""
        template = self.jinja_env.get_template("feed.xml")
        
        # Sort by date, newest first
        sorted_posts = sorted(
            posts,
            key=lambda p: p.published_at or p.created_at,
            reverse=True,
        )[:20]  # RSS typically shows last 20
        
        xml = template.render(
            site=self.site_config,
            posts=sorted_posts,
            generated_at=datetime.utcnow(),
        )
        
        output_path = self.output_dir / "feed.xml"
        output_path.write_text(xml, encoding="utf-8")
        
        logger.debug("Generated RSS feed")
    
    def _generate_sitemap(self, posts: list[Post], tags: list[str]) -> None:
        """Generate XML sitemap."""
        urlset = ET.Element("urlset")
        urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
        
        base_url = self.site_config["base_url"].rstrip("/")
        
        # Add homepage
        self._add_sitemap_url(urlset, f"{base_url}/", "daily", "1.0")
        
        # Add about page
        self._add_sitemap_url(urlset, f"{base_url}/about/", "monthly", "0.5")
        
        # Add posts archive
        self._add_sitemap_url(urlset, f"{base_url}/posts/", "daily", "0.8")
        
        # Add individual posts
        for post in posts:
            url = f"{base_url}/posts/{post.slug}/"
            lastmod = (post.published_at or post.created_at).strftime("%Y-%m-%d")
            self._add_sitemap_url(urlset, url, "monthly", "0.7", lastmod)
        
        # Add tag pages
        for tag in tags:
            tag_slug = self._slugify(tag)
            url = f"{base_url}/tags/{tag_slug}/"
            self._add_sitemap_url(urlset, url, "weekly", "0.6")
        
        # Write sitemap
        tree = ET.ElementTree(urlset)
        output_path = self.output_dir / "sitemap.xml"
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        
        logger.debug("Generated sitemap")
    
    def _add_sitemap_url(
        self,
        urlset: ET.Element,
        loc: str,
        changefreq: str,
        priority: str,
        lastmod: Optional[str] = None,
    ) -> None:
        """Add a URL entry to the sitemap."""
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = loc
        if lastmod:
            ET.SubElement(url, "lastmod").text = lastmod
        ET.SubElement(url, "changefreq").text = changefreq
        ET.SubElement(url, "priority").text = priority
    
    def _copy_assets(self) -> None:
        """Copy static assets to output directory."""
        # CSS file
        css_content = self._generate_css()
        css_path = self.output_dir / "assets" / "css" / "main.css"
        css_path.write_text(css_content, encoding="utf-8")
        
        # JS file for search (minimal)
        js_content = self._generate_js()
        js_path = self.output_dir / "assets" / "js" / "search.js"
        js_path.write_text(js_content, encoding="utf-8")
        
        logger.debug("Copied static assets")
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _collect_tags(self, posts: list[Post]) -> dict[str, list[Post]]:
        """Collect all tags and their associated posts."""
        tags: dict[str, list[Post]] = {}
        
        for post in posts:
            if post.tags:
                for tag in post.tags:
                    if tag not in tags:
                        tags[tag] = []
                    tags[tag].append(post)
        
        return tags
    
    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        import re
        slug = text.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")
    
    def _format_datetime(
        self,
        value: Optional[datetime],
        format_str: str = "%Y-%m-%d",
    ) -> str:
        """Format datetime for templates."""
        if value is None:
            return ""
        return value.strftime(format_str)
    
    def _truncate_words(self, text: str, num_words: int = 30) -> str:
        """Truncate text to specified number of words."""
        if not text:
            return ""
        words = text.split()
        if len(words) <= num_words:
            return text
        return " ".join(words[:num_words]) + "..."
    
    def _render_markdown(self, text: str) -> str:
        """Render markdown to HTML."""
        self.md.reset()
        return self.md.convert(text)
    
    def _generate_css(self) -> str:
        """Generate main CSS file."""
        return """
/* Patient Safety Monitor - Main Styles */
/* Using Tailwind via CDN in templates, this provides overrides */

:root {
    --primary-color: #4f46e5;
    --secondary-color: #6366f1;
    --text-color: #1f2937;
    --text-muted: #6b7280;
    --border-color: #e5e7eb;
    --bg-light: #f9fafb;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
}

/* Article content styling */
.prose {
    max-width: 65ch;
}

.prose h1, .prose h2, .prose h3, .prose h4 {
    color: var(--text-color);
    font-weight: 700;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}

.prose h1 { font-size: 2em; }
.prose h2 { font-size: 1.5em; }
.prose h3 { font-size: 1.25em; }

.prose p {
    margin-bottom: 1em;
}

.prose ul, .prose ol {
    margin-left: 1.5em;
    margin-bottom: 1em;
}

.prose li {
    margin-bottom: 0.25em;
}

.prose blockquote {
    border-left: 4px solid var(--primary-color);
    padding-left: 1em;
    margin: 1em 0;
    color: var(--text-muted);
    font-style: italic;
}

/* Code highlighting */
.highlight {
    background: var(--bg-light);
    border-radius: 0.375rem;
    padding: 1em;
    overflow-x: auto;
    margin: 1em 0;
}

.highlight code {
    font-family: 'Fira Code', 'Monaco', 'Consolas', monospace;
    font-size: 0.875em;
}

/* Key learnings box */
.key-learnings {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-left: 4px solid #f59e0b;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin: 1.5rem 0;
}

.key-learnings h3 {
    color: #92400e;
    margin-top: 0;
}

/* Human factors cards */
.human-factors-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}

.human-factors-card {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    padding: 1rem;
}

.human-factors-card h4 {
    color: var(--primary-color);
    margin-top: 0;
    margin-bottom: 0.5rem;
}

/* Print styles */
@media print {
    .no-print {
        display: none !important;
    }
    
    body {
        font-size: 12pt;
    }
    
    .prose {
        max-width: none;
    }
}
"""
    
    def _generate_js(self) -> str:
        """Generate search JavaScript."""
        return """
// Patient Safety Monitor - Client-side Search
// Minimal implementation for static site

(function() {
    'use strict';
    
    // Search index will be loaded from search-index.json
    let searchIndex = [];
    
    // Initialize search
    function initSearch() {
        const searchInput = document.getElementById('search-input');
        const searchResults = document.getElementById('search-results');
        
        if (!searchInput || !searchResults) return;
        
        // Load search index
        fetch('/search-index.json')
            .then(response => response.json())
            .then(data => { searchIndex = data; })
            .catch(err => console.log('Search index not available'));
        
        // Handle input
        searchInput.addEventListener('input', function(e) {
            const query = e.target.value.toLowerCase().trim();
            
            if (query.length < 2) {
                searchResults.innerHTML = '';
                searchResults.classList.add('hidden');
                return;
            }
            
            const results = searchIndex.filter(item => 
                item.title.toLowerCase().includes(query) ||
                item.excerpt.toLowerCase().includes(query) ||
                item.tags.some(tag => tag.toLowerCase().includes(query))
            ).slice(0, 10);
            
            displayResults(results, searchResults);
        });
    }
    
    function displayResults(results, container) {
        if (results.length === 0) {
            container.innerHTML = '<div class="p-4 text-gray-500">No results found</div>';
            container.classList.remove('hidden');
            return;
        }
        
        const html = results.map(item => `
            <a href="${item.url}" class="block p-4 hover:bg-gray-50 border-b last:border-b-0">
                <h4 class="font-medium text-gray-900">${item.title}</h4>
                <p class="text-sm text-gray-500 mt-1">${item.excerpt}</p>
            </a>
        `).join('');
        
        container.innerHTML = html;
        container.classList.remove('hidden');
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSearch);
    } else {
        initSearch();
    }
})();
"""


# =============================================================================
# CLI Entry Point
# =============================================================================

def main() -> int:
    """
    Command-line entry point for static site generation.
    
    Usage:
        python -m publishing.generator
    """
    import sys
    from config.logging import setup_logging
    from database.connection import init_database
    
    setup_logging()
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Static Site Generator")
    logger.info("=" * 60)
    
    if not init_database():
        logger.error("Database initialization failed")
        return 1
    
    generator = BlogGenerator()
    result = generator.generate_all()
    
    print(f"\nGeneration Complete:")
    print(f"  Posts generated: {result.posts_generated}")
    print(f"  Index pages: {result.index_pages_generated}")
    print(f"  Tag pages: {result.tag_pages_generated}")
    print(f"  RSS feed: {'Yes' if result.rss_generated else 'No'}")
    print(f"  Sitemap: {'Yes' if result.sitemap_generated else 'No'}")
    print(f"  Duration: {result.duration_seconds:.1f}s")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:10]:
            print(f"  - {error}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
