from sentence_transformers import SentenceTransformer

from src.app_config import AppConfig

_app_config: AppConfig | None = None


def get_appconfig() -> AppConfig:
    global _app_config

    if not _app_config:
        _app_config = AppConfig()
    return _app_config


_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model

    if not _embedding_model:
        _embedding_model = SentenceTransformer(get_appconfig().embedding_model)
    return _embedding_model
