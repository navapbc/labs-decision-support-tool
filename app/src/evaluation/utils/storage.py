"""Shared storage utilities for QA pairs and evaluation results."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..qa_generation.models import QAPair


class QAPairStorage:
    """Handles storage and versioning of QA pairs."""

    def __init__(self, base_path: Path):
        """Initialize storage with base path.

        Args:
            base_path: Base directory for QA pairs storage
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_qa_pairs(
        self,
        qa_pairs: List[QAPair],
        version_id: str,
        git_commit: Optional[str] = None,
    ) -> Path:
        """Save QA pairs with version information.

        Args:
            qa_pairs: List of QA pairs to save
            version_id: ID for this QA generation run
            git_commit: Git commit for tracking

        Returns:
            Path to saved QA pairs CSV
        """
        # Create versioned directory
        version_dir = self.base_path / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata = {
            "version_id": version_id,
            "timestamp": datetime.utcnow().isoformat(),
            "llm_model": qa_pairs[0].version.llm_model if qa_pairs else None,
            "total_pairs": len(qa_pairs),
            "datasets": list(set(p.document_source for p in qa_pairs)),
            "git_commit": git_commit,
        }

        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Save QA pairs CSV
        csv_path = version_dir / "qa_pairs.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "question",
                    "answer",
                    "document_name",
                    "document_source",
                    "source",
                    "document_id",
                    "chunk_id",
                    "content_hash",
                    "dataset",
                    "created_at",
                    "version_id",
                    "version_timestamp",
                    "version_llm_model",
                ],
            )
            writer.writeheader()
            for pair in qa_pairs:
                row = pair.dict()
                # Flatten version info into row
                row["version_id"] = pair.version.version_id
                row["version_timestamp"] = pair.version.timestamp
                row["version_llm_model"] = pair.version.llm_model
                # Add source field (e.g. "imagine_la", "edd")
                row["source"] = pair.document_source
                # Remove nested version dict
                del row["version"]
                writer.writerow(row)

        # Update latest symlink with robust handling
        latest_link = self.base_path / "latest"
        try:
            # Create temp symlink with unique name
            temp_link = self.base_path / f"latest.{datetime.now().timestamp()}"
            temp_link.symlink_to(version_dir, target_is_directory=True)

            # Atomic rename of temp symlink to latest
            # This avoids race conditions between processes
            temp_link.rename(latest_link)

        except FileExistsError:
            # If latest exists, verify it points to correct dir
            if latest_link.exists():
                try:
                    if latest_link.resolve() != version_dir:
                        latest_link.unlink()
                        latest_link.symlink_to(version_dir, target_is_directory=True)
                except (OSError, RuntimeError):
                    # Handle edge cases (broken symlink, permission issues, etc)
                    if latest_link.exists():
                        latest_link.unlink()
                    latest_link.symlink_to(version_dir, target_is_directory=True)

        return csv_path

    def get_latest_version(self) -> str:
        """Get the version ID of the latest QA pairs.

        Returns:
            Version ID string

        Raises:
            ValueError if no QA pairs found
        """
        latest_link = self.base_path / "latest"

        # First try to find latest version by timestamp
        versions = sorted(
            [d for d in self.base_path.iterdir() if d.is_dir() and d.name != "latest"],
            key=lambda d: d.name,
            reverse=True,
        )
        if not versions:
            raise ValueError("No QA pairs found - run generation first")

        latest_version = versions[0]

        # Handle symlink creation/update
        try:
            # If symlink exists but points to wrong place, remove it
            if latest_link.exists():
                try:
                    if latest_link.resolve() != latest_version:
                        latest_link.unlink()
                        latest_link.symlink_to(latest_version, target_is_directory=True)
                except (OSError, RuntimeError):
                    # Handle edge cases (broken symlink, permission issues, etc)
                    if latest_link.exists():
                        latest_link.unlink()
                    latest_link.symlink_to(latest_version, target_is_directory=True)
            else:
                # Create new symlink
                latest_link.symlink_to(latest_version, target_is_directory=True)

        except FileExistsError:
            # Race condition: another process created the symlink
            # Just verify it points to our version
            try:
                if latest_link.resolve() != latest_version:
                    latest_link.unlink()
                    latest_link.symlink_to(latest_version, target_is_directory=True)
            except (OSError, RuntimeError):
                if latest_link.exists():
                    latest_link.unlink()
                latest_link.symlink_to(latest_version, target_is_directory=True)

        return latest_version.name

    def get_version_path(self, version_id: str) -> Path:
        """Get the path to a specific version of QA pairs.

        Args:
            version_id: Version ID to locate

        Returns:
            Path to version directory

        Raises:
            ValueError if version not found
        """
        version_dir = self.base_path / version_id
        if not version_dir.exists():
            raise ValueError(f"Version {version_id} not found")

        return version_dir

    def get_version_metadata(self, version_id: str) -> dict:
        """Get metadata for a specific version.

        Args:
            version_id: Version ID to get metadata for

        Returns:
            Version metadata dictionary

        Raises:
            ValueError if version or metadata not found
        """
        version_dir = self.get_version_path(version_id)
        metadata_path = version_dir / "metadata.json"

        if not metadata_path.exists():
            raise ValueError(f"Metadata not found for version {version_id}")

        with open(metadata_path) as f:
            return json.load(f)
