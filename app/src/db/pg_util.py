import logging
import os
import subprocess
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
# Print INFO messages since this is often run from the terminal during local development
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def run_command(command: Sequence[str], stdout_file: Optional[TextIOWrapper] = None) -> bool:
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
        logger.fatal("Stderr:\n%s", e.stderr)
        return False


def pg_dump() -> None:
    dumpfilename = os.environ.get("PG_DUMP_FILE", "db.dump")
    if os.path.exists(dumpfilename):
        logger.fatal(
            "File %r already exists; please delete it first or set PG_DUMP_FILE to a nonexistent file",
            dumpfilename,
        )
        return

    config_dict = postgres_client.get_connection_parameters(postgres_config.get_db_config())
    if not config_dict["password"]:
        logger.fatal("DB password is not set")
        return

    print_row_counts()

    env = os.environ.get("ENVIRONMENT", "local")
    # In local environments, write to the current directory.
    # In deployed environments, write to /tmp/ since it is writeable.
    stdout_file = dumpfilename if env == "local" else f"/tmp/{dumpfilename}"
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
        run_command(command, dumpfile)
    logger.info("DB data dumped to %r", stdout_file)

    if env == "local":
        logger.info("Skipping S3 upload since running in local environment")
    else:
        s3_client = get_s3_client()
        bucket = os.environ.get("BUCKET_NAME", f"decision-support-tool-app-{env}")
        dest_path = f"pg_dumps/{datetime.now().strftime("%Y-%m-%d-%H_%M_%S")}-{dumpfilename}"
        try:
            s3_client.upload_file(stdout_file, bucket, dest_path)
            logger.info("DB dump uploaded to s3://%s/%s", bucket, dest_path)
        except ClientError as e:
            logging.error(e)


TRUE_STRINGS = ["true", "1", "t", "y", "yes"]


def pg_restore() -> None:
    dumpfilename = os.environ.get("PG_DUMP_FILE", "db.dump")
    if not os.path.exists(dumpfilename):
        logger.fatal("File %r not found; please set PG_DUMP_FILE to a valid file", dumpfilename)
        return

    config_dict = postgres_client.get_connection_parameters(postgres_config.get_db_config())
    if not config_dict["password"]:
        logger.fatal("DB password is not set")
        return

    # PGPASSWORD is used by psql and pg_restore
    os.environ["PGPASSWORD"] = config_dict["password"]

    print_row_counts()

    truncate_tables = os.environ.get("TRUNCATE_TABLES", "True").strip().lower() in TRUE_STRINGS
    if truncate_tables:
        if "TRUNCATE_TABLES" not in os.environ:
            logger.info(
                "Will clear out tables in 10 seconds! Press Ctrl+C to cancel. (Use pg_dump to backup data)"
            )
            time.sleep(10)
        logger.info("Clearing out tables")
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
        if run_command(command):
            logger.info("Tables truncated")
        else:
            logger.fatal("Failed to truncate tables")
            return
    else:
        logger.info("Skipping truncating tables; will attempt to append to existing data")

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
    if not run_command(command):
        logger.fatal("Failed to completely restore DB data from %r", dumpfilename)
        return

    print_row_counts()


def print_row_counts() -> None:
    with app_config.db_session() as db_session:
        for table in [
            document.Document,
            document.Chunk,
            conversation.UserSession,
            conversation.ChatMessage,
        ]:
            count = db_session.query(table).count()
            logger.info("Table %r has %d rows", table.__tablename__, count)
