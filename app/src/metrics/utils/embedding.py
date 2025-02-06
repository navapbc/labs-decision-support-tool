"""Utilities for computing embeddings."""

import numpy as np
from typing import List, Optional
from openai import OpenAI
from .timer import measure_time

class EmbeddingComputer:
    """Handles computation of embeddings using OpenAI API."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-large",
        batch_size: int = 100,
        api_key: Optional[str] = None
    ):
        """Initialize the embedding computer.
        
        Args:
            model: OpenAI embedding model to use
            batch_size: Number of texts to process in each batch
            api_key: Optional OpenAI API key (uses env var if not provided)
        """
        self.model = model
        self.batch_size = batch_size
        self.client = OpenAI(api_key=api_key)
        self.embedding_dim = 3072 if "large" in model else 1536
    
    def compute_batch(self, texts: List[str]) -> np.ndarray:
        """Compute embeddings for a batch of texts."""
        try:
            with measure_time() as timer:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts
                )
            
            embeddings = np.array([e.embedding for e in response.data])
            return embeddings, timer.elapsed_ms()
            
        except Exception as e:
            print(f"Error computing embeddings: {e}")
            # Return zero embeddings as fallback
            return np.zeros((len(texts), self.embedding_dim)), 0.0
    
    def compute_all(self, texts: List[str], show_progress: bool = False) -> np.ndarray:
        """Compute embeddings for all texts in batches.
        
        Args:
            texts: List of texts to embed
            show_progress: Whether to show progress bar
        
        Returns:
            Tuple of (embeddings array, total time in ms)
        """
        all_embeddings = []
        total_time_ms = 0.0
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            embeddings, time_ms = self.compute_batch(batch)
            all_embeddings.append(embeddings)
            total_time_ms += time_ms
            
            if show_progress:
                print(f"Processed batch {i//self.batch_size + 1}/{(len(texts)-1)//self.batch_size + 1}")
        
        return np.vstack(all_embeddings), total_time_ms

def normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """Normalize embeddings for cosine similarity."""
    norms = np.linalg.norm(embeddings, axis=1)
    norms = norms.reshape(-1, 1)
    norms[norms == 0] = 1  # Avoid division by zero
    return embeddings / norms

def compute_similarities(
    query_embeddings: np.ndarray,
    chunk_embeddings: np.ndarray,
    normalize: bool = True
) -> np.ndarray:
    """Compute cosine similarities between queries and chunks.
    
    Args:
        query_embeddings: Query embeddings of shape (n_queries, dim)
        chunk_embeddings: Chunk embeddings of shape (n_chunks, dim)
        normalize: Whether to normalize embeddings first
    
    Returns:
        Similarities of shape (n_queries, n_chunks)
    """
    if normalize:
        query_embeddings = normalize_embeddings(query_embeddings)
        chunk_embeddings = normalize_embeddings(chunk_embeddings)
    
    return np.dot(query_embeddings, chunk_embeddings.T)
