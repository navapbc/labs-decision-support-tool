from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class QAPairVersion(BaseModel):
    """Version information for a QA pair set."""
    version_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    llm_model: str  # Model used for generation
    
class QAPair(BaseModel):
    """A question-answer pair with versioning."""
    id: UUID  # Stable ID generated at creation time
    question: str
    answer: str
    document_name: str
    document_source: str
    document_id: UUID
    chunk_id: Optional[UUID]
    content_hash: str
    dataset: str
    version: QAPairVersion
    created_at: datetime = Field(default_factory=datetime.utcnow) 