from functools import cache

from src.app_config import AppConfig


@cache
def get_app_config() -> AppConfig:
    return AppConfig()
