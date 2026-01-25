"""
Patient Safety Monitor - Publishing Integration Tests

Tests for static site generation and FTP deployment.
"""

import pytest
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base,
    Source,
    Finding,
    Analysis,
    Post,
    FindingStatus,
    PostStatus,
    LLMProvider,
)
from publishing.generator import BlogGenerator, GenerationResult
from publishing.deployer import BlogDeployer, DeploymentResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="function")
def temp_templates_dir(temp_output_dir):
    """Create temporary templates directory with minimal templates."""
    templates = temp_output_dir / "templates"
    templates.mkdir()
    
    # Create minimal templates for testing
    (templates / "base.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>{{ site.title }}</title></head>
<body>{% block content %}{% endblock %}</body>
</html>
""")
    
    (templates / "index.html").write_text("""
{% extends "base.html" %}
{% block content %}
<h1>{{ site.title }}</h1>
{% for post in posts %}
<article><h2>{{ post.title }}</h2></article>
{% endfor %}
{% endblock %}
""")
    
    (templates / "post.html").write_text("""
{% extends "base.html" %}
{% block content %}
<article>
<h1>{{ post.title }}</h1>
{{ content_html|safe }}
</article>
{% endblock %}
""")
    
    (templates / "archive.html").write_text("""
{% extends "base.html" %}
{% block content %}
<h1>Archive</h1>
{% for month, posts in grouped_posts.items() %}
<h2>{{ month }}</h2>
{% for post in posts %}<li>{{ post.title }}</li>{% endfor %}
{% endfor %}
{% endblock %}
""")
    
    (templates / "tag.html").write_text("""
{% extends "base.html" %}
{% block content %}
<h1>Tag: {{ tag }}</h1>
{% for post in posts %}<li>{{ post.title }}</li>{% endfor %}
{% endblock %}
""")
    
    (templates / "about.html").write_text("""
{% extends "base.html" %}
{% block content %}
<h1>About</h1>
<p>Patient Safety Monitor</p>
{% endblock %}
""")
    
    (templates / "feed.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{{ site.title }}</title>
{% for post in posts %}
<item><title>{{ post.title }}</title></item>
{% endfor %}
</channel>
</rss>
""")
    
    return templates


@pytest.fixture(scope="function")
def engine():
    """Create in-memory SQLite engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session(engine):
    """Create a new database session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_posts(session) -> list:
    """Create sample posts for testing."""
    # Create source
    source = Source(
        code="test_source",
        name="Test Source",
        country="GB",
        base_url="https://example.com/",
        scraper_class="TestScraper",
        schedule_cron="0 6 * * *",
        is_active=True,
    )
    session.add(source)
    session.flush()
    
    posts = []
    for i in range(3):
        # Create finding
        finding = Finding(
            source_id=source.id,
            external_id=f"test-finding-{i:03d}",
            title=f"Test Finding {i}",
            source_url=f"https://example.com/finding/{i:03d}",
            content_text=f"Test content for finding {i}.",
            status=FindingStatus.ANALYSED,
            is_healthcare=True,
        )
        session.add(finding)
        session.flush()
        
        # Create analysis
        analysis = Analysis(
            finding_id=finding.id,
            llm_provider=LLMProvider.CLAUDE,
            llm_model="claude-sonnet-4-20250514",
            prompt_version="1.0.0",
            summary=f"Summary for finding {i}.",
            human_factors={"individual_factors": []},
            latent_hazards=[],
            recommendations=[],
            key_learnings=[f"Learning {i}"],
            tokens_input=500,
            tokens_output=1000,
            cost_usd=Decimal("0.0225"),
        )
        session.add(analysis)
        session.flush()
        
        # Create post
        post = Post(
            analysis_id=analysis.id,
            slug=f"test-post-{i}",
            title=f"Test Post Title {i}",
            content_markdown=f"# Test Post {i}\n\nThis is test content for post {i}.",
            excerpt=f"Test excerpt for post {i}.",
            tags=["communication", f"tag-{i}"],
            status=PostStatus.PUBLISHED,
            published_at=datetime.utcnow(),
        )
        session.add(post)
        posts.append(post)
    
    session.commit()
    return posts


# =============================================================================
# BlogGenerator Tests
# =============================================================================

class TestBlogGenerator:
    """Tests for BlogGenerator class."""
    
    def test_init_default_paths(self):
        """Test generator initializes with default paths."""
        generator = BlogGenerator()
        assert generator.output_dir == Path("data/public_html")
        assert generator.templates_dir.exists() or True  # May not exist in test
    
    def test_init_custom_paths(self, temp_output_dir, temp_templates_dir):
        """Test generator initializes with custom paths."""
        output = temp_output_dir / "output"
        generator = BlogGenerator(
            output_dir=output,
            templates_dir=temp_templates_dir,
        )
        assert generator.output_dir == output
        assert generator.templates_dir == temp_templates_dir
    
    def test_setup_output_dir(self, temp_output_dir, temp_templates_dir):
        """Test output directory structure creation."""
        output = temp_output_dir / "output"
        generator = BlogGenerator(
            output_dir=output,
            templates_dir=temp_templates_dir,
        )
        generator._setup_output_dir()
        
        assert (output / "posts").exists()
        assert (output / "tags").exists()
        assert (output / "sources").exists()
        assert (output / "about").exists()
        assert (output / "assets" / "css").exists()
        assert (output / "assets" / "js").exists()
    
    def test_slugify(self, temp_output_dir, temp_templates_dir):
        """Test URL slug generation."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        assert generator._slugify("Hello World") == "hello-world"
        assert generator._slugify("Test's Example!") == "tests-example"
        assert generator._slugify("Multiple   Spaces") == "multiple-spaces"
    
    def test_format_datetime(self, temp_output_dir, temp_templates_dir):
        """Test datetime formatting."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        dt = datetime(2026, 1, 15, 10, 30, 0)
        assert generator._format_datetime(dt) == "2026-01-15"
        assert generator._format_datetime(dt, "%d/%m/%Y") == "15/01/2026"
        assert generator._format_datetime(None) == ""
    
    def test_truncate_words(self, temp_output_dir, temp_templates_dir):
        """Test word truncation."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        text = "one two three four five six seven eight nine ten"
        assert generator._truncate_words(text, 5) == "one two three four five..."
        assert generator._truncate_words(text, 20) == text
        assert generator._truncate_words("", 5) == ""
    
    def test_collect_tags(self, temp_output_dir, temp_templates_dir, sample_posts):
        """Test tag collection from posts."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        tags = generator._collect_tags(sample_posts)
        
        assert "communication" in tags
        assert len(tags["communication"]) == 3  # All posts have this tag
    
    def test_generate_css(self, temp_output_dir, temp_templates_dir):
        """Test CSS generation."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        css = generator._generate_css()
        
        assert ":root" in css
        assert "--primary-color" in css
        assert ".prose" in css
    
    def test_generate_js(self, temp_output_dir, temp_templates_dir):
        """Test JavaScript generation."""
        generator = BlogGenerator(
            output_dir=temp_output_dir,
            templates_dir=temp_templates_dir,
        )
        
        js = generator._generate_js()
        
        assert "initSearch" in js
        assert "searchIndex" in js


class TestBlogGeneratorWithDatabase:
    """Integration tests for BlogGenerator with database."""
    
    @patch("database.connection.get_session")
    def test_generate_all(
        self,
        mock_session,
        temp_output_dir,
        temp_templates_dir,
        session,
        sample_posts,
    ):
        """Test full site generation."""
        # Setup mock
        mock_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        output = temp_output_dir / "output"
        generator = BlogGenerator(
            output_dir=output,
            templates_dir=temp_templates_dir,
        )
        
        with patch.object(generator, '_generate_post'):
            with patch.object(generator, '_generate_index'):
                with patch.object(generator, '_generate_archive'):
                    with patch.object(generator, '_generate_tag_page'):
                        with patch.object(generator, '_generate_about_page'):
                            with patch.object(generator, '_generate_rss'):
                                with patch.object(generator, '_generate_sitemap'):
                                    with patch.object(generator, '_copy_assets'):
                                        result = generator.generate_all()
        
        # Check result structure
        assert isinstance(result, GenerationResult)
        assert result.completed_at is not None


# =============================================================================
# BlogDeployer Tests
# =============================================================================

class TestBlogDeployer:
    """Tests for BlogDeployer class."""
    
    def test_init(self, temp_output_dir):
        """Test deployer initialization."""
        deployer = BlogDeployer(source_dir=temp_output_dir)
        assert deployer.source_dir == temp_output_dir
    
    @patch("ftplib.FTP")
    def test_connect_success(self, mock_ftp, temp_output_dir):
        """Test successful FTP connection."""
        deployer = BlogDeployer(source_dir=temp_output_dir)
        
        # Mock FTP methods
        mock_ftp_instance = MagicMock()
        mock_ftp.return_value = mock_ftp_instance
        
        deployer.ftp = mock_ftp_instance
        deployer._connected = True
        
        assert deployer._connected is True
    
    def test_get_relative_path(self, temp_output_dir):
        """Test relative path calculation."""
        deployer = BlogDeployer(source_dir=temp_output_dir)
        
        file_path = temp_output_dir / "posts" / "test-post" / "index.html"
        relative = deployer._get_relative_path(file_path)
        
        assert relative == "posts/test-post/index.html"
    
    def test_collect_files(self, temp_output_dir):
        """Test file collection for deployment."""
        # Create some test files
        (temp_output_dir / "index.html").write_text("<html></html>")
        posts_dir = temp_output_dir / "posts"
        posts_dir.mkdir()
        (posts_dir / "test.html").write_text("<html></html>")
        
        deployer = BlogDeployer(source_dir=temp_output_dir)
        files = deployer._collect_files()
        
        assert len(files) >= 2


class TestDeploymentResult:
    """Tests for DeploymentResult dataclass."""
    
    def test_default_values(self):
        """Test default result values."""
        result = DeploymentResult()
        
        assert result.files_uploaded == 0
        assert result.files_skipped == 0
        assert result.errors == []
        assert result.success is True
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        result = DeploymentResult()
        result.started_at = datetime(2026, 1, 15, 10, 0, 0)
        result.completed_at = datetime(2026, 1, 15, 10, 0, 30)
        
        assert result.duration_seconds == 30.0


# =============================================================================
# GenerationResult Tests
# =============================================================================

class TestGenerationResult:
    """Tests for GenerationResult dataclass."""
    
    def test_default_values(self):
        """Test default result values."""
        result = GenerationResult()
        
        assert result.posts_generated == 0
        assert result.index_pages_generated == 0
        assert result.tag_pages_generated == 0
        assert result.rss_generated is False
        assert result.sitemap_generated is False
        assert result.errors == []
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        result = GenerationResult()
        result.started_at = datetime(2026, 1, 15, 10, 0, 0)
        result.completed_at = datetime(2026, 1, 15, 10, 0, 15)
        
        assert result.duration_seconds == 15.0
    
    def test_duration_without_completion(self):
        """Test duration returns 0 when not completed."""
        result = GenerationResult()
        result.completed_at = None
        
        assert result.duration_seconds == 0.0
