import tiktoken
from openai import OpenAI

from src.embeddings.model import EmbeddingModel

OPENAI_EMBEDDING_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
]


class OpenAIEmbedding(EmbeddingModel):
    """
    Implementation of EmbeddingModel that uses OpenAI's embedding models.
    """

    def __init__(self, model_name: str = "text-embedding-3-small"):
        """
        Initialize with OpenAI client and model name.

        Args:
            model_name: Name of the OpenAI embedding model to use
                       (e.g., 'text-embedding-3-small')
        """
        self._model_name = model_name
        self._client = OpenAI()
        self._tokenizer = tiktoken.get_encoding(
            "cl100k_base"
        )  # Default encoding for text-embedding models

    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        # The models listed in OPENAI_EMBEDDING_MODELS all have this maximum.
        return 8191

    def token_length(self, text: str) -> int:
        """
        Returns the number of tokens of the tokenized text.
        """
        return len(self._tokenizer.encode(text))

    def encode(
        self, texts: str | list[str], show_progress_bar: bool = False
    ) -> list[float] | list[list[float]]:
        """
        Encodes text(s) into embedding vector(s) using OpenAI's embedding API.

        Args:
            texts: Text string or sequence of text strings to encode
            show_progress_bar: Whether to show a progress bar when encoding multiple texts
                              (Note: Not implemented for OpenAI API calls as they handle batching internally)

        Returns:
            A single embedding vector (if texts is a string) or
            a list of embedding vectors (if texts is a sequence of strings)
        """

        single_input = isinstance(texts, str)
        input_texts = [texts] if single_input else list(texts)

        response = self._client.embeddings.create(model=self._model_name, input=input_texts)  # type: ignore

        embeddings = [data.embedding for data in response.data]

        # Return single embedding if input was a single string
        return embeddings[0] if single_input else embeddings
