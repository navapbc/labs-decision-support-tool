import chainlit as cl
from src.cache import get_appconfig


def auth_callback(username: str, password: str) -> cl.User | None:
    if password == get_appconfig().global_password:
        return cl.User(identifier=username)
    else:
        return None


def require_auth() -> None:
    global auth_callback

    if get_appconfig().global_password:
        print("Password required for authentication!!!!!")
        auth_callback = cl.password_auth_callback(auth_callback)
        auth_callback.enabled = True  # type: ignore
