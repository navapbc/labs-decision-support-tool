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
    default_chat_engine: str | None = None
    allowed_chat_engines: str | None = None
    temperature: float = 0.0

    # Default LLM model
    llm: str | None = None

    # Absolute base URL used when creating browser-facing source links.
    public_source_base_url: str | None = None

    # Starts the chat API if set to True
    enable_chat_api: bool = True
    # If set, used instead of LITERAL_API_KEY for API
    literal_api_key_for_api: str | None = None

    @cached_property
    def db_client(self) -> db.PostgresDBClient:
        return db.PostgresDBClient()

    def db_session(self) -> db.Session:
        return self.db_client.get_session()

    @cached_property
    def embedding_model(self) -> EmbeddingModel:
        if self.embedding_model_name in OPENAI_EMBEDDING_MODELS:
            return OpenAIEmbedding(self.embedding_model_name)
        elif self.embedding_model_name in COHERE_EMBEDDING_MODELS:
            return CohereEmbedding(self.embedding_model_name)

        return SentenceTransformerEmbedding(self.embedding_model_name)

    @property
    def api_default_chat_engine(self) -> str:
        return self.default_chat_engine or self.chat_engine

    @property
    def api_allowed_chat_engines(self) -> list[str]:
        if self.allowed_chat_engines:
            return [engine.strip() for engine in self.allowed_chat_engines.split(",") if engine.strip()]
        return [self.api_default_chat_engine]

    @property
    def resolved_public_source_base_url(self) -> str:
        if self.public_source_base_url:
            return self.public_source_base_url.rstrip("/")

        host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{host}:{self.port}"


app_config = AppConfig()
