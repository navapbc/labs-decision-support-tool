import asyncio
import json
import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

import asyncpg

from chainlit.data.base import BaseDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from chainlit.data.literalai import LiteralDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.element import Element, ElementDict
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import Feedback, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User
from src.adapters.db.clients.postgres_client import get_database_url


def get_postgres_data_layer(database_url: Optional[str] = None) -> "PostgresDataLayer":
    return PostgresDataLayer(database_url=database_url)


def get_literal_data_layer(api_key: str) -> LiteralDataLayer:
    server = os.environ.get("LITERAL_API_URL")
    return LiteralDataLayer(api_key=api_key, server=server)


def get_default_data_layers() -> List[BaseDataLayer]:
    data_layers: List[BaseDataLayer] = []

    # The primary data layer is always our Postgres DB
    database_url = os.environ.get("DATABASE_URL")
    data_layers.append(get_postgres_data_layer(database_url))

    if api_key := os.environ.get("LITERAL_API_KEY"):
        data_layers.append(get_literal_data_layer(api_key))
    return data_layers


class ChainlitPolyDataLayer(BaseDataLayer):
    def __init__(self, data_layers: Optional[Sequence[BaseDataLayer]] = None) -> None:
        """
        The first data layer is the primary one, and returned values will be from that layer.
        Failures in other data layers are ignored.
        """
        self.data_layers = data_layers or get_default_data_layers()
        logger.info(
            "Custom Chainlit data layers: %s", [type(dl).__name__ for dl in self.data_layers]
        )
        assert self.data_layers, "No data layers initialized"

    async def _call_method(
        self, call_dl_func: Callable, excluded_dl: Optional[BaseDataLayer] = None
    ) -> List[Any]:
        # Create a list of tasks
        tasks = [
            asyncio.create_task(call_dl_func(dl)) for dl in self.data_layers if dl != excluded_dl
        ]

        # Gather results from all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for exceptions
        if isinstance(results[0], BaseException):
            logger.error("Error in primary data layer: %s", results[0])
            raise results[0]

        for i, result in enumerate(results[1:], start=1):
            if isinstance(result, Exception):
                logger.warning("Error in non-primary data layer %r: %s", i, result)
        return results

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        results = await self._call_method(lambda dl: dl.get_user(identifier))
        return results[0]

    @property
    def literalai_layer(self) -> Optional[BaseDataLayer]:
        return next((dl for dl in self.data_layers if isinstance(dl, LiteralDataLayer)), None)

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        """
        Unlike other persisted objects (like Thread and Step), the User argument has no id that can be set.
        The ChainlitDataLayer and LiteralDataLayer implementations return a generated UUID user.id.
        Unfortunately, since the UUIDs are different, referencing the user from the Thread consistently
        across data layers is not possible.
        (These Chainlit data layers were implemented to use a single data layer at a time.)
        While the LiteralDataLayer does not allow setting the user.id, the ChainlitDataLayer fortunately does.
        So call LiteralDataLayer.create_user() first and use the generated UUID in the call to
        ChainlitDataLayer.create_user() via User.metadata["uuid"]. In this way, the user.id is the same
        across all data layers.
        """
        assert user.identifier, "User identifier is required"

        if self.literalai_layer:
            if lai_user := await self.literalai_layer.create_user(user):
                user.metadata = (user.metadata or {}) | {"uuid": lai_user.id}
                logger.info("Created LiteralAI user %r (%r)", user.identifier, lai_user.id)
            else:
                logger.warning("Failed to create LiteralAI user %r", user.identifier)
                # 2 User objects will be created in LiteralAI:
                # - one with a string identifier that we assigned but this User is not associated with a thread
                #   because the primary data layer's (Postgres's) user.id is being used for Thread.user_id
                # - one with identifier=a generated UUID that is automatically created later when a thread is created
                # This means the user's identifier (a UUID) is shown in LiteralAI's UI instead of user.identifier,
                # which is more meaningful since it was provided as part of the user argument.

        results = await self._call_method(lambda dl: dl.create_user(user), self.literalai_layer)
        return results[0]

    async def delete_feedback(
        self,
        feedback_id: str,
    ) -> bool:
        results = await self._call_method(lambda dl: dl.delete_feedback(feedback_id))
        return results[0]

    async def upsert_feedback(
        self,
        feedback: Feedback,
    ) -> str:
        results = await self._call_method(lambda dl: dl.upsert_feedback(feedback))
        return results[0]

    @queue_until_user_message()
    async def create_element(self, element: Element) -> Optional[ElementDict]:  # pragma: no cover
        # Ensures that the uuid value is the same across data layers so that
        # persisted records can be cross-referenced across data layers
        assert element.id, f"element.id is required for {element}"
        results = await self._call_method(lambda dl: dl.create_element(element))
        return results[0]

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:  # pragma: no cover
        results = await self._call_method(lambda dl: dl.get_element(thread_id, element_id))
        return results[0]

    @queue_until_user_message()
    async def delete_element(
        self, element_id: str, thread_id: Optional[str] = None
    ) -> bool:  # pragma: no cover
        results = await self._call_method(lambda dl: dl.delete_element(element_id, thread_id))
        return results[0]

    @queue_until_user_message()
    async def create_step(self, step_dict: StepDict) -> Optional[StepDict]:
        # Ensures that the uuid value is the same across data layers so that
        # persisted records can be cross-referenced across data layers
        assert step_dict["id"], f"step_dict['id'] is required for {step_dict}"
        results = await self._call_method(lambda dl: dl.create_step(step_dict))
        return results[0]

    @queue_until_user_message()
    async def update_step(self, step_dict: StepDict) -> Optional[StepDict]:
        results = await self._call_method(lambda dl: dl.update_step(step_dict))
        return results[0]

    @queue_until_user_message()
    async def delete_step(self, step_id: str) -> bool:
        results = await self._call_method(lambda dl: dl.delete_step(step_id))
        return results[0]

    async def get_thread_author(self, thread_id: str) -> str:
        results = await self._call_method(lambda dl: dl.get_thread_author(thread_id))
        return results[0]

    async def delete_thread(self, thread_id: str) -> bool:
        results = await self._call_method(lambda dl: dl.delete_thread(thread_id))
        return results[0]

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        results = await self._call_method(lambda dl: dl.list_threads(pagination, filters))
        return results[0]

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        results = await self._call_method(lambda dl: dl.get_thread(thread_id))
        return results[0]

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> ThreadDict:
        results = await self._call_method(
            lambda dl: dl.update_thread(thread_id, name, user_id, metadata, tags)
        )
        return results[0]

    async def build_debug_url(self) -> str:  # pragma: no cover
        results = await self._call_method(lambda dl: dl.build_debug_url())
        # ChainlitDataLayer.build_debug_url() returns "" which isn't useful
        return next(res for res in results if res)


class PostgresDataLayer(ChainlitDataLayer):
    def __init__(
        self,
        database_url: Optional[str] = None,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = False,
    ):
        if database_url is None:
            database_url = ""
        logger.info("Creating PostgresDataLayer with database_url=%r", database_url)

        # See chainlit/data/__init__.py for storage_client options like S3
        super().__init__(
            database_url=database_url, storage_client=storage_client, show_logger=show_logger
        )

    async def connect(self) -> None:
        """
        Override ChainlitDataLayer.connect() to use a connection pool that calls our get_database_url().
        A connection pool is needed for AWS where IAM auth token expires periodically.
        """
        if self.database_url:
            await super().connect()
            return

        if not self.pool:

            async def create_connection(
                *_args: Any, **_kwargs: Any
            ) -> asyncpg.connection.Connection:
                "See asyncpg.connection.connect() for possible args and kwargs, which are configurable via create_pool()"
                logger.info("Creating new connection for pool")
                return await asyncpg.connect(get_database_url())

            self.pool = await asyncpg.create_pool(connect=create_connection)

    def _get_uuid_metadata(self, user: User) -> str | None:
        if "uuid" in user.metadata:
            return user.metadata["uuid"]
        return None

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        "Adapted from ChainlitDataLayer.create_user() to use uuid metadata as the id"
        query = """
        INSERT INTO "User" (id, identifier, metadata, "createdAt", "updatedAt")
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (identifier) DO UPDATE
        SET metadata = $3
        RETURNING *
        """
        now = await self.get_current_timestamp()
        params = {
            "id": self._get_uuid_metadata(user) or str(uuid.uuid4()),
            "identifier": user.identifier,
            "metadata": json.dumps(user.metadata),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.execute_query(query, params)
        row = result[0]

        return PersistedUser(
            id=str(row.get("id")),
            identifier=str(row.get("identifier")),
            createdAt=row.get("createdAt").isoformat(),  # type: ignore
            metadata=json.loads(row.get("metadata", "{}")),
        )
