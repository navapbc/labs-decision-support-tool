from typing import List, Sequence, Union

import tiktoken
from openai import OpenAI

from src.embeddings.model import EmbeddingModel


class OpenAIEmbedding(EmbeddingModel):
    """
    Implementation of EmbeddingModel that uses OpenAI's embedding models.
    """

    def __init__(
        self, model_name: str = "text-embedding-3-small", api_key: str = None, base_url: str = None
    ):
        """
        Initialize with OpenAI client and model name.

        Args:
            model_name: Name of the OpenAI embedding model to use
                       (e.g., 'text-embedding-3-small')
            api_key: Optional API key for OpenAI. If not provided, will use
                     the OPENAI_API_KEY environment variable.
            base_url: Optional base URL for the OpenAI API. If not provided, will
                      use the default OpenAI API URL.
        """
        self._model_name = model_name
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._tokenizer = tiktoken.get_encoding(
            "cl100k_base"
        )  # Default encoding for text-embedding models

    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """

        model_limits = {
            "text-embedding-3-small": 8191,
            "text-embedding-3-large": 8191,
            "text-embedding-ada-002": 8191,
        }
        return model_limits.get(self._model_name, 8191)  # Default to 8191 if model not in the list

    @property
    def tokenizer(self):
        """
        Returns the tokenizer used by the model.
        """
        return self._tokenizer

    def encode(
        self, texts: Union[str, Sequence[str]], show_progress_bar: bool = False
    ) -> Union[List[float], List[List[float]]]:
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

        response = self._client.embeddings.create(model=self._model_name, input=input_texts)

        embeddings = [data.embedding for data in response.data]

        # Return single embedding if input was a single string
        return embeddings[0] if single_input else embeddings
