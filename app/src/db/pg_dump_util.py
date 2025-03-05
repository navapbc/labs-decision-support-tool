import argparse
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
from src.util.file_util import get_s3_client, replace_file_extension

logger = logging.getLogger(__name__)
# Configure logging since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def backup_db(dumpfilename: str, env) -> None:
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
        dated_filename = replace_file_extension(
            dumpfilename, f"-{datetime.now().strftime("%Y-%m-%d-%H_%M_%S")}.dump"
        )
        dest_path = f"pg_dumps/{dated_filename}"
        try:
            s3_client.upload_file(stdout_file, bucket, dest_path)
            logger.info("DB dump uploaded to s3://%s/%s", bucket, dest_path)
        except ClientError as e:
            logging.error(e)


def restore_db(dumpfilename: str, skip_truncate: bool, truncate_delay: int) -> None:
    if not os.path.exists(dumpfilename):
        logger.fatal("File %r not found; please set PG_DUMP_FILE to a valid file", dumpfilename)
        return

    config_dict = _get_db_config()
    _print_row_counts()

    if skip_truncate:
        logger.info("Skipping truncating tables; will attempt to append to existing data")
    else:
        if _truncate_db_tables(config_dict, truncate_delay):
            logger.info("Tables truncated")
        else:
            logger.fatal("Failed to truncate tables")
            return
        _print_row_counts()

    if not _pg_restore(config_dict, dumpfilename):
        logger.fatal("Failed to completely restore DB data from %r", dumpfilename)
    else:
        logger.info("DB data restored from %r", dumpfilename)

    _print_row_counts()


def main() -> None:
    env = os.environ.get("ENVIRONMENT", "local")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dumpfile", default=f"{env}_db.dump", help="dump file containing DB contents"
    )
    parser.add_argument(
        "--skip_truncate",
        action="store_true",
        help="don't truncate tables before restoring (default: false)",
    )
    parser.add_argument(
        "--truncate_delay",
        type=int,
        default=10,
        help="seconds to pause before truncating tables (default: 10)",
    )
    parser.add_argument("action", choices=["backup", "restore"], help="backup or restore DB")
    args = parser.parse_args(sys.argv[1:])

    logger.info("Running with args %r", args)
    sys.exit(111)

    if args.action == "backup":
        backup_db(args.dumpfile, env)
    elif args.action == "restore":
        restore_db(args.dumpfile, args.skip_truncate, args.truncate_delay)
    else:
        logger.fatal("Unknown action %r", args.action)


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


TRUNCATE_SQL = """DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public')
    LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;"""


def _truncate_db_tables(config_dict: dict[str, str], delay_seconds: int) -> bool:
    if delay_seconds:  # pragma: no cover
        logger.info(
            "Will clear out tables in %i seconds! Press Ctrl+C to cancel. (Use backup-db to backup data)",
            delay_seconds,
        )
        time.sleep(delay_seconds)
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
        TRUNCATE_SQL,
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
