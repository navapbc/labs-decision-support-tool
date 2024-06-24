"""
Database module.

This module contains the DBClient class, which is used to manage database connections.
This module can be used on its own or with an application framework such as Flask.

Usage:
    import src.adapters.db as db

    db_client = db.PostgresDBClient()

    # non-ORM style usage
    with db_client.get_connection() as conn:
        conn.execute(...)

    # ORM style usage
    with db_client.get_session() as session:
        session.query(...)
        with session.begin():
            session.add(...)
"""

# Re-export for convenience
from src.adapters.db.client import Connection, DBClient, Session
from src.adapters.db.clients.postgres_client import PostgresDBClient

__all__ = ["Connection", "DBClient", "Session", "PostgresDBClient"]
