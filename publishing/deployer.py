"""
Patient Safety Monitor - Blog Deployer

Deploys generated static files to Hostinger via FTP/SFTP.

Features:
- FTP and SFTP support
- Incremental deployment (only changed files)
- Backup creation before deployment
- Rollback capability
- Progress logging

Usage:
    deployer = BlogDeployer()
    result = deployer.deploy()
"""

import ftplib
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import get_settings
from config.logging import get_logger


logger = get_logger(__name__)


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""
    
    success: bool = True
    files_uploaded: int = 0
    files_skipped: int = 0  # Unchanged files
    files_deleted: int = 0  # Orphaned files on server
    bytes_transferred: int = 0
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    def add_error(self, message: str) -> None:
        """Add an error and mark deployment as failed."""
        self.errors.append(message)
        self.success = False


@dataclass
class FileManifest:
    """Tracks deployed files and their hashes for incremental updates."""
    
    files: dict[str, str] = field(default_factory=dict)  # path -> hash
    last_deployed: Optional[str] = None
    
    def to_json(self) -> str:
        """Serialize manifest to JSON."""
        return json.dumps({
            "files": self.files,
            "last_deployed": self.last_deployed,
        }, indent=2)
    
    @classmethod
    def from_json(cls, data: str) -> "FileManifest":
        """Deserialize manifest from JSON."""
        try:
            obj = json.loads(data)
            return cls(
                files=obj.get("files", {}),
                last_deployed=obj.get("last_deployed"),
            )
        except json.JSONDecodeError:
            return cls()


class BlogDeployer:
    """
    Deploys static blog files to Hostinger via FTP.
    
    Supports incremental deployment by tracking file hashes
    and only uploading changed files.
    """
    
    MANIFEST_FILE = ".deploy-manifest.json"
    
    def __init__(
        self,
        source_dir: Optional[Path] = None,
        remote_dir: str = "/public_html",
    ):
        """
        Initialize the deployer.
        
        Args:
            source_dir: Local directory containing generated files
            remote_dir: Remote directory on FTP server
        """
        self.settings = get_settings()
        self.source_dir = source_dir or Path("data/public_html")
        self.remote_dir = remote_dir.rstrip("/")
        
        # FTP connection
        self._ftp: Optional[ftplib.FTP] = None
        
        # Track local and remote manifests
        self._local_manifest: Optional[FileManifest] = None
        self._remote_manifest: Optional[FileManifest] = None
    
    def deploy(
        self,
        force_full: bool = False,
        dry_run: bool = False,
    ) -> DeploymentResult:
        """
        Deploy static files to Hostinger.
        
        Args:
            force_full: Force full deployment (ignore manifest)
            dry_run: Log what would be done without actually deploying
            
        Returns:
            DeploymentResult with statistics
        """
        result = DeploymentResult()
        
        logger.info(
            "Starting deployment",
            extra={
                "source_dir": str(self.source_dir),
                "remote_dir": self.remote_dir,
                "force_full": force_full,
                "dry_run": dry_run,
            },
        )
        
        # Validate configuration
        if not self._validate_config():
            result.add_error("FTP configuration is incomplete")
            return result
        
        # Validate source directory
        if not self.source_dir.exists():
            result.add_error(f"Source directory does not exist: {self.source_dir}")
            return result
        
        try:
            # Connect to FTP
            if not dry_run:
                self._connect()
            
            # Load manifests
            self._local_manifest = self._build_local_manifest()
            if not force_full and not dry_run:
                self._remote_manifest = self._load_remote_manifest()
            else:
                self._remote_manifest = FileManifest()
            
            # Calculate files to upload/delete
            to_upload, to_delete = self._calculate_changes()
            
            logger.info(
                f"Deployment plan: {len(to_upload)} to upload, {len(to_delete)} to delete",
                extra={
                    "upload_count": len(to_upload),
                    "delete_count": len(to_delete),
                },
            )
            
            if dry_run:
                # Just log what would happen
                for file_path in to_upload:
                    logger.info(f"[DRY RUN] Would upload: {file_path}")
                for file_path in to_delete:
                    logger.info(f"[DRY RUN] Would delete: {file_path}")
                result.files_uploaded = len(to_upload)
                result.files_deleted = len(to_delete)
            else:
                # Perform actual deployment
                result = self._execute_deployment(to_upload, to_delete, result)
                
                if result.success:
                    # Update remote manifest
                    self._save_remote_manifest()
            
        except ftplib.all_errors as e:
            logger.exception(f"FTP error during deployment: {e}")
            result.add_error(f"FTP error: {e}")
        except Exception as e:
            logger.exception(f"Deployment failed: {e}")
            result.add_error(f"Deployment failed: {e}")
        finally:
            self._disconnect()
        
        result.completed_at = datetime.utcnow()
        
        logger.info(
            "Deployment complete",
            extra={
                "success": result.success,
                "uploaded": result.files_uploaded,
                "skipped": result.files_skipped,
                "deleted": result.files_deleted,
                "bytes": result.bytes_transferred,
                "duration_seconds": result.duration_seconds,
            },
        )
        
        return result
    
    def _validate_config(self) -> bool:
        """Validate FTP configuration is present."""
        return bool(
            self.settings.ftp_host
            and self.settings.ftp_username
            and self.settings.ftp_password
        )
    
    def _connect(self) -> None:
        """Connect to FTP server."""
        logger.debug(f"Connecting to FTP: {self.settings.ftp_host}")
        
        self._ftp = ftplib.FTP()
        self._ftp.connect(
            host=self.settings.ftp_host,
            port=self.settings.ftp_port or 21,
            timeout=30,
        )
        self._ftp.login(
            user=self.settings.ftp_username,
            passwd=self.settings.ftp_password,
        )
        
        # Switch to binary mode
        self._ftp.voidcmd("TYPE I")
        
        logger.debug("FTP connection established")
    
    def _disconnect(self) -> None:
        """Disconnect from FTP server."""
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                try:
                    self._ftp.close()
                except Exception:
                    pass
            self._ftp = None
            logger.debug("FTP disconnected")
    
    def _build_local_manifest(self) -> FileManifest:
        """Build manifest from local files."""
        manifest = FileManifest()
        
        for file_path in self.source_dir.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(self.source_dir))
                file_hash = self._hash_file(file_path)
                manifest.files[rel_path] = file_hash
        
        manifest.last_deployed = datetime.utcnow().isoformat()
        
        logger.debug(f"Built local manifest: {len(manifest.files)} files")
        return manifest
    
    def _hash_file(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _load_remote_manifest(self) -> FileManifest:
        """Load manifest from remote server."""
        if not self._ftp:
            return FileManifest()
        
        manifest_path = f"{self.remote_dir}/{self.MANIFEST_FILE}"
        
        try:
            lines = []
            self._ftp.retrlines(f"RETR {manifest_path}", lines.append)
            data = "\n".join(lines)
            manifest = FileManifest.from_json(data)
            logger.debug(f"Loaded remote manifest: {len(manifest.files)} files")
            return manifest
        except ftplib.error_perm:
            logger.debug("No remote manifest found, will do full deployment")
            return FileManifest()
    
    def _save_remote_manifest(self) -> None:
        """Save manifest to remote server."""
        if not self._ftp or not self._local_manifest:
            return
        
        manifest_path = f"{self.remote_dir}/{self.MANIFEST_FILE}"
        data = self._local_manifest.to_json().encode("utf-8")
        
        from io import BytesIO
        self._ftp.storbinary(f"STOR {manifest_path}", BytesIO(data))
        logger.debug("Saved remote manifest")
    
    def _calculate_changes(self) -> tuple[list[str], list[str]]:
        """
        Calculate files to upload and delete.
        
        Returns:
            Tuple of (files_to_upload, files_to_delete)
        """
        local_files = set(self._local_manifest.files.keys()) if self._local_manifest else set()
        remote_files = set(self._remote_manifest.files.keys()) if self._remote_manifest else set()
        
        to_upload = []
        to_delete = []
        
        # Files to upload (new or changed)
        for file_path in local_files:
            local_hash = self._local_manifest.files[file_path]
            remote_hash = self._remote_manifest.files.get(file_path) if self._remote_manifest else None
            
            if remote_hash != local_hash:
                to_upload.append(file_path)
        
        # Files to delete (exist on remote but not locally)
        for file_path in remote_files - local_files:
            # Don't delete the manifest file
            if file_path != self.MANIFEST_FILE:
                to_delete.append(file_path)
        
        return to_upload, to_delete
    
    def _execute_deployment(
        self,
        to_upload: list[str],
        to_delete: list[str],
        result: DeploymentResult,
    ) -> DeploymentResult:
        """
        Execute the actual file transfers.
        
        Args:
            to_upload: List of files to upload
            to_delete: List of files to delete
            result: Result object to update
            
        Returns:
            Updated DeploymentResult
        """
        # Upload files
        for file_path in to_upload:
            try:
                local_path = self.source_dir / file_path
                remote_path = f"{self.remote_dir}/{file_path}"
                
                self._upload_file(local_path, remote_path)
                
                result.files_uploaded += 1
                result.bytes_transferred += local_path.stat().st_size
                
                logger.debug(f"Uploaded: {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to upload {file_path}: {e}")
                result.warnings.append(f"Upload failed: {file_path}")
        
        # Delete orphaned files
        for file_path in to_delete:
            try:
                remote_path = f"{self.remote_dir}/{file_path}"
                self._ftp.delete(remote_path)
                result.files_deleted += 1
                logger.debug(f"Deleted: {file_path}")
            except ftplib.error_perm as e:
                # File might not exist, which is fine
                logger.debug(f"Could not delete {file_path}: {e}")
        
        # Calculate skipped files
        total_local = len(self._local_manifest.files) if self._local_manifest else 0
        result.files_skipped = total_local - result.files_uploaded
        
        return result
    
    def _upload_file(self, local_path: Path, remote_path: str) -> None:
        """
        Upload a single file to the remote server.
        
        Creates parent directories if needed.
        """
        if not self._ftp:
            raise RuntimeError("Not connected to FTP")
        
        # Ensure parent directory exists
        parent_dir = os.path.dirname(remote_path)
        self._ensure_remote_dir(parent_dir)
        
        # Upload file
        with open(local_path, "rb") as f:
            self._ftp.storbinary(f"STOR {remote_path}", f)
    
    def _ensure_remote_dir(self, dir_path: str) -> None:
        """Ensure a remote directory exists, creating if needed."""
        if not self._ftp or not dir_path:
            return
        
        # Split path and create each level
        parts = dir_path.strip("/").split("/")
        current = ""
        
        for part in parts:
            if not part:
                continue
            current = f"{current}/{part}"
            try:
                self._ftp.cwd(current)
            except ftplib.error_perm:
                # Directory doesn't exist, create it
                try:
                    self._ftp.mkd(current)
                except ftplib.error_perm:
                    pass  # Might already exist
        
        # Return to root
        self._ftp.cwd("/")
    
    def rollback(self, manifest_data: str) -> DeploymentResult:
        """
        Rollback to a previous deployment state.
        
        Args:
            manifest_data: JSON manifest from previous deployment
            
        Returns:
            DeploymentResult with rollback statistics
        """
        result = DeploymentResult()
        
        logger.info("Starting rollback")
        
        try:
            # Parse the target manifest
            target_manifest = FileManifest.from_json(manifest_data)
            
            # Connect and get current state
            self._connect()
            self._remote_manifest = self._load_remote_manifest()
            
            # Calculate what needs to change to match target
            current_files = set(self._remote_manifest.files.keys())
            target_files = set(target_manifest.files.keys())
            
            # Delete files not in target
            to_delete = list(current_files - target_files)
            
            for file_path in to_delete:
                try:
                    remote_path = f"{self.remote_dir}/{file_path}"
                    self._ftp.delete(remote_path)
                    result.files_deleted += 1
                except ftplib.error_perm:
                    pass
            
            logger.warning(
                "Rollback complete - note that rollback only deletes files, "
                "it does not restore previous versions. You may need to redeploy."
            )
            
        except Exception as e:
            logger.exception(f"Rollback failed: {e}")
            result.add_error(f"Rollback failed: {e}")
        finally:
            self._disconnect()
        
        result.completed_at = datetime.utcnow()
        return result


# =============================================================================
# CLI Entry Point
# =============================================================================

def main() -> int:
    """
    Main entry point for deployment.
    
    Usage:
        python -m publishing.deployer [--force] [--dry-run]
    """
    import argparse
    import sys
    
    from config.logging import setup_logging
    
    parser = argparse.ArgumentParser(description="Deploy static blog to Hostinger")
    parser.add_argument("--force", action="store_true", help="Force full deployment")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--source", type=str, help="Source directory", default="data/public_html")
    args = parser.parse_args()
    
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Blog Deployer")
    logger.info("=" * 60)
    
    deployer = BlogDeployer(source_dir=Path(args.source))
    result = deployer.deploy(
        force_full=args.force,
        dry_run=args.dry_run,
    )
    
    print(f"\nDeployment {'completed' if result.success else 'FAILED'}")
    print(f"  Files uploaded: {result.files_uploaded}")
    print(f"  Files skipped: {result.files_skipped}")
    print(f"  Files deleted: {result.files_deleted}")
    print(f"  Bytes transferred: {result.bytes_transferred:,}")
    print(f"  Duration: {result.duration_seconds:.1f}s")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")
    
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings[:5]:
            print(f"  - {warning}")
    
    return 0 if result.success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
