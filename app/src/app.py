from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.app_config import app_config
from src.healthcheck import healthcheck_router

app = FastAPI()
public_sources_dir = Path(__file__).resolve().parents[1] / "documents" / "public_sources"
public_sources_dir.mkdir(parents=True, exist_ok=True)
loopback_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
firebase_origin_regex = (
    r"https://(dev-social-benefits-navigator[a-zA-Z0-9-]+|benefitnavigator)\.web\.app"
)

app.add_middleware(
    CORSMiddleware,
    # Local development can use either localhost or 127.0.0.1 on varying ports.
    allow_origins=["http://localhost:3000", "http://localhost:3004"],
    allow_origin_regex=f"^({loopback_origin_regex}|{firebase_origin_regex})$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck_router)
app.mount("/sources", StaticFiles(directory=public_sources_dir), name="sources")

if app_config.enable_chat_api:
    from src import chat_api

    app.include_router(chat_api.router)

# Chainlit UI has been replaced by the Next.js frontend at /frontend
# The frontend connects to the API endpoints defined in chat_api.py
# To re-enable the Chainlit UI, uncomment the following lines:
# from chainlit.utils import mount_chainlit
# mount_chainlit(app=app, target="src/chainlit.py", path="/chat")
