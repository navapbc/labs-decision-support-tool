#!/usr/bin/env python3

"""
This is a sample API file that demonstrates how to create an API using FastAPI,
which is compatible with Chainlit. This file is a starting point for creating
an API that can be deployed with the Chainlit chatbot.
"""

import logging
import os
import platform
import socket
from fastapi import APIRouter, Request, status
from pydantic import BaseModel


healthcheck_router = APIRouter()
logger = logging.getLogger("chatbot.healthcheck")

class HealthCheck(BaseModel):
    """Response model to validate and return when performing a health check."""

    status: str
    build_date: str
    git_sha: str
    service_name: str
    hostname: str


@healthcheck_router.get(
    "/health",
    tags=["health"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
async def health(request: Request) -> HealthCheck:
    """
    Healthcheck for api endpoint

    Args:
        request (Request)

    Returns:
        HealthCheck
    """
    logger.info(request.headers)

    git_sha = os.environ.get("GIT_SHA", "")
    build_date = os.environ.get("BUILD_DATE", "")

    service_name = os.environ.get("SERVICE_NAME", "")
    hostname = f"{platform.node()} {socket.gethostname()}"

    logger.info(f"Healthy {git_sha} built at {build_date}<br/>{service_name} {hostname}")
    return HealthCheck(
        build_date=build_date, git_sha=git_sha, status="OK", service_name=service_name, hostname=hostname
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=8001, log_level="info")
