import chainlit as cl
from src.app_config import app_config


def login_callback(username: str, password: str) -> cl.User | None:
    if password == app_config.global_password:
        return cl.User(identifier=username)
    else:
        return None


def require_login() -> None:
    # Set GLOBAL_PASSWORD, and also set CHAINLIT_AUTH_SECRET for
    # Chainlit to sign the authorization tokens.

    if app_config.global_password:
        cl.password_auth_callback(login_callback)
