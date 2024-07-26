import types
from functools import cached_property
from typing import Any

from sentence_transformers import SentenceTransformer

import src.adapters.db as db
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

    global_password: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080

    embedding_model: str = "multi-qa-mpnet-base-cos-v1"
    chat_engine: str = "guru-snap"

    # Thresholds that determine which documents are sent to the LLM
    retrieval_k: int = 8
    retrieval_k_min_score: float = 0.45

    # Thresholds that determine which retrieved documents are shown in the UI
    docs_shown_max_num: int = 5
    docs_shown_min_score: float = 0.65

    def db_session(self) -> db.Session:
        return db.PostgresDBClient().get_session()

    @cached_property
    def sentence_transformer(self) -> SentenceTransformer:
        return SentenceTransformer(self.embedding_model)


class DynamicAppConfig:
    """
    This class is needed as a wrapper around AppConfig to support dynamically changing
    or reloading configuration values for unit testing, while still allowing cleaner calls
    like `app_config.retrieval_k` (as opposed to `app_config().retrieval_k`).
    """
    def __init__(self) -> None:
        self.reinit()

    def reinit(self, new_config: AppConfig | None = None) -> None:
        self.app_config = new_config if new_config else AppConfig()

    def __getattr__(self, name: str) -> Any:
        attrib = getattr(self.app_config, name)

        if not hasattr(self.app_config, name):
            raise AttributeError(f"No such field/method: {name}")

        if isinstance(attrib, types.MethodType):
            def func_wrapper(*args: Any, **kwargs: dict[str, Any]) -> Any:
                return attrib(*args, **kwargs)
            return func_wrapper

        return attrib


app_config = DynamicAppConfig()

