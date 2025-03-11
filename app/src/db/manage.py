"""
This script adapts and combines manage.py and db.py (from infra/modules/database/role_manager)
into a single file that sets up the DB schema such that (1) it is as close to the deployed DB schema as possible
and (2) a backup of the deployed DB can be restored locally (via pg_dump_util.py),
i.e., the schema names must be the same.

This script is called as part of `make db-recreate`
Changes from the original manage.py are noted with the "LOCALSETUP" comment prefix -- in summary:
- Uses DB_USER as both the APP_USER and MIGRATOR_USER
- Connects to the DB as DB_USER (`db_connect_as_master_user()`)
- Ignores any setup for the rds_iam role
- Skips `configure_superuser_extensions()`

This script could be shortened but a decision was made to keep it as close to the original manage.py as possible
to make it easier to compare and update the script if changes were made to the original.
"""

import itertools
import os
from operator import itemgetter

from pg8000.native import Connection, identifier


def manage(config: dict) -> dict:
    """Manage database roles, schema, and privileges"""

    print("-- Running command 'manage' to manage database roles, schema, and privileges")
    with db_connect_as_master_user() as master_conn:
        print_current_db_config(master_conn)
        configure_database(master_conn, config)
        roles, schema_privileges = print_current_db_config(master_conn)
        roles_with_groups = get_roles_with_groups(master_conn)

    configure_default_privileges()

    return {
        "roles": roles,
        "roles_with_groups": roles_with_groups,
        "schema_privileges": {
            schema_name: schema_acl for schema_name, schema_acl in schema_privileges
        },
    }


def get_roles(conn: Connection) -> list[str]:
    return [
        row[0]
        for row in db_execute(
            conn,
            "SELECT rolname "
            "FROM pg_roles "
            "WHERE rolname NOT LIKE 'pg_%' "
            "AND rolname NOT LIKE 'rds%'",
            print_query=False,
        )
    ]


def get_roles_with_groups(conn: Connection) -> dict[str, str]:
    roles_groups = db_execute(
        conn,
        """
        SELECT u.rolname AS user, g.rolname AS group
        FROM pg_roles u
        INNER JOIN pg_auth_members a ON u.oid = a.member
        INNER JOIN pg_roles g ON g.oid = a.roleid
        ORDER BY user ASC
        """,
        print_query=False,
    )

    result = {}
    for user, groups in itertools.groupby(roles_groups, itemgetter(0)):
        result[user] = ",".join(map(itemgetter(1), groups))
    return result


# Get schema access control lists. The format of the ACLs is abbreviated. To interpret
# what the ACLs mean, see the Postgres documentation on Privileges:
# https://www.postgresql.org/docs/current/ddl-priv.html
def get_schema_privileges(conn: Connection) -> list[tuple[str, str]]:
    return [
        (row[0], row[1])
        for row in db_execute(
            conn,
            """
            SELECT nspname, nspacl
            FROM pg_namespace
            WHERE nspname NOT LIKE 'pg_%'
            AND nspname <> 'information_schema'
            """,
            print_query=False,
        )
    ]


def configure_database(conn: Connection, config: dict) -> None:
    print("-- Configuring database")
    app_username = os.environ.get("APP_USER")
    migrator_username = os.environ.get("MIGRATOR_USER")
    schema_name = os.environ.get("DB_SCHEMA")
    database_name = os.environ.get("DB_NAME")
    assert migrator_username
    assert app_username
    assert schema_name
    assert database_name

    # In Postgres 15 and higher, the CREATE privilege on the public
    # schema is already revoked/removed from all users except the
    # database owner. However, we are explicitly revoking access anyways
    # for projects that wish to use earlier versions of Postgres.
    print("---- Revoking default access on public schema")
    db_execute(conn, "REVOKE CREATE ON SCHEMA public FROM PUBLIC")

    print("---- Revoking database access from public role")
    db_execute(conn, f"REVOKE ALL ON DATABASE {identifier(database_name)} FROM PUBLIC")
    print(f"---- Setting default search path to schema {schema_name}")
    db_execute(
        conn,
        f"ALTER DATABASE {identifier(database_name)} SET search_path TO {identifier(schema_name)}",
    )

    configure_roles(conn, set([migrator_username, app_username]), database_name)
    configure_schema(conn, schema_name, migrator_username, app_username)
    # LOCALSETUP: Skip superuser extensions which are only needed for AWS setup
    # configure_superuser_extensions(conn, config["superuser_extensions"])


def configure_roles(conn: Connection, roles: set[str], database_name: str) -> None:
    print("---- Configuring roles")
    for role in roles:
        configure_role(conn, role, database_name)


def configure_role(conn: Connection, username: str, database_name: str) -> None:
    print(f"------ Configuring role: {username=}")
    # role = "rds_iam"
    db_execute(
        conn,
        f"""
        DO $$
        BEGIN
            CREATE USER {identifier(username)};
            EXCEPTION WHEN DUPLICATE_OBJECT THEN
            RAISE NOTICE 'user already exists';
        END
        $$;
        """,
    )
    # LOCALSETUP: Skip setup for the rds_iam role
    # db_execute(conn, f"GRANT {identifier(role)} TO {identifier(username)}")
    db_execute(
        conn,
        f"GRANT CONNECT ON DATABASE {identifier(database_name)} TO {identifier(username)}",
    )


def configure_schema(
    conn: Connection, schema_name: str, migrator_username: str, app_username: str
) -> None:
    print("---- Configuring schema")
    print(f"------ Creating schema: {schema_name=}")
    db_execute(conn, f"CREATE SCHEMA IF NOT EXISTS {identifier(schema_name)}")
    print(f"------ Changing schema owner: new_owner={migrator_username}")
    db_execute(
        conn,
        f"ALTER SCHEMA {identifier(schema_name)} OWNER TO {identifier(migrator_username)}",
    )
    print(f"------ Granting schema usage privileges: grantee={app_username}")
    db_execute(
        conn,
        f"GRANT USAGE ON SCHEMA {identifier(schema_name)} TO {identifier(app_username)}",
    )


def configure_default_privileges() -> None:
    """
    Configure default privileges so that future tables, sequences, and routines
    created by the migrator user can be accessed by the app user.
    You can only alter default privileges for the current role, so we need to
    run these SQL queries as the migrator user rather than as the master user.
    """
    # migrator_username = os.environ.get("MIGRATOR_USER")
    schema_name = os.environ.get("DB_SCHEMA")
    app_username = os.environ.get("APP_USER")
    # LOCALSETUP: Connect as master user instead of migrator_username
    with db_connect_as_master_user() as conn:
        print(f"------ Granting privileges for future objects in schema: grantee={app_username}")
        db_execute(
            conn,
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {identifier(schema_name)} GRANT ALL ON TABLES TO {identifier(app_username)}",
        )
        db_execute(
            conn,
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {identifier(schema_name)} GRANT ALL ON SEQUENCES TO {identifier(app_username)}",
        )
        db_execute(
            conn,
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {identifier(schema_name)} GRANT ALL ON ROUTINES TO {identifier(app_username)}",
        )


def print_current_db_config(
    conn: Connection,
) -> tuple[list[str], list[tuple[str, str]]]:
    print("-- Current database configuration")
    roles = get_roles(conn)
    print_roles(roles)
    schema_privileges = get_schema_privileges(conn)
    print_schema_privileges(schema_privileges)
    return roles, schema_privileges


def print_roles(roles: list[str]) -> None:
    print("---- Roles")
    for role in roles:
        print(f"------ Role {role}")


def print_schema_privileges(schema_privileges: list[tuple[str, str]]) -> None:
    print("---- Schema privileges")
    for name, acl in schema_privileges:
        print(f"------ Schema {name=} {acl=}")


### The following was adapted from infra/modules/database/role_manager/db.py


def db_connect_as_master_user() -> Connection:
    user = os.environ["DB_USER"]
    host = os.environ["DB_HOST"]
    port = os.environ["DB_PORT"]
    database = os.environ["DB_NAME"]
    password = os.environ["DB_PASSWORD"]

    print(f"Connecting to database: {user=} {host=} {port=} {database=}")
    return Connection(
        user=user,
        host=host,
        port=port,
        database=database,
        password=password,
        # LOCALSETUP: SSL is not used in local setup
        # ssl_context=True,
    )


def db_execute(conn: Connection, query: str, print_query: bool = True) -> list:
    if print_query:
        print(f"{conn.user.decode('utf-8')}> {query}")
    return conn.run(query)


if __name__ == "__main__":
    # These should be set in local.env
    assert os.environ["DB_USER"]
    assert os.environ.get("DB_SCHEMA")
    assert os.environ.get("DB_NAME")

    os.environ["DB_PORT"] = os.environ.get("DB_PORT", "5432")
    os.environ["APP_USER"] = os.environ["DB_USER"]
    os.environ["MIGRATOR_USER"] = os.environ["DB_USER"]

    manage({})
