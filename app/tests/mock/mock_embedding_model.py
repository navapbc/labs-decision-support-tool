import math

from src.embeddings.model import EmbeddingModel


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
        self._embedding_size = embedding_size

    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        return self._max_seq_length

    @max_seq_length.setter
    def max_seq_length(self, value: int):
        """
        Sets the maximum sequence length supported by the model.
        """
        self._max_seq_length = value

    def token_length(self, text: str) -> int:
        """
        Returns the number of tokens in the text.
        """
        return len(text.split())

    def _encode_one(self, text: str) -> list[float]:
        """
        Encode a single text string into an embedding vector.

        The embedding vector is deterministically generated based on the average
        token length in the text.
        """
        tokens = text.split()
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
        if isinstance(texts, str):
            return self._encode_one(texts)
        return [self._encode_one(text) for text in texts]
