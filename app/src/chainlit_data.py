import asyncio
import os
from typing import Callable, Dict, List, Optional, Sequence

from chainlit.data.base import BaseDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from chainlit.data.literalai import LiteralDataLayer
from chainlit.data.utils import queue_until_user_message
from chainlit.element import Element, ElementDict
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import Feedback, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User


def get_postgres_data_layer(database_url: str) -> ChainlitDataLayer:
    # See chainlit/data/__init__.py for storage_client options like S3
    storage_client = None
    return ChainlitDataLayer(database_url=database_url, storage_client=storage_client)


def get_literal_data_layer(api_key: str) -> LiteralDataLayer:
    server = os.environ.get("LITERAL_API_URL")
    return LiteralDataLayer(api_key=api_key, server=server)


def get_default_data_layers() -> List[BaseDataLayer]:
    data_layers: List[BaseDataLayer] = []
    if database_url := os.environ.get("DATABASE_URL"):
        data_layers.append(get_postgres_data_layer(database_url))
    if api_key := os.environ.get("LITERAL_API_KEY"):
        data_layers.append(get_literal_data_layer(api_key))
    logger.info("Data layers initialized: %s", data_layers)
    return data_layers


class ChainlitPolyDataLayer(BaseDataLayer):
    def __init__(self, data_layers: Optional[Sequence[BaseDataLayer]]) -> None:
        """
        The first data layer is the primary one, and returned values will be from that layer.
        Failures in other data layers are ignored.
        """
        logger.info("Custom Chainlit data layer initialized")
        self.data_layers = data_layers or get_default_data_layers()
        assert self.data_layers, "No data layers initialized"

    async def _call_method(self, call_dl_func: Callable, dls_to_skip: Sequence[BaseDataLayer] = []) -> List[Optional]:
        # Create a list of tasks
        tasks = [asyncio.create_task(call_dl_func(dl)) for dl in self.data_layers if dl not in dls_to_skip]

        # Gather results from all tasks
        return await asyncio.gather(*tasks)

    async def get_user(self, identifier: str) -> Optional["PersistedUser"]:
        results = await self._call_method(lambda dl: dl.get_user(identifier))
        return results[0]

    async def create_user(self, user: "User") -> Optional["PersistedUser"]:
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
    async def create_element(self, element: "Element") -> Optional["ElementDict"]:
        elem_dict = self.data_layers[0].create_element(element)
        created_elem = Element.from_dict(elem_dict)
        await self._call_method(lambda dl: dl.create_element(created_elem), dls_to_skip=[self.data_layers[0]])
        return elem_dict

    async def get_element(self, thread_id: str, element_id: str) -> Optional["ElementDict"]:
        results = await self._call_method(lambda dl: dl.get_element(thread_id, element_id))
        return results[0]

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        results = await self._call_method(lambda dl: dl.delete_element(element_id, thread_id))
        return results[0]

    @queue_until_user_message()
    async def create_step(self, step_dict: "StepDict"):
        results = await self._call_method(lambda dl: dl.create_step(step_dict))
        return results[0]

    @queue_until_user_message()
    async def update_step(self, step_dict: "StepDict"):
        results = await self._call_method(lambda dl: dl.update_step(step_dict))
        return results[0]

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        results = await self._call_method(lambda dl: dl.delete_step(step_id))
        return results[0]

    async def get_thread_author(self, thread_id: str) -> str:
        results = await self._call_method(lambda dl: dl.get_thread_author(thread_id))
        return results[0]

    async def delete_thread(self, thread_id: str):
        results = await self._call_method(lambda dl: dl.delete_thread(thread_id))
        return results[0]

    async def list_threads(
        self, pagination: "Pagination", filters: "ThreadFilter"
    ) -> "PaginatedResponse[ThreadDict]":
        results = await self._call_method(lambda dl: dl.list_threads(pagination, filters))
        return results[0]

    async def get_thread(self, thread_id: str) -> "Optional[ThreadDict]":
        results = await self._call_method(lambda dl: dl.get_thread(thread_id))
        return results[0]

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        results = await self._call_method(
            lambda dl: dl.update_thread(thread_id, name, user_id, metadata, tags)
        )
        return results[0]

    async def build_debug_url(self) -> str:
        results = await self._call_method(lambda dl: dl.build_debug_url())
        # ChainlitDataLayer.build_debug_url() returns "" which isn't useful
        return next(res for res in results if res)
