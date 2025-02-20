from dataclasses import dataclass
from enum import Enum
from typing import List

class QuestionSource(str, Enum):
    DOCUMENT = "document"
    CHUNK = "chunk"

@dataclass
class GenerationConfig:
    """Configuration for QA pair generation."""
    datasets: List[str] | None = None  # If None, uses all datasets
    llm_model: str = "gpt-4o-mini"  # Model to use for generation
    
    # Fixed defaults
    questions_per_unit: int = 1  # One question per chunk
    question_source: QuestionSource = QuestionSource.CHUNK  # Always generate from chunks
    
    @classmethod
    def from_cli_args(cls, args) -> "GenerationConfig":
        """Create config from CLI arguments."""
        return cls(
            datasets=args.dataset,  # args.dataset is already a list from nargs
            llm_model=args.llm
        ) 