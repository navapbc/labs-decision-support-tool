import logging

import _pytest.monkeypatch
import boto3
import moto
import pytest

import src.adapters.db as db
import tests.src.db.models.factories as factories
from src.app_config import AppConfig
from src.db import models
from src.db.models.document import ChunkWithScore
from src.util.local import load_local_env_vars
from tests.lib import db_testing
from tests.mock.mock_embedding_model import MockEmbeddingModel

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def env_vars():
    """
    Default environment variables for tests to be
    based on the local.env file. These get set once
    before all tests run. As "session" is the highest
    scope, this will run before any other explicit fixtures
    in a test.

    See: https://docs.pytest.org/en/6.2.x/fixture.html#autouse-order

    To set a different environment variable for a test,
    use the monkeypatch fixture, for example:

    ```py
    def test_example(monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
    ```

    Several monkeypatch fixtures exists below for different
    scope levels.
    """
    load_local_env_vars()


####################
# Test DB session
####################


# From https://github.com/pytest-dev/pytest/issues/363
@pytest.fixture(scope="session")
def monkeypatch_session():
    """
    Create a monkeypatch instance that can be used to
    monkeypatch global environment, objects, and attributes
    for the duration the test session.
    """
    mpatch = _pytest.monkeypatch.MonkeyPatch()
    yield mpatch
    mpatch.undo()


# From https://github.com/pytest-dev/pytest/issues/363
@pytest.fixture(scope="module")
def monkeypatch_module():
    mpatch = _pytest.monkeypatch.MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session")
def db_client(monkeypatch_session) -> db.DBClient:
    """
    Creates an isolated database for the test session.

    Creates a new empty PostgreSQL schema, creates all tables in the new schema
    using SQLAlchemy, then returns a db.DBClient instance that can be used to
    get connections or sessions to this database schema. The schema is dropped
    after the test suite session completes.
    """

    with db_testing.create_isolated_db(monkeypatch_session) as db_client:
        with db_client.get_connection() as conn, conn.begin():
            models.metadata.create_all(bind=conn)
        yield db_client


@pytest.fixture
def db_session(db_client: db.DBClient) -> db.Session:
    """
    Returns a database session connected to the schema used for the test session.
    """
    with db_client.get_session() as session:
        yield session


@pytest.fixture
def enable_factory_create(monkeypatch, db_session) -> db.Session:
    """
    Allows the create method of factories to be called. By default, the create
    throws an exception to prevent accidental creation of database objects for tests
    that do not need persistence. This fixture only allows the create method to be
    called for the current test. Each test that needs to call Factory.create should pull in
    this fixture.
    """
    monkeypatch.setattr(factories, "_db_session", db_session)
    return db_session


@pytest.fixture
def app_config(monkeypatch, db_client: db.DBClient):
    monkeypatch.setattr(AppConfig, "db_session", lambda _self: db_client.get_session())
    monkeypatch.setattr(AppConfig, "embedding_model", MockEmbeddingModel())


####################
# Test App & Client
####################


@pytest.fixture
def api_auth_token(monkeypatch):
    auth_token = "abcd1234"
    monkeypatch.setenv("API_AUTH_TOKEN", auth_token)
    return auth_token


####################
# AWS Mock Fixtures
####################


@pytest.fixture
def reset_aws_env_vars(monkeypatch):
    # Reset the env vars so you can't accidentally connect
    # to a real AWS account if you were doing some local testing
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def mock_s3(reset_aws_env_vars):
    with moto.mock_s3():
        yield boto3.resource("s3")


@pytest.fixture
def mock_s3_bucket_resource(mock_s3):
    bucket = mock_s3.Bucket("test_bucket")
    bucket.create()
    yield bucket


@pytest.fixture
def mock_s3_bucket(mock_s3_bucket_resource):
    yield mock_s3_bucket_resource.name


@pytest.fixture
def chunks_with_scores():
    return [
        ChunkWithScore(factories.ChunkFactory.build(), 0.99),
        ChunkWithScore(factories.ChunkFactory.build(), 0.90),
        ChunkWithScore(factories.ChunkFactory.build(), 0.85),
    ]
