from functools import cached_property

import src.adapters.db as db
from sentence_transformers import SentenceTransformer
from src.util.env_config import PydanticBaseEnvConfig


class AppConfig(PydanticBaseEnvConfig):
    # Do not instantiate this class directly. Use app_config instead.
    # These are default configuration values for the app, and
    # are shared across both local and deployed environments.

    # These values are overridden by environment variables.

    # To override these values for local development, set them
    # in .env (if they should be set just for you), or set
    # them in local.env (if they should be committed to the repo.)

    # To customize these values in deployed environments, set
    # them in infra/app/app-config/env-config/environment-variables.tf

    embedding_model: str = "multi-qa-mpnet-base-cos-v1"
    global_password: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    chat_engine: str = "guru-snap"

    def db_session(self) -> db.Session:
        return db.PostgresDBClient().get_session()

    @cached_property
    def sentence_transformer(self) -> SentenceTransformer:
        return SentenceTransformer(self.embedding_model)


app_config = AppConfig()
