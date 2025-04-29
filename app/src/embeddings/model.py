from abc import ABC, abstractmethod


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

    @abstractmethod
    def token_length(self, text: str) -> int:
        """
        Returns the number of tokens of the input text.
        """
        pass

    @abstractmethod
    def encode(
        self, texts: str | list[str], show_progress_bar: bool = False
    ) -> list[float] | list[list[float]]:
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
