"""
Patient Safety Monitor - Publishing Module Unit Tests

Tests for static site generation, deployment, and search indexing.
Uses pytest fixtures with mocked dependencies for isolation.
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open, call
from io import BytesIO
import ftplib
import hashlib

from publishing.generator import (
    GenerationResult,
    BlogGenerator,
)
from publishing.deployer import (
    DeploymentResult,
    FileManifest,
    BlogDeployer,
)
from publishing.search_index import SearchIndexBuilder


# =============================================================================
# Test GenerationResult
# =============================================================================

class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_default_initialization(self):
        """Test that GenerationResult initializes with correct defaults."""
        result = GenerationResult()

        assert result.posts_generated == 0
        assert result.index_pages_generated == 0
        assert result.tag_pages_generated == 0
        assert result.source_pages_generated == 0
        assert result.rss_generated is False
        assert result.sitemap_generated is False
        assert result.errors == []
        assert result.completed_at is None
        assert isinstance(result.started_at, datetime)

    def test_duration_calculation(self):
        """Test duration_seconds calculation."""
        result = GenerationResult()
        result.started_at = datetime(2024, 1, 1, 12, 0, 0)
        result.completed_at = datetime(2024, 1, 1, 12, 5, 30)

        assert result.duration_seconds == 330.0  # 5 minutes 30 seconds

    def test_duration_zero_when_incomplete(self):
        """Test duration returns 0.0 when not completed."""
        result = GenerationResult()
        assert result.duration_seconds == 0.0


# =============================================================================
# Test DeploymentResult
# =============================================================================

class TestDeploymentResult:
    """Tests for DeploymentResult dataclass."""

    def test_default_initialization(self):
        """Test that DeploymentResult initializes with correct defaults."""
        result = DeploymentResult()

        assert result.success is True
        assert result.files_uploaded == 0
        assert result.files_skipped == 0
        assert result.files_deleted == 0
        assert result.bytes_transferred == 0
        assert result.errors == []
        assert result.warnings == []
        assert result.completed_at is None
        assert isinstance(result.started_at, datetime)

    def test_add_error_marks_failure(self):
        """Test that add_error() appends error and sets success=False."""
        result = DeploymentResult()
        result.add_error("Test error")

        assert result.success is False
        assert "Test error" in result.errors

    def test_duration_calculation(self):
        """Test duration_seconds calculation."""
        result = DeploymentResult()
        result.started_at = datetime(2024, 1, 1, 12, 0, 0)
        result.completed_at = datetime(2024, 1, 1, 12, 0, 45)

        assert result.duration_seconds == 45.0


# =============================================================================
# Test BlogGenerator Helper Methods
# =============================================================================

class TestBlogGenerator:
    """Tests for BlogGenerator class."""

    @pytest.fixture
    def generator(self, tmp_path, mock_settings):
        """Create a BlogGenerator with temp directory."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        # Create minimal template files
        (templates_dir / "post.html").write_text("{{ post.title }}")
        (templates_dir / "index.html").write_text("{{ site.title }}")
        (templates_dir / "archive.html").write_text("Archive")
        (templates_dir / "tag.html").write_text("Tag: {{ tag }}")
        (templates_dir / "source.html").write_text("Source: {{ source.name }}")
        (templates_dir / "about.html").write_text("About")
        (templates_dir / "feed.xml").write_text("<rss></rss>")

        output_dir = tmp_path / "output"

        return BlogGenerator(
            output_dir=output_dir,
            templates_dir=templates_dir,
        )

    def test_slugify_basic(self, generator):
        """Test _slugify with basic text."""
        assert generator._slugify("Hello World") == "hello-world"

    def test_slugify_special_characters(self, generator):
        """Test _slugify removes special characters."""
        assert generator._slugify("Test! @#$ Value") == "test-value"

    def test_slugify_unicode(self, generator):
        """Test _slugify handles unicode."""
        assert generator._slugify("Café René") == "caf-ren"

    def test_slugify_multiple_spaces(self, generator):
        """Test _slugify collapses multiple spaces."""
        assert generator._slugify("Too   Many    Spaces") == "too-many-spaces"

    def test_slugify_leading_trailing_dashes(self, generator):
        """Test _slugify strips leading/trailing dashes."""
        assert generator._slugify("-test-value-") == "test-value"

    def test_format_datetime_default_format(self, generator):
        """Test _format_datetime with default format."""
        dt = datetime(2024, 3, 15, 14, 30, 0)
        assert generator._format_datetime(dt) == "2024-03-15"

    def test_format_datetime_custom_format(self, generator):
        """Test _format_datetime with custom format."""
        dt = datetime(2024, 3, 15, 14, 30, 0)
        assert generator._format_datetime(dt, "%B %d, %Y") == "March 15, 2024"

    def test_format_datetime_none(self, generator):
        """Test _format_datetime with None."""
        assert generator._format_datetime(None) == ""

    def test_truncate_words_under_limit(self, generator):
        """Test _truncate_words when text is under limit."""
        text = "This is a short text"
        result = generator._truncate_words(text, 10)
        assert result == text

    def test_truncate_words_over_limit(self, generator):
        """Test _truncate_words when text exceeds limit."""
        text = "This is a much longer text that should be truncated"
        result = generator._truncate_words(text, 5)
        assert result == "This is a much longer..."

    def test_truncate_words_exact_limit(self, generator):
        """Test _truncate_words at exact word limit."""
        text = "One two three four five"
        result = generator._truncate_words(text, 5)
        assert result == text

    def test_truncate_words_empty_text(self, generator):
        """Test _truncate_words with empty string."""
        assert generator._truncate_words("") == ""

    def test_render_markdown(self, generator):
        """Test _render_markdown converts markdown to HTML."""
        markdown_text = "# Heading\n\nParagraph with **bold** text."
        html = generator._render_markdown(markdown_text)

        assert "<h1>" in html
        assert "<strong>bold</strong>" in html or "<b>bold</b>" in html

    def test_collect_tags_single_post(self, generator, post_factory):
        """Test _collect_tags with single post."""
        post = post_factory(tags=["tag1", "tag2"])
        tags = generator._collect_tags([post])

        assert "tag1" in tags
        assert "tag2" in tags
        assert post in tags["tag1"]
        assert post in tags["tag2"]

    def test_collect_tags_multiple_posts(self, generator, post_factory):
        """Test _collect_tags with multiple posts sharing tags."""
        post1 = post_factory(tags=["python", "testing"])
        post2 = post_factory(tags=["python", "debugging"])

        tags = generator._collect_tags([post1, post2])

        assert "python" in tags
        assert "testing" in tags
        assert "debugging" in tags
        assert len(tags["python"]) == 2
        assert len(tags["testing"]) == 1

    def test_collect_tags_empty_list(self, generator):
        """Test _collect_tags with empty post list."""
        tags = generator._collect_tags([])
        assert tags == {}

    def test_collect_tags_post_without_tags(self, generator, post_factory):
        """Test _collect_tags with post that has no tags."""
        post = post_factory(tags=None)
        tags = generator._collect_tags([post])
        assert tags == {}

    def test_collect_sources(self, generator, post_factory, analysis_factory, finding_factory, source_factory):
        """Test _collect_sources from posts."""
        source1 = source_factory(code="source1", name="Source One", country="GB")
        source2 = source_factory(code="source2", name="Source Two", country="AU")

        finding1 = finding_factory(source=source1)
        finding2 = finding_factory(source=source2)

        analysis1 = analysis_factory(finding=finding1)
        analysis2 = analysis_factory(finding=finding2)

        post1 = post_factory(analysis=analysis1)
        post2 = post_factory(analysis=analysis2)

        sources = generator._collect_sources([post1, post2])

        assert "source1" in sources
        assert "source2" in sources
        assert sources["source1"]["info"]["name"] == "Source One"
        assert sources["source2"]["info"]["country"] == "AU"
        assert post1 in sources["source1"]["posts"]

    def test_collect_sources_post_without_analysis(self, generator, post_factory):
        """Test _collect_sources with post lacking analysis."""
        post = MagicMock()
        post.analysis = None

        sources = generator._collect_sources([post])
        assert sources == {}

    def test_generate_single_post_success(self, generator, post_factory):
        """Test generate_single_post returns True on success."""
        post = post_factory(
            slug="test-post",
            title="Test Post",
            content_markdown="# Test"
        )

        with patch.object(generator, '_generate_post'):
            result = generator.generate_single_post(post)
            assert result is True

    def test_generate_single_post_failure(self, generator, post_factory):
        """Test generate_single_post returns False on exception."""
        post = post_factory(slug="test-post")

        with patch.object(generator, '_generate_post', side_effect=Exception("Test error")):
            result = generator.generate_single_post(post)
            assert result is False

    def test_generate_rss_limits_to_20_posts(self, generator, post_factory):
        """Test _generate_rss only includes last 20 posts."""
        posts = [post_factory(slug=f"post-{i}") for i in range(30)]

        with tempfile.TemporaryDirectory() as tmpdir:
            generator.output_dir = Path(tmpdir)
            generator._generate_rss(posts)

            # Verify feed.xml was created
            feed_path = Path(tmpdir) / "feed.xml"
            assert feed_path.exists()

    def test_generate_sitemap_includes_all_sections(self, generator, post_factory):
        """Test _generate_sitemap includes posts, tags, and sources."""
        posts = [post_factory(slug="test-post")]
        tags = ["python", "testing"]
        sources = ["source1", "source2"]

        with tempfile.TemporaryDirectory() as tmpdir:
            generator.output_dir = Path(tmpdir)
            generator._generate_sitemap(posts, tags, sources)

            sitemap_path = Path(tmpdir) / "sitemap.xml"
            assert sitemap_path.exists()

            content = sitemap_path.read_text()
            assert "posts/test-post" in content
            assert "tags/python" in content
            assert "sources/source1" in content


# =============================================================================
# Test FileManifest
# =============================================================================

class TestFileManifest:
    """Tests for FileManifest dataclass."""

    def test_to_json_serialization(self):
        """Test to_json() serializes manifest to JSON."""
        manifest = FileManifest(
            files={"index.html": "abc123", "style.css": "def456"},
            last_deployed="2024-01-15T12:00:00"
        )

        json_str = manifest.to_json()
        data = json.loads(json_str)

        assert data["files"]["index.html"] == "abc123"
        assert data["files"]["style.css"] == "def456"
        assert data["last_deployed"] == "2024-01-15T12:00:00"

    def test_from_json_deserialization(self):
        """Test from_json() deserializes JSON to manifest."""
        json_str = json.dumps({
            "files": {"test.html": "hash123"},
            "last_deployed": "2024-01-15T12:00:00"
        })

        manifest = FileManifest.from_json(json_str)

        assert manifest.files["test.html"] == "hash123"
        assert manifest.last_deployed == "2024-01-15T12:00:00"

    def test_from_json_invalid_json(self):
        """Test from_json() returns empty manifest on invalid JSON."""
        manifest = FileManifest.from_json("invalid json {")

        assert manifest.files == {}
        assert manifest.last_deployed is None

    def test_from_json_missing_keys(self):
        """Test from_json() handles missing keys gracefully."""
        manifest = FileManifest.from_json("{}")

        assert manifest.files == {}
        assert manifest.last_deployed is None

    def test_empty_manifest(self):
        """Test empty manifest initialization."""
        manifest = FileManifest()

        assert manifest.files == {}
        assert manifest.last_deployed is None


# =============================================================================
# Test BlogDeployer
# =============================================================================

class TestBlogDeployer:
    """Tests for BlogDeployer class."""

    @pytest.fixture
    def deployer(self, tmp_path, mock_settings):
        """Create a BlogDeployer with temp directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        return BlogDeployer(source_dir=source_dir, remote_dir="/public_html")

    def test_hash_file_consistency(self, deployer, tmp_path):
        """Test _hash_file produces consistent MD5 hashes."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")

        hash1 = deployer._hash_file(test_file)
        hash2 = deployer._hash_file(test_file)

        assert hash1 == hash2
        assert hash1 == hashlib.md5(b"test content").hexdigest()

    def test_hash_file_different_content(self, deployer, tmp_path):
        """Test _hash_file produces different hashes for different content."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")

        hash1 = deployer._hash_file(file1)
        hash2 = deployer._hash_file(file2)

        assert hash1 != hash2

    def test_calculate_changes_new_files(self, deployer):
        """Test _calculate_changes detects new files."""
        deployer._local_manifest = FileManifest(
            files={"new.html": "hash1", "existing.html": "hash2"}
        )
        deployer._remote_manifest = FileManifest(
            files={"existing.html": "hash2"}
        )

        to_upload, to_delete = deployer._calculate_changes()

        assert "new.html" in to_upload
        assert "existing.html" not in to_upload
        assert len(to_delete) == 0

    def test_calculate_changes_updated_files(self, deployer):
        """Test _calculate_changes detects updated files."""
        deployer._local_manifest = FileManifest(
            files={"file.html": "newhash"}
        )
        deployer._remote_manifest = FileManifest(
            files={"file.html": "oldhash"}
        )

        to_upload, to_delete = deployer._calculate_changes()

        assert "file.html" in to_upload

    def test_calculate_changes_deleted_files(self, deployer):
        """Test _calculate_changes detects deleted files."""
        deployer._local_manifest = FileManifest(
            files={"kept.html": "hash1"}
        )
        deployer._remote_manifest = FileManifest(
            files={"kept.html": "hash1", "deleted.html": "hash2"}
        )

        to_upload, to_delete = deployer._calculate_changes()

        assert "deleted.html" in to_delete
        assert "kept.html" not in to_upload

    def test_calculate_changes_ignores_manifest(self, deployer):
        """Test _calculate_changes doesn't delete manifest file."""
        deployer._local_manifest = FileManifest(files={})
        deployer._remote_manifest = FileManifest(
            files={".deploy-manifest.json": "hash"}
        )

        to_upload, to_delete = deployer._calculate_changes()

        assert ".deploy-manifest.json" not in to_delete

    def test_validate_config_success(self, deployer, mock_settings):
        """Test _validate_config returns True with valid config."""
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"

        deployer.settings = mock_settings
        assert deployer._validate_config() is True

    def test_validate_config_missing_host(self, deployer, mock_settings):
        """Test _validate_config returns False with missing host."""
        mock_settings.ftp_host = None
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"

        deployer.settings = mock_settings
        assert deployer._validate_config() is False

    def test_validate_config_missing_credentials(self, deployer, mock_settings):
        """Test _validate_config returns False with missing credentials."""
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_username = None
        mock_settings.ftp_password = None

        deployer.settings = mock_settings
        assert deployer._validate_config() is False

    def test_build_local_manifest(self, deployer, tmp_path):
        """Test _build_local_manifest creates manifest from directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create test files
        (source_dir / "index.html").write_bytes(b"index content")
        (source_dir / "style.css").write_bytes(b"css content")

        deployer.source_dir = source_dir
        manifest = deployer._build_local_manifest()

        assert "index.html" in manifest.files
        assert "style.css" in manifest.files
        assert manifest.last_deployed is not None

    def test_build_local_manifest_nested_files(self, deployer, tmp_path):
        """Test _build_local_manifest includes nested files."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        subdir = source_dir / "posts"
        subdir.mkdir()
        (subdir / "post1.html").write_bytes(b"post content")

        deployer.source_dir = source_dir
        manifest = deployer._build_local_manifest()

        assert "posts/post1.html" in manifest.files or "posts\\post1.html" in manifest.files

    @patch('ftplib.FTP')
    def test_ftp_connect_success(self, mock_ftp_class, deployer, mock_settings):
        """Test _connect establishes FTP connection."""
        mock_ftp = Mock()
        mock_ftp_class.return_value = mock_ftp

        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"

        deployer.settings = mock_settings
        deployer._connect()

        mock_ftp.connect.assert_called_once_with(
            host="ftp.example.com",
            port=21,
            timeout=30
        )
        mock_ftp.login.assert_called_once_with(user="user", passwd="pass")
        mock_ftp.voidcmd.assert_called_once_with("TYPE I")

    @patch('ftplib.FTP')
    def test_ftp_disconnect(self, mock_ftp_class, deployer):
        """Test _disconnect closes FTP connection."""
        mock_ftp = Mock()
        deployer._ftp = mock_ftp

        deployer._disconnect()

        mock_ftp.quit.assert_called_once()
        assert deployer._ftp is None

    @patch('ftplib.FTP')
    def test_ftp_disconnect_handles_exception(self, mock_ftp_class, deployer):
        """Test _disconnect handles quit() exception gracefully."""
        mock_ftp = Mock()
        mock_ftp.quit.side_effect = Exception("Connection error")
        mock_ftp.close.return_value = None

        deployer._ftp = mock_ftp
        deployer._disconnect()

        mock_ftp.close.assert_called_once()
        assert deployer._ftp is None

    @patch('ftplib.FTP')
    def test_load_remote_manifest_success(self, mock_ftp_class, deployer):
        """Test _load_remote_manifest loads from FTP."""
        mock_ftp = Mock()

        manifest_json = json.dumps({
            "files": {"test.html": "hash123"},
            "last_deployed": "2024-01-15T12:00:00"
        })

        def mock_retrlines(cmd, callback):
            for line in manifest_json.split('\n'):
                callback(line)

        mock_ftp.retrlines = mock_retrlines
        deployer._ftp = mock_ftp

        manifest = deployer._load_remote_manifest()

        assert manifest.files["test.html"] == "hash123"

    @patch('ftplib.FTP')
    def test_load_remote_manifest_not_found(self, mock_ftp_class, deployer):
        """Test _load_remote_manifest returns empty on file not found."""
        mock_ftp = Mock()
        mock_ftp.retrlines.side_effect = ftplib.error_perm("550 File not found")

        deployer._ftp = mock_ftp
        manifest = deployer._load_remote_manifest()

        assert manifest.files == {}
        assert manifest.last_deployed is None

    @patch('ftplib.FTP')
    def test_save_remote_manifest(self, mock_ftp_class, deployer):
        """Test _save_remote_manifest uploads manifest to FTP."""
        mock_ftp = Mock()
        deployer._ftp = mock_ftp
        deployer._local_manifest = FileManifest(
            files={"test.html": "hash123"},
            last_deployed="2024-01-15T12:00:00"
        )

        deployer._save_remote_manifest()

        # Verify storbinary was called
        assert mock_ftp.storbinary.called
        call_args = mock_ftp.storbinary.call_args
        assert "/public_html/.deploy-manifest.json" in call_args[0][0]

    def test_deploy_missing_source_directory(self, deployer):
        """Test deploy returns error when source directory doesn't exist."""
        deployer.source_dir = Path("/nonexistent/path")

        with patch.object(deployer, '_validate_config', return_value=True):
            result = deployer.deploy()

        assert result.success is False
        assert any("does not exist" in err for err in result.errors)

    def test_deploy_invalid_config(self, deployer):
        """Test deploy returns error when config is invalid."""
        with patch.object(deployer, '_validate_config', return_value=False):
            result = deployer.deploy()

        assert result.success is False
        assert any("configuration" in err.lower() for err in result.errors)

    def test_deploy_dry_run(self, deployer, tmp_path):
        """Test deploy with dry_run doesn't actually upload."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.html").write_bytes(b"content")

        deployer.source_dir = source_dir

        with patch.object(deployer, '_validate_config', return_value=True):
            with patch.object(deployer, '_connect') as mock_connect:
                result = deployer.deploy(dry_run=True)

        # Should not connect in dry run
        mock_connect.assert_not_called()
        assert result.completed_at is not None


# =============================================================================
# Test SearchIndexBuilder
# =============================================================================

class TestSearchIndexBuilder:
    """Tests for SearchIndexBuilder class."""

    @pytest.fixture
    def builder(self):
        """Create a SearchIndexBuilder instance."""
        return SearchIndexBuilder()

    def test_extract_excerpt_short_content(self, builder):
        """Test _extract_excerpt with content shorter than max_length."""
        content = "Short content here"
        excerpt = builder._extract_excerpt(content, max_length=150)
        assert excerpt == "Short content here"

    def test_extract_excerpt_long_content(self, builder):
        """Test _extract_excerpt truncates long content."""
        content = "This is a very long piece of content " * 10
        excerpt = builder._extract_excerpt(content, max_length=50)

        assert len(excerpt) <= 54  # 50 + "..."
        assert excerpt.endswith("...")

    def test_extract_excerpt_word_boundary(self, builder):
        """Test _extract_excerpt truncates at word boundary."""
        content = "This is a test of word boundary handling"
        excerpt = builder._extract_excerpt(content, max_length=20)

        # Should not cut in middle of word
        assert not excerpt[:-3].endswith(" t")  # Shouldn't end with partial "test"
        assert excerpt.endswith("...")

    def test_extract_excerpt_empty_content(self, builder):
        """Test _extract_excerpt with empty content."""
        assert builder._extract_excerpt("") == ""
        assert builder._extract_excerpt(None) == ""

    def test_extract_excerpt_whitespace_normalization(self, builder):
        """Test _extract_excerpt normalizes whitespace."""
        content = "Too    many   \n\n  spaces"
        excerpt = builder._extract_excerpt(content)
        assert excerpt == "Too many spaces"

    def test_create_entry(self, builder, post_factory):
        """Test _create_entry creates correct entry structure."""
        post = post_factory(
            slug="test-post",
            title="Test Post Title",
            content_text="This is test content for the post.",
            tags=["python", "testing"]
        )

        entry = builder._create_entry(post)

        assert entry["title"] == "Test Post Title"
        assert entry["url"] == "/posts/test-post/"
        assert "test content" in entry["excerpt"]
        assert entry["tags"] == ["python", "testing"]

    def test_create_entry_no_tags(self, builder, post_factory):
        """Test _create_entry with post that has no tags."""
        post = post_factory(
            slug="test-post",
            title="Test Post",
            content_text="Content",
            tags=None
        )

        entry = builder._create_entry(post)
        assert entry["tags"] == []

    def test_create_entry_uses_markdown_fallback(self, builder, post_factory):
        """Test _create_entry falls back to content_markdown if no content_text."""
        post = post_factory(
            slug="test-post",
            title="Test Post",
            content_text=None,
            content_markdown="# Markdown content here"
        )

        entry = builder._create_entry(post)
        assert "Markdown content" in entry["excerpt"]

    def test_build_index(self, builder, post_factory):
        """Test build_index creates entries for all posts."""
        posts = [
            post_factory(slug=f"post-{i}", title=f"Post {i}")
            for i in range(5)
        ]

        index_data = builder.build_index(posts)

        assert len(index_data) == 5
        assert all("title" in entry for entry in index_data)
        assert all("url" in entry for entry in index_data)

    def test_build_index_empty_list(self, builder):
        """Test build_index with empty post list."""
        index_data = builder.build_index([])
        assert index_data == []

    def test_build_index_stores_internally(self, builder, post_factory):
        """Test build_index stores data in instance variable."""
        posts = [post_factory(slug="post-1")]

        builder.build_index(posts)

        assert len(builder.index_data) == 1
        assert builder.index_data[0]["url"] == "/posts/post-1/"

    def test_generate_json(self, builder, post_factory, tmp_path):
        """Test generate_json writes JSON file."""
        posts = [
            post_factory(slug="post-1", title="First Post"),
            post_factory(slug="post-2", title="Second Post"),
        ]

        builder.build_index(posts)

        output_path = tmp_path / "search-index.json"
        builder.generate_json(output_path)

        assert output_path.exists()

        with output_path.open('r') as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["title"] == "First Post"

    def test_generate_json_creates_parent_directory(self, builder, post_factory, tmp_path):
        """Test generate_json creates parent directories if needed."""
        posts = [post_factory(slug="test")]
        builder.build_index(posts)

        output_path = tmp_path / "nested" / "dir" / "search-index.json"
        builder.generate_json(output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_generate_json_empty_index(self, builder, tmp_path):
        """Test generate_json with empty index."""
        output_path = tmp_path / "search-index.json"
        builder.generate_json(output_path)

        assert output_path.exists()

        with output_path.open('r') as f:
            data = json.load(f)

        assert data == []

    def test_generate_json_utf8_encoding(self, builder, post_factory, tmp_path):
        """Test generate_json handles UTF-8 characters correctly."""
        post = post_factory(
            slug="unicode-test",
            title="Test with émojis 🎉 and ümläüts",
            content_text="Content with café and naïve"
        )

        builder.build_index([post])

        output_path = tmp_path / "search-index.json"
        builder.generate_json(output_path)

        with output_path.open('r', encoding='utf-8') as f:
            data = json.load(f)

        assert "émojis" in data[0]["title"]
        assert "café" in data[0]["excerpt"]
