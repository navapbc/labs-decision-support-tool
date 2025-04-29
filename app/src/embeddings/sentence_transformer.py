from typing import List, Sequence, Union

from sentence_transformers import SentenceTransformer

from src.embeddings.model import EmbeddingModel


class SentenceTransformerEmbedding(EmbeddingModel):
    """
    Implementation of EmbeddingModel that uses SentenceTransformer odels.
    """

    def __init__(self, model_name: str):
        """
        Initialize with a SentenceTransformer model name.

        Args:
            model_name: Name of the SentenceTransformer model to use
                        (e.g., 'multi-qa-mpnet-base-cos-v1')
        """
        self._model = SentenceTransformer(model_name)

    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        return self._model.max_seq_length

    @property
    def tokenizer(self):
        """
        Returns the tokenizer used by the model.
        """
        return self._model.tokenizer

    def encode(
        self, texts: Union[str, Sequence[str]], show_progress_bar: bool = False
    ) -> Union[List[float], List[List[float]]]:
        """
        Encodes text(s) into embedding vector(s) using the SentenceTransformer model.

        Args:
            texts: Text string or sequence of text strings to encode
            show_progress_bar: Whether to show a progress bar when encoding multiple texts

        Returns:
            A single embedding vector (if texts is a string) or
            a list of embedding vectors (if texts is a sequence of strings)
        """
        return self._model.encode(texts, show_progress_bar=show_progress_bar)
