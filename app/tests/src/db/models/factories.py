"""Factories for generating test data.

These factories are used to generate test data for the tests. They are
used both for generating in memory objects and for generating objects
that are persisted to the database.

The factories are based on the `factory_boy` library. See
https://factoryboy.readthedocs.io/en/latest/ for more information.
"""

from datetime import datetime
from typing import Optional

import factory
import factory.fuzzy
import faker
from sqlalchemy.orm import scoped_session

import src.adapters.db as db
import src.util.datetime_util as datetime_util
from src.db.models.document import Chunk, Document
from tests.mock.mock_sentence_transformer import MockSentenceTransformer

_db_session: Optional[db.Session] = None

fake = faker.Faker()


def get_db_session() -> db.Session:
    # _db_session is only set in the pytest fixture `enable_factory_create`
    # so that tests do not unintentionally write to the database.
    if _db_session is None:
        raise Exception(
            """Factory db_session is not initialized.

            If your tests don't need to cover database behavior, consider
            calling the `build()` method instead of `create()` on the factory to
            not persist the generated model.

            If running tests that actually need data in the DB, pull in the
            `enable_factory_create` fixture to initialize the db_session.
            """
        )

    return _db_session


# The scopefunc ensures that the session gets cleaned up after each test
# it implicitly calls `remove()` on the session.
# see https://docs.sqlalchemy.org/en/20/orm/contextual.html
Session = scoped_session(lambda: get_db_session(), scopefunc=lambda: get_db_session())


class Generators:
    Now = factory.LazyFunction(datetime.now)
    UtcNow = factory.LazyFunction(datetime_util.utcnow)
    UuidObj = factory.Faker("uuid4", cast_to=None)


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = Session
        sqlalchemy_session_persistence = "commit"


class DocumentFactory(BaseFactory):
    class Meta:
        model = Document

    name = factory.Faker("word")
    content = factory.Faker("text")
    dataset = factory.Faker("word")
    program = factory.Faker("random_element", elements=["SNAP", "Medicaid", "TANF"])
    region = factory.Faker("random_element", elements=["MI", "MD", "PA"])


class ChunkFactory(BaseFactory):
    class Meta:
        model = Chunk

    document = factory.SubFactory(DocumentFactory)
    content = factory.LazyAttribute(lambda o: o.document.content)
    tokens = factory.LazyAttribute(
        lambda o: len(MockSentenceTransformer().tokenizer.tokenize(o.content))
    )
    mpnet_embedding = factory.LazyAttribute(lambda o: MockSentenceTransformer().encode(o.content))

    num_splits = 1
    split_index = 0
