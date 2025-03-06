import argparse
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from subprocess import CalledProcessError
from textwrap import dedent
from typing import Any, Optional, Sequence

from smart_open import open as smart_open

from src.adapters.db.clients import postgres_client, postgres_config
from src.app_config import app_config
from src.db.models import conversation, document
from src.util.file_util import replace_file_extension

logger = logging.getLogger(__name__)
# Configure logging since this file is run directly
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def backup_db(dumpfilename: str, env: str) -> None:
    if env == "local":
        logger.info("Skipping S3 upload since running in local environment")
    else:
        # In not local environment, write to a specific S3 bucket and folder
        bucket = os.environ.get("BUCKET_NAME", f"decision-support-tool-app-{env}")
        dated_filename = replace_file_extension(
            dumpfilename, f"-{datetime.now().strftime("%Y-%m-%d-%H_%M_%S")}.dump"
        )
        dumpfilename = f"s3://{bucket}/pg_dumps/{dated_filename}"

    if file_exists(dumpfilename):
        logger.fatal(
            "File %r already exists; delete or move it first or specify a different file using --dumpfile",
            dumpfilename,
        )
        return

    _print_row_counts()
    logger.info("Writing DB dump to %r", dumpfilename)
    config_dict = _get_db_config()
    if not _pg_dump(config_dict, dumpfilename):
        logger.fatal("Failed to dump DB data to %r", dumpfilename)
        return
    logger.info("DB data dumped to %r", dumpfilename)


def restore_db(dumpfilename: str, skip_truncate: bool, truncate_delay: int) -> None:
    if not os.path.exists(dumpfilename):
        logger.fatal("File %r not found", dumpfilename)
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


def main() -> None:  # pragma: no cover
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
    if args.action == "backup":
        backup_db(args.dumpfile, env)
    elif args.action == "restore":
        restore_db(args.dumpfile, args.skip_truncate, args.truncate_delay)
    else:
        logger.fatal("Unknown action %r", args.action)


def file_exists(uri: str) -> bool:
    try:
        with smart_open(uri, "rb"):
            return True
    except Exception:
        return False


def _run_command(
    command: Sequence[str], stdout_file: Optional[Any] = None
) -> bool:  # pragma: no cover
    try:
        logger.info("Running: %r", " ".join(command))
        if stdout_file:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            outs, errs = proc.communicate()
            if proc.returncode > 0:
                logger.error("Error: Command failed with return code %r", proc.returncode)
                logger.error("Stderr:\n%s", errs.decode("utf-8").strip())
                return False
            stdout_file.write(outs)
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
    with smart_open(stdout_file, "wb") as dumpfile:
        # PGPASSWORD is used by pg_dump
        os.environ["PGPASSWORD"] = config_dict["password"]
        # Unit test sets DB_SCHEMA to avoid affecting the real DB
        schema = _get_schema_name()
        command = [
            "pg_dump",
            "--data-only",
            "--format=c",
            "-U",
            config_dict["user"],
            "-h",
            config_dict["host"],
            "--schema",
            schema,
            config_dict["dbname"],
        ]
        return _run_command(command, dumpfile)


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
    # Unit test sets DB_SCHEMA to avoid affecting the real DB
    schema = _get_schema_name()
    sql_str = dedent(
        f"""DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = {schema!r})
            LOOP
                EXECUTE 'TRUNCATE TABLE {schema}.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;"""  # nosec
    )
    command = [
        "psql",
        "-U",
        config_dict["user"],
        "-h",
        config_dict["host"],
        "-d",
        config_dict["dbname"],
        "-c",
        sql_str,
    ]
    return _run_command(command)


def _pg_restore(config_dict: dict[str, str], dumpfilename: str) -> bool:
    # PGPASSWORD is used by pg_restore
    os.environ["PGPASSWORD"] = config_dict["password"]
    # Unit test sets DB_SCHEMA to avoid affecting the real DB
    schema = _get_schema_name()
    command = [
        "pg_restore",
        "-U",
        config_dict["user"],
        "-h",
        config_dict["host"],
        "-d",
        config_dict["dbname"],
        "--schema",
        schema,
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


def _get_schema_name() -> str:
    schema = os.environ.get("DB_SCHEMA", "public")
    # This gets passed to subprocess.Popen, so first validate
    # that it only contains expected characters
    if not re.match(r"^[a-zA-Z0-9_]+$", schema):
        logger.fatal("Invalid schema name")
        sys.exit(2)
    return schema
