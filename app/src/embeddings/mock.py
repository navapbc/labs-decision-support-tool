import math
from typing import List, Sequence, Union

from src.embeddings.model import EmbeddingModel


class MockTokenizer:
    def tokenize(self, text, **kwargs):
        return text.split()


class MockEmbeddingModel(EmbeddingModel):
    """
    Mock implementation of EmbeddingModel for testing.
    """
    
    def __init__(self, embedding_size: int = 768):
        """
        Initialize the mock embedding model.
        
        Args:
            embedding_size: Size of the embedding vectors to generate
        """
        self._max_seq_length = 512
        self._tokenizer = MockTokenizer()
        self._embedding_size = embedding_size
    
    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        return self._max_seq_length
    
    @property
    def tokenizer(self):
        """
        Returns the tokenizer used by the model.
        """
        return self._tokenizer
    
    def _encode_one(self, text: str) -> List[float]:
        """
        Encode a single text string into an embedding vector.
        
        The embedding vector is deterministically generated based on the average
        token length in the text.
        """
        tokens = self.tokenizer.tokenize(text)
        if not tokens:
            return [0.0] * self._embedding_size
            
        average_token_length = sum(len(token) for token in tokens) / len(tokens)
        
        # Map average length to between 0 and 90 degrees
        # Then project that angle on the first two dimensions and pad the rest as 0
        return [
            float(math.cos(math.pi / 2 * average_token_length)),
            float(math.sin(math.pi / 2 * average_token_length)),
        ] + [0.0] * (self._embedding_size - 2)
    
    def encode(
        self, 
        texts: Union[str, Sequence[str]], 
        show_progress_bar: bool = False
    ) -> Union[List[float], List[List[float]]]:
        """
        Encodes text(s) into embedding vector(s).
        
        Args:
            texts: Text string or sequence of text strings to encode
            show_progress_bar: Whether to show a progress bar when encoding multiple texts
            
        Returns:
            A single embedding vector (if texts is a string) or
            a list of embedding vectors (if texts is a sequence of strings)
        """
        if isinstance(texts, str):
            return self._encode_one(texts)
        return [self._encode_one(text) for text in texts]