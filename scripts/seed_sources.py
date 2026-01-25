"""
Patient Safety Monitor - Source Seeding Script

Seeds the database with data source configurations from sources.yaml.
This script is typically run after migrations during initial setup.

Usage:
    python -m scripts.seed_sources
    
    # Or via Docker Compose
    docker-compose run --rm migrate
"""

import logging
import sys
from pathlib import Path

import yaml

from config.settings import get_settings
from config.logging import setup_logging, get_logger
from database.connection import get_session, init_database
from database.repository import SourceRepository


logger = get_logger(__name__)


def load_sources_config() -> dict:
    """
    Load sources configuration from YAML file.
    
    Returns:
        Parsed sources configuration dictionary
        
    Raises:
        FileNotFoundError: If sources.yaml doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    config_path = Path("config/sources.yaml")
    
    if not config_path.exists():
        raise FileNotFoundError(f"Sources config not found: {config_path}")
    
    logger.info(f"Loading sources from {config_path}")
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    return config


def seed_sources(dry_run: bool = False) -> tuple[int, int, int]:
    """
    Seed data sources from configuration file.
    
    Args:
        dry_run: If True, don't commit changes to database
        
    Returns:
        Tuple of (created_count, updated_count, skipped_count)
    """
    config = load_sources_config()
    sources = config.get("sources", [])
    
    if not sources:
        logger.warning("No sources defined in configuration")
        return 0, 0, 0
    
    created = 0
    updated = 0
    skipped = 0
    
    with get_session() as session:
        repo = SourceRepository(session)
        
        for source_config in sources:
            code = source_config.get("code")
            
            if not code:
                logger.warning("Source missing 'code' field, skipping")
                skipped += 1
                continue
            
            try:
                # Check if source already exists
                existing = repo.get_by_code(code)
                
                if existing:
                    # Update existing source
                    logger.info(f"Updating existing source: {code}")
                    
                    existing.name = source_config.get("name", existing.name)
                    existing.country = source_config.get("country", existing.country)
                    existing.region = source_config.get("region")
                    existing.base_url = source_config.get("base_url", existing.base_url)
                    existing.scraper_class = source_config.get("scraper_class", existing.scraper_class)
                    existing.schedule_cron = source_config.get("schedule", existing.schedule_cron)
                    existing.is_active = source_config.get("is_active", existing.is_active)
                    existing.config_json = source_config.get("config", existing.config_json)
                    
                    updated += 1
                else:
                    # Create new source
                    logger.info(f"Creating new source: {code}")
                    
                    repo.create(
                        code=code,
                        name=source_config.get("name", code),
                        country=source_config.get("country", "XX"),
                        region=source_config.get("region"),
                        base_url=source_config.get("base_url", ""),
                        scraper_class=source_config.get("scraper_class", ""),
                        schedule_cron=source_config.get("schedule", "0 6 * * *"),
                        is_active=source_config.get("is_active", False),
                        config_json=source_config.get("config"),
                    )
                    
                    created += 1
                    
            except Exception as e:
                logger.error(f"Failed to process source {code}: {e}")
                skipped += 1
        
        if not dry_run:
            session.commit()
            logger.info("Changes committed to database")
        else:
            session.rollback()
            logger.info("Dry run - changes rolled back")
    
    return created, updated, skipped


def main() -> int:
    """
    Main entry point for source seeding script.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Seed database with source configurations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Source Seeding")
    logger.info("=" * 60)
    
    # Initialize database
    if not init_database():
        logger.error("Database initialization failed")
        return 1
    
    try:
        created, updated, skipped = seed_sources(dry_run=args.dry_run)
        
        logger.info("-" * 40)
        logger.info(f"Seeding complete:")
        logger.info(f"  Created: {created}")
        logger.info(f"  Updated: {updated}")
        logger.info(f"  Skipped: {skipped}")
        
        if args.dry_run:
            logger.info("  (DRY RUN - no changes committed)")
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Seeding failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
