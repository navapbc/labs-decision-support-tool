import chainlit as cl
from src.shared import get_app_config


def login_callback(username: str, password: str) -> cl.User | None:
    if password == get_app_config().global_password:
        return cl.User(identifier=username)
    else:
        return None


def require_login() -> None:
    # In addition to setting GLOBAL_PASSWORD, Chainlit also
    # requires CHAINLIT_AUTH_SECRET to be set (to sign the
    # authorization tokens.)

    if get_app_config().global_password:
        cl.password_auth_callback(login_callback)
