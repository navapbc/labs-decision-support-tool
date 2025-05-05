import cohere
import time

from src.embeddings.model import EmbeddingModel

COHERE_EMBEDDING_MODELS = [
    "embed-v4.0",
]

MAX_RETRY_COUNT = 3
MAX_RETRY_DELAY_SECONDS = 0.5


class CohereEmbedding(EmbeddingModel):
    """
    Implementation of EmbeddingModel that uses Cohere's embedding models.
    """

    def __init__(self, model_name: str = "embed-v4.0"):
        """
        Initialize with Cohere client and model name.

        Args:
            model_name: Name of the Cohere embedding model to use
                       (e.g., 'embed-english-v3.0')
        """
        self._model_name = model_name
        self._client = cohere.ClientV2()

        # embed-v4.0 supports up to 128,000 tokens
        self._max_seq_length = 128_000

    @property
    def max_seq_length(self) -> int:
        """
        Returns the maximum sequence length supported by the model.
        """
        return self._max_seq_length

    def token_length(self, text: str) -> int:
        """
        Returns the number of tokens of the tokenized text.
        
        Note: This is an approximation as Cohere's internal tokenization
        might differ from tiktoken's tokenization.
        """
        return len(self._client.tokenize(text=text, model=self._model_name).tokens)

    def encode(
        self, texts: str | list[str], show_progress_bar: bool = False,
        input_type="search_document"  # Other option is "search_query"
    ) -> list[float] | list[list[float]]:
        """
        Encodes text(s) into embedding vector(s) using Cohere's embedding API.

        Args:
            texts: Text string or sequence of text strings to encode
            show_progress_bar: Whether to show a progress bar when encoding multiple texts
                              (Note: Not implemented for Cohere API calls)

        Returns:
            A single embedding vector (if texts is a string) or
            a list of embedding vectors (if texts is a sequence of strings)
        """
        single_input = isinstance(texts, str)
        input_texts = [texts] if single_input else list(texts)

        # The Cohere API is particularly flakey and will frequently return 500 errors
        retry_count = 0
        while retry_count < MAX_RETRY_COUNT:
            try:
                response = self._client.embed(
                    texts=input_texts,
                    model=self._model_name,
                    input_type=input_type,
                    embedding_types=["float"],
                )
                break  # Exit loop if successful
            except Exception as e:
                retry_count += 1
                if retry_count >= MAX_RETRY_COUNT:
                    raise e  # Re-raise exception if max retries reached
                time.sleep(MAX_RETRY_DELAY_SECONDS)

        
        embeddings = response.embeddings.float_

        # Return single embedding if input was a single string
        return embeddings[0] if single_input else embeddings