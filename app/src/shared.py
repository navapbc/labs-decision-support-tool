from functools import cache

from sentence_transformers import SentenceTransformer

from src.app_config import AppConfig


@cache
def get_app_config() -> AppConfig:
    return AppConfig()


@cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(get_app_config().embedding_model)
