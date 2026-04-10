import asyncio
import json
import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

import asyncpg

from chainlit.data.base import BaseDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
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


def get_default_data_layers() -> List[BaseDataLayer]:
    data_layers: List[BaseDataLayer] = []

    # The primary data layer is always our Postgres DB
    database_url = os.environ.get("DATABASE_URL")
    data_layers.append(get_postgres_data_layer(database_url))

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

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        assert user.identifier, "User identifier is required"
        results = await self._call_method(lambda dl: dl.create_user(user))
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
        # Return the first non-empty result, or empty string if none
        return next((res for res in results if res), "")


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
            logger.info("New DB connection pool: idle_size=%r", self.pool.get_idle_size())

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
