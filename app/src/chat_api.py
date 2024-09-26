#!/usr/bin/env python3

"""
This is an initial API that demonstrates how to create an API using FastAPI,
which is compatible with Chainlit. This file is a starting point for creating
an API that can be deployed with the Chainlit chatbot or as a standalone app.
"""

import logging
import os
import platform
import socket
from functools import cached_property
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from src import chat_engine
from src.healthcheck import health

if __name__ == "__main__":
    # If running directly, define the FastAPI app
    app = FastAPI()
else:
    # Otherwise use Chainlit's app
    # See https://docs.chainlit.io/deploy/api#how-it-works
    from chainlit.server import app

logger = logging.getLogger(__name__)


@app.get("/healthcheck")
async def healthcheck(request: Request):
    logger.info(request.headers)
    healthcheck_response = await health(request)
    return healthcheck_response


class ApiState:
    @cached_property
    def chat_engine(self):
        # Load the initial settings
        # settings = chatbot.create_init_settings()
        # chatbot.validate_settings(settings)

        # Create the chat engine
        # return chatbot.create_chat_engine(settings)

        engine_id = "bridges-eligibility-manual"
        return chat_engine.create_engine(engine_id)


app_state = ApiState()


# Make sure to use async functions for faster responses
@app.get("/engines")
async def engines():
    # response = app_state.chat_engine().gen_response(message)
    response = chat_engine.available_engines()
    return response


# This function cannot be async because it uses a single non-thread-safe app_state
@app.post("/query")
def query(message: str | Dict):
    # response = app_state.chat_engine().gen_response(message)
    response = chat_engine.available_engines()
    return response


@app.get("/query_html")
def query_html(request: Request):
    logger.info(request.headers)
    return HTMLResponse("<h1>Chainlit API</h1><p>Query HTML</p>")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=8001, log_level="info")
