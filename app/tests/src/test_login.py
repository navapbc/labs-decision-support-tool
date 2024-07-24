import os

import chainlit.config
from src.app_config import get_app_config
from src.login import login_callback, require_login


def test_require_login_no_password(monkeypatch):
    if "GLOBAL_PASSWORD" in os.environ:
        monkeypatch.delenv("GLOBAL_PASSWORD")

    # Rebuild AppConfig with new environment variables
    get_app_config.cache_clear()

    require_login()

    assert not chainlit.config.code.password_auth_callback


def test_require_login_with_password(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "password")
    get_app_config.cache_clear()

    require_login()

    assert chainlit.config.code.password_auth_callback


def test_login_callback(monkeypatch):
    monkeypatch.setenv("GLOBAL_PASSWORD", "correct pass")
    get_app_config.cache_clear()

    assert login_callback("some user", "wrong pass") is None
    assert login_callback("some user", "correct pass").identifier == "some user"
