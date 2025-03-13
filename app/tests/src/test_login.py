import chainlit.config
from src.app_config import app_config
from src.login import login_callback, require_login


def test_require_login_no_password(monkeypatch):
    app_config.global_password = None
    require_login()

    assert not chainlit.config.CodeSettings.password_auth_callback


def test_require_login_with_password(monkeypatch):
    app_config.global_password = "password"
    require_login()

    assert chainlit.config.CodeSettings.password_auth_callback


def test_login_callback(monkeypatch):
    app_config.global_password = "correct pass"

    assert login_callback("some user", "wrong pass") is None
    assert login_callback("some user", "correct pass").identifier == "some user"
