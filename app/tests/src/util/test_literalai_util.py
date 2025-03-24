from datetime import datetime
from unittest.mock import MagicMock

import pytest
from literalai import Thread
from literalai.my_types import PageInfo

from src.util import literalai_util
from src.util.literalai_util import filter_between, get_project_id, get_users, query_threads_between

THREADS = [Thread(f"th_{i}") for i in range(18)]


class MockLiteralAIApi:
    def __init__(self):
        self.get_threads_counter = 0
        self.responses = [THREADS[:5], THREADS[5:10], THREADS[10:]]

    def get_my_project_id(self):
        return "Test_Project_1234ABC"

    def get_threads(self, *args, **kwargs):
        threads = self.responses[self.get_threads_counter]
        self.get_threads_counter += 1

        response = MagicMock()
        response.data = threads
        response.total_count = len(THREADS)
        response.page_info = PageInfo(
            has_next_page=(threads != self.responses[-1]),
            start_cursor=threads[0].id,
            end_cursor=threads[-1].id,
        )
        return response

    def get_users(self, *args, **kwargs):
        users = [MagicMock(id=f"user_{i}") for i in range(5)]

        response = MagicMock()
        response.data = users
        response.total_count = len(users)
        response.page_info = PageInfo(
            has_next_page=False,
            start_cursor=users[0].id,
            end_cursor=users[-1].id,
        )
        return response


@pytest.fixture
def literalai_client(monkeypatch):
    mock_lai_client = MagicMock()
    mock_lai_client.api = MockLiteralAIApi()
    monkeypatch.setattr(literalai_util, "client", lambda: mock_lai_client)


def test_get_project_id(literalai_client):
    assert get_project_id() == "Test_Project_1234ABC"


def test_query_threads(literalai_client):
    start_date = datetime.fromisoformat("2025-03-06")
    end_date = datetime.fromisoformat("2025-03-07")
    threads = query_threads_between(start_date, end_date)
    assert len(threads) == len(THREADS)


def test_get_users(literalai_client):
    start_date = datetime.fromisoformat("2025-03-06")
    end_date = datetime.fromisoformat("2025-03-07")
    filters = filter_between(start_date, end_date)
    users = get_users(filters)
    assert len(users) == 5
