import os

import chainlit.config
import src.cache
from src.login import login_callback, require_login


def test_require_login_no_password(monkeypatch):
    if "GLOBAL_PASSWORD" in os.environ:
        monkeypatch.delenv("GLOBAL_PASSWORD")
    src.cache._app_config = None

    require_login()

    assert not chainlit.config.code.password_auth_callback


def test_require_login_with_password(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "password")
    src.cache._app_config = None

    require_login()

    assert chainlit.config.code.password_auth_callback


def test_login_callback(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "correct pass")
    src.cache._app_config = None

    assert login_callback("some user", "wrong pass") is None
    assert login_callback("some user", "correct pass").identifier == "some user"
