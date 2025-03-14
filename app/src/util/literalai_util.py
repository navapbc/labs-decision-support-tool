import argparse
import functools
import json
import logging
import os
import pickle
import sys
from datetime import datetime
from typing import Any

from literalai import LiteralClient, Thread
from literalai.observability.filter import Filter, OrderBy

from src.app_config import app_config

logger = logging.getLogger(__name__)


@functools.cache
def client() -> LiteralClient:  # pragma: no cover
    if app_config.literal_api_key_for_api:
        return LiteralClient(api_key=app_config.literal_api_key_for_api)
    return LiteralClient()


def get_project_id() -> str:
    lai_client = client()
    return lai_client.api.get_my_project_id()


def get_threads(filters: list[Filter]) -> list[Thread]:
    logger.info("Query filter: %r", filters)
    order_by: OrderBy = OrderBy(column="createdAt", direction="ASC")

    lai_client = client()
    threads = []
    after = None
    while True:
        response = lai_client.api.get_threads(filters=filters, order_by=order_by, after=after)
        after = response.page_info.end_cursor
        threads += response.data
        logger.info("Got %r of %r total threads", len(threads), response.total_count)
        if not response.page_info.has_next_page:
            assert (
                len(threads) == response.total_count
            ), f"Expected {response.total_count} threads, but got only {len(threads)}"
            return threads


def query_threads_between(start_date: datetime, end_date: datetime) -> list[Thread]:
    filters: list[Filter] = [
        Filter(field="createdAt", operator="gte", value=start_date.isoformat()),
        Filter(field="createdAt", operator="lt", value=end_date.isoformat()),
    ]
    return get_threads(filters)


def query_untagged_threads(user_ids: list[str]) -> list[Thread]:
    filters: list[Filter] = [
        Filter(field="participantIdentifiers", operator="in", value=user_ids),
        Filter(field="tags", operator="is", value=None),
    ]
    return get_threads(filters)


def tag_threads_by_user(threads: list[Thread], user2tag: dict[str, str]) -> None:
    lai_client = client()
    for th in threads:
        assert (
            th.participant_identifier in user2tag
        ), f"Missing tag for user {th.participant_identifier}"
        new_tag = user2tag[th.participant_identifier]
        lai_client.api.update_thread(th.id, tags=[new_tag])
        logger.info("Tagged thread %r with %r", th.id, new_tag)


def save_threads(threads: list[Thread], basefilename: str) -> None:  # pragma: no cover
    with open(f"{basefilename}.pickle", "wb") as file:
        logger.info("Saving to %s.pickle", basefilename)
        pickle.dump(threads, file)
    with open(f"{basefilename}.json", "w", encoding="utf-8") as f:
        # Also save as JSON for readability and in case the Thread object changes
        logger.info("Saving to %s.json", basefilename)
        thread_dicts = [thread.to_dict() for thread in threads]
        f.write(json.dumps(thread_dicts, indent=2))


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
    threads = query_threads_between(start_date, end_date)
    save_threads(
        threads,
        f"{project_id}-archive-{start_date.strftime('%Y-%m-%d')}-{end_date.strftime('%Y-%m-%d')}",
    )
    logger.info("REMINDER: Upload the JSON file to the 'LiteralAI logs' Google Drive folder")


def tag_threads() -> None:  # pragma: no cover
    # Configure logging since this function is run directly
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only query; don't update threads")
    args = parser.parse_args(sys.argv[1:])
    logger.info("Running with args %r", args)

    input_json = "literalai_user_tags.json"
    if not os.path.exists(input_json):
        logger.error(
            "Missing input file %r. Download from the 'LiteralAI logs' Google Drive folder.",
            input_json,
        )
        sys.exit(4)

    with open(input_json, "r", encoding="utf-8") as f:
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
