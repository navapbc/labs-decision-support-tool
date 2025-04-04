import logging
from dataclasses import dataclass
from urllib.parse import quote_plus

import pytest

from src.adapters.db.clients.postgres_client import (
    get_connection_parameters,
    get_database_url,
    verify_ssl,
)
from src.adapters.db.clients.postgres_config import get_db_config


@dataclass
class DummyPgConn:
    ssl_in_use: bool


class DummyConnectionInfo:
    def __init__(self, ssl_in_use):
        self.pgconn = DummyPgConn(ssl_in_use)


def test_verify_ssl(caplog):
    caplog.set_level(logging.INFO)  # noqa: B1

    conn_info = DummyConnectionInfo(True)
    verify_ssl(conn_info)

    assert caplog.messages == ["database connection is using SSL"]
    assert caplog.records[0].levelname == "INFO"


def test_verify_ssl_not_in_use(caplog):
    caplog.set_level(logging.INFO)  # noqa: B1

    conn_info = DummyConnectionInfo(False)
    verify_ssl(conn_info)

    assert caplog.messages == ["database connection is not using SSL"]
    assert caplog.records[0].levelname == "INFO"


def test_get_connection_parameters(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DB_SSL_MODE")
    db_config = get_db_config()
    conn_params = get_connection_parameters(db_config)

    assert conn_params == dict(
        host=db_config.host,
        dbname=db_config.name,
        user=db_config.username,
        password=db_config.password,
        port=db_config.port,
        options=f"-c search_path={db_config.db_schema}",
        connect_timeout=10,
        sslmode="require",
    )


def test_get_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DB_SSL_MODE")
    monkeypatch.setenv("DB_PASSWORD", "some:pass:with:colons")
    db_config = get_db_config()
    conn_params = get_connection_parameters(db_config)
    db_url = get_database_url()

    assert (
        db_url
        == f"postgresql://{conn_params['user']}:{quote_plus("some:pass:with:colons")}@{conn_params['host']}:{conn_params['port']}/{conn_params['dbname']}?search_path={db_config.db_schema}"
    )
