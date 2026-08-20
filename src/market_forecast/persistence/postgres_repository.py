"""PostgreSQL adapter reusing the established market repository contract."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .sqlite_repository import SQLiteMarketRepository


class _CursorAdapter:
    """Normalize PostgreSQL result values to the legacy repository representation."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self) -> tuple[Any, ...] | None:
        row = self._cursor.fetchone()
        return _normalize_row(row) if row is not None else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [_normalize_row(row) for row in self._cursor.fetchall()]


class _ConnectionAdapter:
    """Expose the small connection surface used by SQLiteMarketRepository."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __enter__(self) -> "_ConnectionAdapter":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return bool(self._connection.__exit__(exc_type, exc, traceback))

    def close(self) -> None:
        self._connection.close()

    def execute(
        self, query: str, parameters: Iterable[Any] | None = None
    ) -> _CursorAdapter:
        postgres_query = query.replace("?", "%s")
        cursor = self._connection.execute(postgres_query, tuple(parameters or ()))
        return _CursorAdapter(cursor)


class PostgresMarketRepository(SQLiteMarketRepository):
    """Persist market data in PostgreSQL while preserving the SQLite contract."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        self.database_url = database_url
        # Some presentation code uses this label; it must never reveal credentials.
        self.database_path = Path("Neon PostgreSQL")

    def initialize(self) -> None:
        """Verify connectivity; schema migrations are managed separately."""

        with self._connect() as connection:
            row = connection.execute("SELECT 1").fetchone()
        if row != (1,):
            raise RuntimeError("PostgreSQL connectivity check failed")

    def _connect(self) -> _ConnectionAdapter:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - packaging guard
            raise RuntimeError("PostgreSQL support requires psycopg") from exc
        return _ConnectionAdapter(psycopg.connect(self.database_url))


def create_market_repository(
    database_path: Path, database_url: str | None = None
) -> SQLiteMarketRepository:
    """Create the configured repository, keeping SQLite as the safe default."""

    if database_url:
        return PostgresMarketRepository(database_url)
    return SQLiteMarketRepository(database_path)


def _normalize_row(row: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(_normalize_value(value) for value in row)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
