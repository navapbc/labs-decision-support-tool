import chainlit as cl
from src.cache import get_appconfig


def login_callback(username: str, password: str) -> cl.User | None:
    if password == get_appconfig().global_password:
        return cl.User(identifier=username)
    else:
        return None


def require_login() -> None:
    if get_appconfig().global_password:
        cl.password_auth_callback(login_callback)
