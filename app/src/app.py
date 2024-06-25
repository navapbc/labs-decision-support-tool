from fastapi import FastAPI
from chainlit.utils import mount_chainlit
from src.healthcheck import healthcheck_router

app = FastAPI()

app.include_router(healthcheck_router)

mount_chainlit(app=app, target="src/chainlit.py", path="/chat")