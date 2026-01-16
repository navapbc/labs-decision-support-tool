from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app_config import app_config
from src.healthcheck import healthcheck_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Imagine LA uses port 5173 for development, Next.js uses 3000/3004
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:3004"],
    allow_origin_regex=r"https://(dev-social-benefits-navigator[a-zA-Z0-9-]+|benefitnavigator)\.web\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck_router)

if app_config.enable_chat_api:
    from src import chat_api

    app.include_router(chat_api.router)

# Chainlit UI has been replaced by the Next.js frontend at /frontend
# The frontend connects to the API endpoints defined in chat_api.py
# To re-enable the Chainlit UI, uncomment the following lines:
# from chainlit.utils import mount_chainlit
# mount_chainlit(app=app, target="src/chainlit.py", path="/chat")
