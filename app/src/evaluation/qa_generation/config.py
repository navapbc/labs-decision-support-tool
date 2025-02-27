from argparse import Namespace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional


class QuestionSource(str, Enum):
    """Source for generating questions."""

    CHUNK = "chunk"  # Generate from individual chunks
    DOCUMENT = "document"  # Generate from full documents


class GenerationConfig:
    """Configuration for QA pair generation."""

    DEFAULT_OUTPUT_DIR = Path("src/evaluation/data")

    def __init__(
        self,
        llm_model: str = "gpt-4o-mini",
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        dataset_filter: Optional[List[str]] = None,
        sample_fraction: Optional[float] = None,
        random_seed: Optional[int] = None,
        question_source: QuestionSource = QuestionSource.CHUNK,
        args: Optional[Namespace] = None,
    ):
        """
        Initialize configuration for QA pair generation.

        Args can be provided either directly or via a Namespace object (e.g., from argparse).
        If args is provided, it takes precedence over other parameters.
        """
        if args is not None:
            # Initialize from CLI arguments if provided
            self.llm_model = args.llm
            self.output_dir = args.output_dir
            self.dataset_filter = args.dataset
            self.sample_fraction = args.sampling
            self.random_seed = args.random_seed
            self.question_source = question_source  # Not in CLI args, use default
        else:
            # Initialize from direct parameters
            self.llm_model = llm_model
            self.output_dir = output_dir
            self.dataset_filter = dataset_filter
            self.sample_fraction = sample_fraction
            self.random_seed = random_seed
            self.question_source = question_source

        # Generate version ID using timestamp for unique identification
        self.version_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    @property
    def qa_pairs_dir(self) -> Path:
        """Get the directory for storing QA pairs with versioning."""
        return self.output_dir / "qa_pairs" / self.version_id

    @property
    def latest_symlink(self) -> Path:
        """Get the path to the 'latest' symlink."""
        return self.output_dir / "qa_pairs" / "latest"
