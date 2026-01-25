"""
Patient Safety Monitor - Search Index Builder

Generates a JSON search index for client-side search functionality.

The search index contains:
- Post title
- Post URL
- Excerpt (first 150 chars)
- Tags

Usage:
    from publishing.search_index import SearchIndexBuilder

    builder = SearchIndexBuilder()
    index = builder.build_index(posts)
    builder.generate_json(output_path)
"""

import json
import logging
from pathlib import Path
from typing import Any

from config.logging import get_logger
from database.models import Post


logger = get_logger(__name__)


class SearchIndexBuilder:
    """
    Builds a JSON search index for client-side search.

    The search index contains minimal information for each post:
    - title: Post title
    - url: Relative URL to the post
    - excerpt: First 150 characters of content
    - tags: List of tags
    """

    def __init__(self):
        """Initialize the search index builder."""
        self.index_data: list[dict[str, Any]] = []

    def build_index(self, posts: list[Post]) -> list[dict[str, Any]]:
        """
        Build search index from list of posts.

        Args:
            posts: List of Post objects to index

        Returns:
            List of search index entries
        """
        self.index_data = []

        for post in posts:
            entry = self._create_entry(post)
            self.index_data.append(entry)

        logger.info(f"Built search index with {len(self.index_data)} entries")

        return self.index_data

    def generate_json(self, output_path: Path) -> None:
        """
        Write the search index to a JSON file.

        Args:
            output_path: Path to write the search-index.json file
        """
        if not self.index_data:
            logger.warning("Search index is empty, generating empty file")

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON file
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(self.index_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Search index written to {output_path}")

    def _create_entry(self, post: Post) -> dict[str, Any]:
        """
        Create a search index entry for a single post.

        Args:
            post: Post object to create entry for

        Returns:
            Dictionary with search index data
        """
        # Get excerpt from content_text if available, otherwise from content_markdown
        content = post.content_text or post.content_markdown or ""
        excerpt = self._extract_excerpt(content)

        # Build URL from slug
        url = f"/posts/{post.slug}/"

        # Get tags or empty list
        tags = post.tags if post.tags else []

        return {
            "title": post.title,
            "url": url,
            "excerpt": excerpt,
            "tags": tags,
        }

    def _extract_excerpt(self, content: str, max_length: int = 150) -> str:
        """
        Extract a short excerpt from content.

        Args:
            content: Full content text
            max_length: Maximum excerpt length in characters

        Returns:
            Truncated excerpt with ellipsis if needed
        """
        if not content:
            return ""

        # Remove extra whitespace
        clean_content = " ".join(content.split())

        # Truncate to max length
        if len(clean_content) <= max_length:
            return clean_content

        # Truncate at word boundary
        truncated = clean_content[:max_length]
        last_space = truncated.rfind(' ')

        if last_space > 0:
            truncated = truncated[:last_space]

        return truncated + "..."


# =============================================================================
# CLI Entry Point
# =============================================================================

def main() -> int:
    """
    Command-line entry point for search index generation.

    Usage:
        python -m publishing.search_index
    """
    from config.logging import setup_logging
    from database.connection import init_database, get_session
    from database.repository import PostRepository
    from database.models import PostStatus

    setup_logging()
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Search Index Generator")
    logger.info("=" * 60)

    if not init_database():
        logger.error("Database initialization failed")
        return 1

    # Load published posts
    with get_session() as session:
        repo = PostRepository(session)
        posts = repo.get_by_status(PostStatus.PUBLISHED)

        logger.info(f"Found {len(posts)} published posts")

        # Build index
        builder = SearchIndexBuilder()
        builder.build_index(posts)

        # Write to file
        output_path = Path("data/public_html/search-index.json")
        builder.generate_json(output_path)

        print(f"\nSearch Index Generated:")
        print(f"  Posts indexed: {len(posts)}")
        print(f"  Output: {output_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
