from src.util.env_config import PydanticBaseEnvConfig


class AppConfig(PydanticBaseEnvConfig):
    embedding_model: str = "multi-qa-mpnet-base-dot-v1"
