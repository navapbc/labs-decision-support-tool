from abc import ABC, abstractmethod
from typing import List, Sequence, Union


class EmbeddingModel(ABC):
    """
    Abstract class for embedding models.
    
    This interface defines the methods needed by the application,
    allowing different embedding models to be used interchangeably.
    """
    
    @property
    @abstractmethod
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        pass
    
    @property
    @abstractmethod
    def tokenizer(self):
        """
        Returns the tokenizer used by the model.
        """
        pass
    
    @abstractmethod
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
        pass