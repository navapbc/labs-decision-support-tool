from fastapi import FastAPI

from chainlit.utils import mount_chainlit
from src.app_config import app_config
from src.healthcheck import healthcheck_router

app = FastAPI()
app.include_router(healthcheck_router)

mount_chainlit(app=app, target="src/chainlit.py", path="/chat")

if app_config.enable_chat_api:
    from src import chat_api

    app.include_router(chat_api.router)
    chat_api.logger.info("Chat API loaded: %s", chat_api.__name__)
