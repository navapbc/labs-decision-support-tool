import argparse
import functools
import json
import logging
import os
import pickle
import sys
from datetime import datetime
from typing import Any, Callable

from literalai import LiteralClient, Thread, User
from literalai.my_types import PaginatedResponse
from literalai.observability.filter import Filter, OrderBy
from smart_open import open as smart_open

from src.app_config import app_config

logger = logging.getLogger(__name__)


@functools.cache
def client() -> LiteralClient:  # pragma: no cover
    if app_config.literal_api_key_for_api:
        return LiteralClient(api_key=app_config.literal_api_key_for_api)
    return LiteralClient()


def get_project_id() -> str:
    return client().api.get_my_project_id()


def get_threads(filters: list[Filter]) -> list[Thread]:
    logger.info("Query filter: %r", filters)
    order_by: OrderBy = OrderBy(column="createdAt", direction="ASC")
    return get_all_entities(
        lambda client, after: client.api.get_threads(
            filters=filters, order_by=order_by, after=after
        )
    )


def get_users(filters: list[Filter]) -> list[User]:
    return get_all_entities(
        lambda lai_client, after: lai_client.api.get_users(filters=filters, after=after)
    )


def get_all_entities[T](api_call: Callable[[LiteralClient, Any], PaginatedResponse[T]]) -> list[T]:
    lai_client = client()
    entities = []
    after = None
    while True:
        response = api_call(lai_client, after)
        after = response.page_info.end_cursor
        entities += response.data
        logger.info("Got %r of %r total entities", len(entities), response.total_count)
        if not response.page_info.has_next_page:
            assert (
                len(entities) == response.total_count
            ), f"Expected {response.total_count} entities, but got only {len(entities)}"
            return entities


def query_threads_between(start_date: datetime, end_date: datetime) -> list[Thread]:
    return get_threads(filter_between(start_date, end_date))


def filter_between(start_date: datetime, end_date: datetime) -> list[Filter]:
    return [
        Filter(field="createdAt", operator="gte", value=start_date.isoformat()),
        Filter(field="createdAt", operator="lt", value=end_date.isoformat()),
    ]


def query_untagged_threads(user_ids: list[str]) -> list[Thread]:
    filters: list[Filter] = [
        Filter(field="participantIdentifiers", operator="in", value=user_ids),
        Filter(field="tags", operator="is", value=None),
    ]
    return get_threads(filters)


def tag_threads_by_user(
    threads: list[Thread], user2tag: dict[str, str]
) -> None:  # pragma: no cover
    lai_client = client()
    for th in threads:
        assert (
            th.participant_identifier in user2tag
        ), f"Missing tag for user {th.participant_identifier}"
        new_tag = user2tag[th.participant_identifier]
        lai_client.api.update_thread(th.id, tags=[new_tag])
        logger.info("Tagged thread %r with %r", th.id, new_tag)


def save_entities(
    entities: list[Thread] | list[User], basefilename: str
) -> None:  # pragma: no cover
    with open(f"{basefilename}.pickle", "wb") as file:
        logger.info("Saving to %s.pickle", basefilename)
        pickle.dump(entities, file)
    with open(f"{basefilename}.json", "w", encoding="utf-8") as f:
        # Also save as JSON for readability and in case the Thread object changes
        logger.info("Saving to %s.json", basefilename)
        dicts = [e.to_dict() for e in entities]
        f.write(json.dumps(dicts, indent=2))


def load_threads(basefilename: str) -> list[Thread] | Any:  # pragma: no cover
    if os.path.exists(f"{basefilename}.pickle"):
        # Prefer to load from pickle file since it loads Thread objects
        logger.info("Loading from %s.pickle", basefilename)
        with open(f"{basefilename}.pickle", "rb") as file:
            return pickle.load(file)  # nosec
    elif os.path.exists(f"{basefilename}.json"):
        logger.info("Loading from %s.json", basefilename)
        with open(f"{basefilename}.json", "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        raise FileNotFoundError(f"Could not find {basefilename}.json or {basefilename}.pickle")


def archive_threads() -> None:  # pragma: no cover
    # Configure logging since this function is run directly
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("start", help="(inclusive) beginning datetime of threads to download")
    parser.add_argument("end", help="(exclusive) end datetime of threads to download")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    start_date = datetime.fromisoformat(args.start)
    end_date = datetime.fromisoformat(args.end)

    project_id = get_project_id()
    logger.info("Project ID: %r", project_id)

    prefix = f"{project_id}-{start_date.strftime('%Y-%m-%d')}-{end_date.strftime('%Y-%m-%d')}"

    filters = filter_between(start_date, end_date)
    threads = get_threads(filters)
    save_entities(threads, f"{prefix}-threads-archive")
    users = get_users(filters)
    save_entities(users, f"{prefix}-users-archive")

    logger.info("REMINDER: Upload the JSON file to the 'LiteralAI logs' Google Drive folder")


def tag_threads() -> None:  # pragma: no cover
    # Configure logging since this function is run directly
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only query; don't update threads")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    env = os.environ.get("ENVIRONMENT")
    bucket_name = os.environ.get("BUCKET_NAME")
    if env == "local" and not bucket_name:
        input_json = "literalai_user_tags.json"
        if not os.path.exists(input_json):
            logger.error("Missing input file %r. Download from S3.", input_json)
            sys.exit(4)
    else:
        bucket = bucket_name or f"decision-support-tool-app-{env}"
        input_json = f"s3://{bucket}/literalai_user_tags.json"

    logger.info("Using file: %r", input_json)
    with smart_open(input_json, "r", encoding="utf-8") as f:
        user_objs = json.load(f)
    user2tag = {u["user_id"]: u["tag"] for u in user_objs}
    logger.info(user2tag)

    project_id = get_project_id()
    logger.info("Project ID: %r", project_id)
    if threads := query_untagged_threads(list(user2tag)):
        for th in threads:
            logger.info("%s (%s) %s %r", th.id, th.created_at, th.participant_identifier, th.tags)
        if not args.dry_run:
            tag_threads_by_user(threads, user2tag)
