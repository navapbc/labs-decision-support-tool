from sentence_transformers import SentenceTransformer

from src.embeddings.model import EmbeddingModel


class SentenceTransformerEmbedding(EmbeddingModel):
    """
    Implementation of EmbeddingModel that uses SentenceTransformer models.
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

    def token_length(self, text: str) -> int:
        """
        Returns the number of tokens of the input text.
        """

        """
        The add_special_tokens argument is specified in PreTrainedTokenizerFast.encode_plus(), parent class of MPNetTokenizerFast.
        It defaults to True for encode_plus() but defaults to False for .tokenize().
        Setting add_special_tokens=True will add the special tokens CLS(0) and SEP(2) to the beginning and end of the input text.
        The add_special_tokens argument is valid for only PreTrainedTokenizerFast subclasses.
        """
        return len(self._model.tokenizer.tokenize(text, add_special_tokens=True))

    def encode(
        self, texts: str | list[str], show_progress_bar: bool = False
    ) -> list[float] | list[list[float]]:
        """
        Encodes text(s) into embedding vector(s) using the SentenceTransformer model.

        Args:
            texts: Text string or sequence of text strings to encode
            show_progress_bar: Whether to show a progress bar when encoding multiple texts

        Returns:
            A single embedding vector (if texts is a string) or
            a list of embedding vectors (if texts is a sequence of strings)
        """
        return self._model.encode(texts, show_progress_bar=show_progress_bar)  # type: ignore
