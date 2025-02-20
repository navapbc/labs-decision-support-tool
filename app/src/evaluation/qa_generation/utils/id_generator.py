import uuid
from hashlib import md5
from typing import Optional

def generate_stable_id(question: str, answer: str) -> uuid.UUID:
    """Generate a stable UUID for a QA pair based on content.
    
    Note: No longer includes dataset in hash to support future multiple ground truths.
    """
    content = f"{question}||{answer}".encode("utf-8")
    content_hash = md5(content, usedforsecurity=False).digest()
    return uuid.UUID(bytes=content_hash[:16]) 