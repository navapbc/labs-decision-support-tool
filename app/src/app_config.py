from functools import cached_property

from src.adapters import db
from src.embeddings.cohere import COHERE_EMBEDDING_MODELS, CohereEmbedding
from src.embeddings.model import EmbeddingModel
from src.embeddings.openai import OPENAI_EMBEDDING_MODELS, OpenAIEmbedding
from src.embeddings.sentence_transformer import SentenceTransformerEmbedding
from src.util.env_config import PydanticBaseEnvConfig


class AppConfig(PydanticBaseEnvConfig):
    # Do not instantiate this class directly. Use app_config instead.
    # These are constant configuration values for the app, and
    # are shared across both local and deployed environments.
    # Do not add changeable configuration settings to this class.

    # These values are overridden by environment variables.

    # To override these values for local development, set them
    # in .env (if they should be set just for you), or set
    # them in local.env (if they should be committed to the repo.)

    # To customize these values in deployed environments, set
    # them in infra/app/app-config/env-config/environment-variables.tf

    global_password: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080

    # Used for ingestion (before chatbot application starts) and retrieval (during chatbot interactions)
    embedding_model_name: str = "multi-qa-mpnet-base-cos-v1"

    # Default chat engine
    chat_engine: str = "imagine-la"
    temperature: float = 0.0

    # Default LLM model
    llm: str | None = None

    # Starts the chat API if set to True
    enable_chat_api: bool = True
    # If set, used instead of LITERAL_API_KEY for API
    literal_api_key_for_api: str | None = None

    @cached_property
    def db_client(self) -> db.PostgresDBClient:
        return db.PostgresDBClient()

    def db_session(self) -> db.Session:
        import pdb
        pdb.set_trace()
        return db.PostgresDBClient().get_session()

    # def db_session(self) -> db.Session:
    #     return self.db_client.get_session()

    @cached_property
    def embedding_model(self) -> EmbeddingModel:
        if self.embedding_model_name in OPENAI_EMBEDDING_MODELS:
            return OpenAIEmbedding(self.embedding_model_name)
        elif self.embedding_model_name in COHERE_EMBEDDING_MODELS:
            return CohereEmbedding(self.embedding_model_name)

        return SentenceTransformerEmbedding(self.embedding_model_name)


app_config = AppConfig()
