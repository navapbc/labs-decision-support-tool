"""Shared storage utilities for QA pairs and evaluation results."""

import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from ..data_models import QAPair

MAX_RETRIES = 3
RETRY_DELAY = 0.1


class QAPairStorage:
    """Handles storage and versioning of QA pairs."""

    def __init__(self, base_path: Path):
        """Initialize storage with base path.

        Args:
            base_path: Base directory for QA pairs storage
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _update_symlink(self, target_dir: Path, max_retries: int = MAX_RETRIES) -> None:
        """Update latest symlink with retry logic.

        Args:
            target_dir: Directory to link to
            max_retries: Maximum number of retry attempts
        """
        latest_link = self.base_path / "latest"
        temp_link = None

        for attempt in range(max_retries):
            try:
                # Create temp symlink with unique name
                temp_link = self.base_path / f"latest.{datetime.now().timestamp()}"
                if temp_link.exists():
                    temp_link.unlink()
                temp_link.symlink_to(target_dir, target_is_directory=True)

                # Atomic rename of temp symlink to latest
                if latest_link.exists():
                    latest_link.unlink()
                temp_link.rename(latest_link)
                return

            except (OSError, RuntimeError) as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(RETRY_DELAY)
            finally:
                # Clean up temp link if it exists and wasn't renamed
                if temp_link and temp_link.exists():
                    temp_link.unlink()

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
            "timestamp": datetime.now(UTC).isoformat(),
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
                    "document_id",
                    "chunk_id",
                    "content_hash",
                    "dataset",
                    "created_at",
                    "version_id",
                    "version_timestamp",
                    "version_llm_model",
                    "expected_chunk_content",
                ],
            )
            writer.writeheader()
            for pair in qa_pairs:
                # Convert dataclass to dict and handle nested version
                row = pair.__dict__.copy()
                # Flatten version info into row
                row["version_id"] = pair.version.version_id
                row["version_timestamp"] = pair.version.timestamp
                row["version_llm_model"] = pair.version.llm_model
                # Remove nested version dict
                del row["version"]
                writer.writerow(row)

        # Update latest symlink with robust handling
        try:
            self._update_symlink(version_dir)
        except (OSError, RuntimeError):
            # If symlink operations fail, just continue
            # The files are still saved successfully
            pass

        return csv_path

    def get_latest_version(self) -> str:
        """Get the version ID of the latest QA pairs.

        Returns:
            Version ID string

        Raises:
            ValueError if no QA pairs found
        """
        try:
            # First try to find latest version by timestamp
            versions = sorted(
                [d for d in self.base_path.iterdir() if d.is_dir() and d.name != "latest"],
                key=lambda d: d.name,
                reverse=True,
            )
        except OSError as e:
            raise ValueError("No QA pairs found - error accessing directory") from e

        if not versions:
            raise ValueError("No QA pairs found - run generation first")

        latest_version = versions[0]

        # Handle symlink creation/update with retries
        try:
            self._update_symlink(latest_version)
        except (OSError, RuntimeError):
            # If symlink operations fail completely, just return the version
            # This maintains core functionality even if symlink fails
            pass

        return latest_version.name

    def get_version_path(self, version_id: str) -> Path:
        """Get the path to a specific version of QA pairs.

        Args:
            version_id: Version ID to locate

        Returns:
            Path to version directory

        Raises:
            ValueError if version not found or not a directory
        """
        version_dir = self.base_path / version_id
        if not version_dir.exists() or not version_dir.is_dir():
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
