"""Repair Alembic version tracking when app tables exist but alembic_version is missing."""

import logging
import sys

from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db.schema import quoted_schema, target_schema

logger = logging.getLogger(__name__)

ALEMBIC_HEAD = "h1b2c3d4e5f6"


def _schema_has_app_tables(connection, schema: str | None) -> bool:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names(schema=schema))
    return "users" in tables and "knowledge_bases" in tables


def _read_alembic_version(connection, schema: str | None) -> str | None:
    inspector = inspect(connection)
    if schema:
        if "alembic_version" not in inspector.get_table_names(schema=schema):
            return None
        qschema = quoted_schema(schema)
        row = connection.execute(
            text(f"SELECT version_num FROM {qschema}.alembic_version LIMIT 1")
        ).scalar()
        return row

    if "alembic_version" not in inspector.get_table_names():
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()


def _write_alembic_version(connection, schema: str | None, revision: str) -> None:
    if schema:
        qschema = quoted_schema(schema)
        connection.execute(text(f"SET search_path TO {qschema}, public"))
        connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {qschema}.alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                ")"
            )
        )
        connection.execute(text(f"DELETE FROM {qschema}.alembic_version"))
        connection.execute(
            text(
                f"INSERT INTO {qschema}.alembic_version (version_num) "
                "VALUES (:revision)"
            ),
            {"revision": revision},
        )
    else:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                ")"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
    connection.commit()


def repair_alembic_version(force_stamp: bool = False) -> bool:
    """
    Ensure Alembic version tracking matches an already-initialized database.

    Returns True when no further repair is required.
    """
    schema = target_schema()
    engine = create_engine(
        settings.get_database_url,
        connect_args=settings.postgres_connect_args,
    )

    with engine.connect() as connection:
        has_tables = _schema_has_app_tables(connection, schema)
        current_version = _read_alembic_version(connection, schema)

        if current_version == ALEMBIC_HEAD and not force_stamp:
            logger.info("Alembic already at head (%s)", ALEMBIC_HEAD)
            return True

        if not has_tables:
            logger.info("App tables not found; Alembic will run normal migrations")
            return True

        if current_version and current_version != ALEMBIC_HEAD and not force_stamp:
            logger.info(
                "Alembic version is %s; leaving upgrade flow to Alembic",
                current_version,
            )
            return True

        logger.warning(
            "Repairing Alembic version in %s (current=%s, target=%s)",
            schema or "public",
            current_version or "missing",
            ALEMBIC_HEAD,
        )
        _write_alembic_version(connection, schema, ALEMBIC_HEAD)

    logger.info("Alembic version repaired to %s", ALEMBIC_HEAD)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    force = "--force-stamp" in sys.argv
    repair_alembic_version(force_stamp=force)
