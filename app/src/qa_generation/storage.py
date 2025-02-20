import csv
from datetime import datetime
from pathlib import Path
from typing import List
from .models import QAPair, QAPairVersion
import json

class QAPairStorage:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        
    def save_qa_pairs(
        self, 
        qa_pairs: List[QAPair],
        version_id: str,  # ID for this QA generation run
    ) -> Path:
        """Save QA pairs with version information."""
        # Create versioned directory
        version_dir = self.base_path / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # TODO: Save metadata for metrics CLI
        # This metadata file will be used by the metrics CLI to track:
        # - Which LLM model was used
        # - Generation parameters (questions per chunk)
        # - Dataset versions
        # - Other relevant info for reproducing results
        metadata = {
            "version_id": version_id,
            "timestamp": datetime.utcnow().isoformat(),
            "llm_model": qa_pairs[0].version.llm_model if qa_pairs else None,
            "questions_per_chunk": len(qa_pairs) // len(set(p.chunk_id for p in qa_pairs if p.chunk_id)),
            "total_pairs": len(qa_pairs)
        }
        
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        # Save QA pairs CSV
        csv_path = version_dir / "qa_pairs.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "id", "question", "answer", "document_name",
                "document_source", "source", "document_id", "chunk_id",
                "content_hash", "dataset", "created_at",
                "version_id", "version_timestamp", "version_llm_model"
            ])
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
                
        return csv_path 