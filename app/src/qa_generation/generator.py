from typing import List, Iterator
from uuid import UUID
from litellm import completion
from hashlib import md5
import json
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from src.app_config import app_config
from src.db.models.document import Document, Chunk
from src.generate import completion_args
from .models import QAPair, QAPairVersion
from .config import GenerationConfig, QuestionSource
from .progress import GenerationProgress

logger = logging.getLogger(__name__)

GENERATE_QUESTION_ANSWER_PROMPT = """
Using the provided text, generate unique questions and answers, avoid rephrasing or changing the punctuation of the question to ensure distinct questions and answers.
Respond with a single JSON dictionary in the following format:
{
  "question": "A specific question based on the content",
  "answer": "A clear and accurate answer from the content"
}
Do not include any additional formatting, newlines, or text outside the JSON.
"""

MAX_WORKERS = 5  # Limit concurrent API calls

def generate_qa_pairs(document_or_chunk: Document | Chunk, num_pairs: int = 1, llm: str = "gpt-4o-mini") -> List[QAPair]:
    """Generate QA pairs from a document or chunk."""
    # Get document and chunk info
    if isinstance(document_or_chunk, Document):
        document = document_or_chunk
        chunk_id = None
    else:
        document = document_or_chunk.document
        chunk_id = document_or_chunk.id
    
    # Create version info
    version = QAPairVersion(
        version_id=datetime.now().strftime("%Y-%m-%d"),
        llm_model=llm,
    )
    
    response = completion(
        model=llm,
        messages=[
            {
                "content": GENERATE_QUESTION_ANSWER_PROMPT,
                "role": "system",
            },
            {
                "content": f"Please create one high-quality question-answer pair from this content: {document_or_chunk.content}",
                "role": "user",
            },
        ],
        temperature=app_config.temperature,
        **completion_args(llm),
    )
    
    content = response.choices[0].message.content
    try:
        # Clean up the response
        content = content.strip()
        
        # Handle different JSON formats
        # Try parsing as a list first
        if content.startswith("["):
            generated_pairs = json.loads(content)
        # Try parsing as a single object
        elif content.startswith("{"):
            generated_pairs = [json.loads(content)]
        else:
            # Try parsing each line as a separate JSON object
            generated_pairs = []
            for line in content.split("\n"):
                line = line.strip()
                if line and line.startswith("{"):
                    try:
                        pair = json.loads(line)
                        generated_pairs.append(pair)
                    except json.JSONDecodeError:
                        continue
        
        # Validate required fields
        valid_pairs = []
        for pair in generated_pairs:
            if "question" in pair and "answer" in pair:
                valid_pairs.append(pair)
        generated_pairs = valid_pairs
        
        if not generated_pairs:
            logger.error(f"No valid QA pairs found in response: {content}")
            return []
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response: {content}")
        logger.error(f"Error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error processing response: {e}")
        logger.error(f"Response content: {content}")
        return []
    
    qa_pairs: List[QAPair] = []

    # Process each generated pair
    for pair in generated_pairs:
        # Generate stable ID from content
        content = f"{pair['question']}||{pair['answer']}||{document.source}".encode("utf-8")
        content_hash = md5(content, usedforsecurity=False).digest()
        qa_id = UUID(bytes=content_hash[:16])

        qa_pair = QAPair(
            id=qa_id,
            question=pair['question'],
            answer=pair['answer'],
            document_name=document.name,
            document_source=document.source,
            document_id=document.id,
            chunk_id=chunk_id,
            content_hash=md5(document_or_chunk.content.encode('utf-8'), usedforsecurity=False).hexdigest(),
            dataset=document.source,
            created_at=document.created_at,
            version=version
        )
        qa_pairs.append(qa_pair)

    return qa_pairs 

class QAGenerator:
    """Handles QA pair generation with progress tracking."""
    
    def __init__(self, config: GenerationConfig):
        self.config = config
        self.progress = GenerationProgress()
        self.llm = config.llm_model or app_config.llm
        
    def _get_chunks_to_process(self, documents: List[Document]) -> List[tuple[Document | Chunk, int]]:
        """Get list of (document/chunk, num_pairs) tuples to process."""
        items = []
        if self.config.question_source == QuestionSource.DOCUMENT:
            items.extend((doc, self.config.questions_per_unit) for doc in documents)
        else:
            for doc in documents:
                items.extend((chunk, self.config.questions_per_unit) for chunk in doc.chunks)
        return items
        
    def generate_from_documents(self, documents: List[Document]) -> Iterator[QAPair]:
        """Generate QA pairs from documents."""
        items = self._get_chunks_to_process(documents)
        total = len(items)
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all generation tasks
            futures = {
                executor.submit(
                    generate_qa_pairs,
                    item,
                    num_pairs,
                    self.config.llm_model
                ): item 
                for item, num_pairs in items
            }
            
            # Process results as they complete
            with tqdm(total=total, desc="Generating QA pairs") as pbar:
                for future in as_completed(futures):
                    pbar.update(1)
                    try:
                        for qa_pair in future.result():
                            yield qa_pair
                    except Exception as e:
                        logger.error(f"Error generating QA pair: {e}")
                        continue 