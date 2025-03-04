from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chainlit.utils import mount_chainlit
from src.app_config import app_config
from src.healthcheck import healthcheck_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Imagine LA uses port 5173 for development
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"https://(dev-social-benefits-navigator[a-zA-Z0-9-]+|benefitnavigator)\.web\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck_router)

if app_config.enable_chat_api:
    from src import chat_api

    app.include_router(chat_api.router)

# Add Chainlit AFTER including routers
mount_chainlit(app=app, target="src/chainlit.py", path="/chat")
