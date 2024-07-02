import os

import chainlit.config
import src.cache
from src.auth import auth_callback, require_auth


def test_require_auth_no_password(monkeypatch):
    if "GLOBAL_PASSWORD" in os.environ:
        monkeypatch.delenv("GLOBAL_PASSWORD")
    src.cache._app_config = None

    require_auth()

    assert not chainlit.config.code.password_auth_callback


def test_require_auth_with_password(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "password")
    src.cache._app_config = None

    require_auth()

    assert chainlit.config.code.password_auth_callback


def test_auth_callback(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "correct pass")
    src.cache._app_config = None

    require_auth()

    assert auth_callback("some user", "wrong pass") is None
    assert auth_callback("some user", "correct pass").identifier == "some user"
