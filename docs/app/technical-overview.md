# Technical Overview

- [Key Technologies](#key-technologies)

## Key Technologies

The application is built on Chainlit, using Postgres with the pgvector extension for vectors (embeddings).

SQLAlchemy is the ORM, with migrations driven by Alembic. pydantic is used in
many spots for parsing data (and often serializing it to json or plain
dictionaries). Where pydantic is not used, plain Python dataclasses are
generally preferred.

- [SQLAlchemy][sqlalchemy-home] ([source code][sqlalchemy-src])
- [Alembic][alembic-home] ([source code][alembic-src])
- [pydantic][pydantic-home] ([source code][pydantic-src])
- [poetry](https://python-poetry.org/docs/) - Python dependency management

[pydantic-home]:https://pydantic-docs.helpmanual.io/
[pydantic-src]: https://github.com/samuelcolvin/pydantic/

[sqlalchemy-home]: https://www.sqlalchemy.org/
[sqlalchemy-src]: https://github.com/sqlalchemy/sqlalchemy

[alembic-home]: https://alembic.sqlalchemy.org/en/latest/
[alembic-src]: https://github.com/sqlalchemy/alembic