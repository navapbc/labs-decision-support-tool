import asyncio
import json
import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from chainlit.chat_context import chat_context
from chainlit.context import context
from chainlit.data import get_data_layer
from chainlit.data.base import BaseDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from chainlit.data.literalai import LiteralDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.element import Element, ElementDict
from chainlit.logger import logger
from chainlit.message import Message
from chainlit.step import StepDict
from chainlit.types import Feedback, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User
from src.adapters.db.clients.postgres_config import PostgresDBConfig


def get_postgres_data_layer(database_url: str) -> "PostgresDataLayer":
    # See chainlit/data/__init__.py for storage_client options like S3
    storage_client = None
    return PostgresDataLayer(database_url=database_url, storage_client=storage_client)


def get_database_url() -> str:
    conf = PostgresDBConfig()
    return f"postgresql://{conf.username}:{conf.password}@{conf.host}:{conf.port}/{conf.name}?search_path={conf.db_schema}"


def get_literal_data_layer(api_key: str) -> LiteralDataLayer:
    server = os.environ.get("LITERAL_API_URL")
    return LiteralDataLayer(api_key=api_key, server=server)


def get_default_data_layers() -> List[BaseDataLayer]:
    data_layers: List[BaseDataLayer] = []
    if database_url := os.environ.get("DATABASE_URL", get_database_url()):
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
            "%r Custom Chainlit data layers: %s",
            self,
            [type(dl).__name__ for dl in self.data_layers],
        )
        assert self.data_layers, "No data layers initialized"

    async def _call_method(self, call_dl_func: Callable) -> List[Any]:
        # Create a list of tasks
        tasks = [asyncio.create_task(call_dl_func(dl)) for dl in self.data_layers]

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
        """
        Upon chainlit startup, a PersistedUser is created with a UUID.
        There's a discrepancy in the LiteralAI data layer where a user's identifier
        is being set to the user.id (a UUID) rather than user.identifier.
        Plus, LiteralAI's participant.id is a newly generated UUID.
        Looking at LiteralDataLayer.create_user(), it doesn't pass in a UUID.
        So rely on user.identifier and NOT the DB's User.id.

        When given an identifier, LiteralAI creates a new user.id (UUID) that is different
        from the one in the Postgres database. This causes issues since the Thread has a foreign
        key to the Postgres user.id.
        When a thread is created LiteralAI createa a new user with identifier=Postgres user.id
        and a new UUID user.id.

        Cannot set UUID via LiteralDataLayer.create_user(), but can set it via
        ChainlitDataLayer.create_user(). So call LiteralDataLayer.create_user() and
        use the UUID to call ChainlitDataLayer.create_user().
        """
        assert user.identifier, "User identifier is required"

        lai_dl = self.data_layers[1]
        assert isinstance(lai_dl, LiteralDataLayer)
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
        # Thread, Step, and Element records can be cross-referenced across data layers.
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
        database_url: str,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = False,
    ):
        super().__init__(
            database_url=database_url, storage_client=storage_client, show_logger=show_logger
        )

    def _get_uuid_metadata(self, user: User) -> str | None:
        if "uuid" in user.metadata:
            return user.metadata["uuid"]
        return None

    async def create_user(self, user: User) -> Optional[PersistedUser]:
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


# class Cl_Message(Message):  # pragma: no cover
#     """
#     Workaround to fix bug: https://github.com/Chainlit/chainlit/issues/2029
#     by simply adding `await` for data_layer calls
#     """

#     async def update(
#         self,
#     ) -> bool:
#         """
#         Update a message already sent to the UI.
#         """
#         if self.streaming:
#             self.streaming = False

#         step_dict = self.to_dict()
#         chat_context.add(self)

#         data_layer = get_data_layer()
#         if data_layer:
#             try:
#                 await data_layer.update_step(step_dict)
#             except Exception as e:
#                 if self.fail_on_persist_error:
#                     raise e
#                 logger.error(f"Failed to persist message update: {e!s}")

#         await context.emitter.update_step(step_dict)

#         return True

#     async def remove(self) -> bool:
#         """
#         Remove a message already sent to the UI.
#         """
#         chat_context.remove(self)
#         step_dict = self.to_dict()
#         data_layer = get_data_layer()
#         if data_layer:
#             try:
#                 await data_layer.delete_step(step_dict["id"])
#             except Exception as e:
#                 if self.fail_on_persist_error:
#                     raise e
#                 logger.error(f"Failed to persist message deletion: {e!s}")

#         await context.emitter.delete_step(step_dict)

#         return True

#     async def _create(self) -> StepDict:
#         step_dict = self.to_dict()
#         data_layer = get_data_layer()
#         if data_layer and not self.persisted:
#             try:
#                 await data_layer.create_step(step_dict)
#                 self.persisted = True
#             except Exception as e:
#                 if self.fail_on_persist_error:
#                     raise e
#                 logger.error(f"Failed to persist message creation: {e!s}")

#         return step_dict
