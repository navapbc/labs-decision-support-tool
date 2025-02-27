"""QA pair generation functionality."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import md5
from typing import List

from litellm import completion
from pydantic import BaseModel, Field

from src.app_config import app_config
from src.db.models.document import Chunk, Document
from src.generate import completion_args

from ..data_models import QAPair
from .config import GenerationConfig, QuestionSource

logger = logging.getLogger(__name__)


class QAPairResponse(BaseModel):
    """Pydantic model for QA pair response from LLM."""

    question: str = Field(..., description="A specific question based on the content")
    answer: str = Field(..., description="A clear and accurate answer from the content")


GENERATE_QUESTION_ANSWER_PROMPT = """
Using the provided text, generate a unique question and answer, avoid rephrasing or changing the punctuation of the question to ensure distinct questions and answers.
Respond with a single question-answer pair based on the content in JSON format with 'question' and 'answer' fields.
"""

MAX_WORKERS = 5  # Limit concurrent API calls


def generate_qa_pair(document_or_chunk: Document | Chunk, llm: str = "gpt-4o-mini") -> List[QAPair]:
    """Generate QA pair from a document or chunk."""
    # Get document and chunk info
    if isinstance(document_or_chunk, Document):
        document = document_or_chunk
        chunk_id = None
    else:
        document = document_or_chunk.document
        chunk_id = document_or_chunk.id

    # Skip if content is None or source is None
    if not document_or_chunk.content or not document.source:
        logger.warning(
            f"Skipping QA generation for {document_or_chunk} - content or source is None"
        )
        return []

    try:
        response = completion(
            model=llm,
            messages=[
                {
                    "content": GENERATE_QUESTION_ANSWER_PROMPT,
                    "role": "system",
                },
                {
                    "content": f"Please create one high-quality question-answer pair from this content and format it as JSON: {document_or_chunk.content}",
                    "role": "user",
                },
            ],
            temperature=app_config.temperature,
            response_format={"type": "json_object"},
            **completion_args(llm),
        )

        content = response.choices[0].message.content

        # Parse the response using Pydantic
        try:
            qa_response = QAPairResponse.model_validate_json(content)
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {content}")
            logger.error(f"Error: {e}")
            return []

        # Create QAPair from the validated response
        qa_pair = QAPair(
            question=qa_response.question,
            answer=qa_response.answer,
            document_name=document.name,
            document_source=document.source,
            document_id=document.id,
            chunk_id=chunk_id,
            content_hash=md5(
                document_or_chunk.content.encode("utf-8"), usedforsecurity=False
            ).hexdigest(),
            dataset=document.dataset,
            llm_model=llm,
            created_at=document.created_at,
        )

        return [qa_pair]

    except Exception as e:
        logger.error(f"Unexpected error processing response: {e}")
        if hasattr(e, "response"):
            logger.error(f"Response content: {e.response}")
        return []


class QAGenerator:
    """Handles QA pair generation."""

    def __init__(self, config: GenerationConfig):
        """Initialize generator with config.

        Args:
            config: Generation configuration
        """
        self.config = config
        self.llm = config.llm_model or app_config.llm

    def _get_chunks_to_process(self, documents: List[Document]) -> List[Document | Chunk]:
        """Get list of documents or chunks to process."""
        items: List[Document | Chunk] = []
        if self.config.question_source == QuestionSource.DOCUMENT:
            items.extend(documents)
        else:
            for doc in documents:
                items.extend(doc.chunks)
        return items

    def generate_from_documents(self, documents: List[Document]) -> List[QAPair]:
        """Generate QA pair from documents.

        Args:
            documents: List of documents to generate QA pairs from

        Returns:
            List of generated QA pairs
        """
        items = self._get_chunks_to_process(documents)
        results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all generation tasks
            futures = {
                executor.submit(generate_qa_pair, item, self.config.llm_model): item
                for item in items
            }

            # Process results as they complete
            for future in as_completed(futures):
                try:
                    pairs = future.result()
                    results.extend(pairs)
                except Exception as e:
                    logger.error(f"Error generating QA pair: {e}")
                    continue

            logger.info(f"Generated QA pairs from {len(items)} items")

        return results
