import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from io import TextIOWrapper
from subprocess import CalledProcessError
from typing import Optional, Sequence

from botocore.exceptions import ClientError

from src.adapters.db.clients import postgres_client, postgres_config
from src.app_config import app_config
from src.db.models import conversation, document
from src.util.file_util import get_s3_client

logger = logging.getLogger(__name__)
# Print INFO messages since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def backup_db() -> None:
    env = os.environ.get("ENVIRONMENT", "local")
    dumpfilename = os.environ.get("PG_DUMP_FILE", f"{env}_db.dump")
    if os.path.exists(dumpfilename):
        logger.fatal(
            "File %r already exists; please delete it first or set PG_DUMP_FILE to a nonexistent file",
            dumpfilename,
        )
        return

    config_dict = _get_db_config()
    _print_row_counts()

    # In local environments, write to the current directory
    if env == "local":
        if not _pg_dump(config_dict, dumpfilename):
            logger.fatal("Failed to dump DB data to %r", dumpfilename)
            return

        logger.info("DB data dumped to %r", dumpfilename)
        logger.info("Skipping S3 upload since running in local environment")
        return

    # In deployed environments, write to (writeable) temp directory and upload to S3
    with tempfile.TemporaryDirectory() as tmpdirname:
        logger.info("Created temporary directory: %r", tmpdirname)
        stdout_file = f"{tmpdirname}/{dumpfilename}"
        # In case dumpfilename is a path, create the parent directories
        os.makedirs(os.path.dirname(stdout_file), exist_ok=True)

        if not _pg_dump(config_dict, stdout_file):
            logger.fatal("Failed to dump DB data to %r", stdout_file)
            return

        s3_client = get_s3_client()
        bucket = os.environ.get("BUCKET_NAME", f"decision-support-tool-app-{env}")
        dated_filename = _replace_extension(
            dumpfilename, f"-{datetime.now().strftime("%Y-%m-%d-%H_%M_%S")}.dump"
        )
        dest_path = f"pg_dumps/{dated_filename}"
        try:
            s3_client.upload_file(stdout_file, bucket, dest_path)
            logger.info("DB dump uploaded to s3://%s/%s", bucket, dest_path)
        except ClientError as e:
            logging.error(e)


def _replace_extension(filename: str, new_extension: str) -> str:
    base_name, _ = os.path.splitext(filename)
    return base_name + new_extension


TRUE_STRINGS = ["true", "1", "t", "y", "yes"]


def restore_db() -> None:
    dumpfilename = os.environ.get("PG_DUMP_FILE", "db.dump")
    if not os.path.exists(dumpfilename):
        logger.fatal("File %r not found; please set PG_DUMP_FILE to a valid file", dumpfilename)
        return

    config_dict = _get_db_config()
    _print_row_counts()

    truncate_tables = os.environ.get("TRUNCATE_TABLES", "True").strip().lower() in TRUE_STRINGS
    if truncate_tables:
        delay = "TRUNCATE_TABLES" not in os.environ
        if _truncate_db_tables(config_dict, delay):
            logger.info("Tables truncated")
        else:
            logger.fatal("Failed to truncate tables")
            return
        _print_row_counts()
    else:
        logger.info("Skipping truncating tables; will attempt to append to existing data")

    if not _pg_restore(config_dict, dumpfilename):
        logger.fatal("Failed to completely restore DB data from %r", dumpfilename)
    else:
        logger.info("DB data restored from %r", dumpfilename)

    _print_row_counts()


def _run_command(
    command: Sequence[str], stdout_file: Optional[TextIOWrapper] = None
) -> bool:  # pragma: no cover
    try:
        logger.info("Running: %r", " ".join(command))
        if stdout_file:
            result = subprocess.run(command, check=True, stdout=stdout_file)
        else:
            # capture_output=True ensures that both stdout and stderr are captured.
            # check=True causes CalledProcessError when the command fails.
            result = subprocess.run(command, capture_output=True, check=True)

        if stdout_file:
            logger.info("Output written to %r", stdout_file.name)
        elif result.stdout:
            logger.info("Stdout: %s", result.stdout.decode("utf-8").strip())
        return True
    except FileNotFoundError:
        logger.fatal("pg_dump not found. Please install postgresql or postgresql-client v16+.")
        return False
    except CalledProcessError as e:
        logger.fatal("Error: Command failed with return code %r", e.returncode)
        logger.fatal("Stderr:\n%s", e.stderr.decode("utf-8").strip())
        return False


def _get_db_config() -> dict[str, str]:
    config_dict = postgres_client.get_connection_parameters(postgres_config.get_db_config())
    if not config_dict["password"]:  # pragma: no cover
        logger.fatal("DB password is not set")
        sys.exit(2)
    return config_dict


def _pg_dump(config_dict: dict[str, str], stdout_file: str) -> bool:
    with open(stdout_file, "w", encoding="utf-8") as dumpfile:
        # PGPASSWORD is used by pg_dump
        os.environ["PGPASSWORD"] = config_dict["password"]
        command = [
            "pg_dump",
            "--data-only",
            "--format=c",
            "-U",
            config_dict["user"],
            "-h",
            config_dict["host"],
            config_dict["dbname"],
        ]
        return _run_command(command, dumpfile)


def _truncate_db_tables(config_dict: dict[str, str], delay: bool) -> bool:
    if delay:  # pragma: no cover
        logger.info(
            "Will clear out tables in 10 seconds! Press Ctrl+C to cancel. (Use backup-db to backup data)"
        )
        time.sleep(10)
    logger.info("Clearing out tables")
    # PGPASSWORD is used by psql
    os.environ["PGPASSWORD"] = config_dict["password"]
    command = [
        "psql",
        "-U",
        config_dict["user"],
        "-h",
        config_dict["host"],
        "-d",
        config_dict["dbname"],
        "-c",
        "TRUNCATE TABLE alembic_version, user_session, chat_message, document CASCADE;",
    ]
    return _run_command(command)


def _pg_restore(config_dict: dict[str, str], dumpfilename: str) -> bool:
    # PGPASSWORD is used by pg_restore
    os.environ["PGPASSWORD"] = config_dict["password"]
    command = [
        "pg_restore",
        "-U",
        config_dict["user"],
        "-h",
        config_dict["host"],
        "-d",
        config_dict["dbname"],
        dumpfilename,
    ]
    return _run_command(command)


def _print_row_counts() -> None:
    with app_config.db_session() as db_session:
        for table in [
            document.Document,
            document.Chunk,
            conversation.UserSession,
            conversation.ChatMessage,
        ]:
            count = db_session.query(table).count()
            logger.info("Table %r has %d rows", table.__tablename__, count)
