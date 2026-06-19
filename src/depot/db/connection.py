"""pyodbc connection factory. Read = ICMS, write = insert-target DB (archeet /
prod via env). Helper to chunk IN(...) queries at chunk_size."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable, Iterator

from ..settings import get_settings


def _conn_str(database: str) -> str:
    s = get_settings()
    server = s.icms_server()
    user = os.environ.get("ICMS_DB_USER", "")
    password = os.environ.get("ICMS_DB_PASSWORD", "")
    return (
        f"DRIVER={{{s.icms_db.driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};TrustServerCertificate=yes;"
    )


def _connect(database: str):
    import pyodbc
    return pyodbc.connect(_conn_str(database), autocommit=False)


@contextmanager
def read_connection():
    conn = _connect(get_settings().icms_db.database)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write_connection():
    db = os.environ.get("INSERT_DB") or get_settings().insert_db.database
    conn = _connect(db)
    try:
        yield conn
    finally:
        conn.close()


def chunked(items: Iterable, size: int | None = None) -> Iterator[list]:
    size = size or get_settings().icms_db.chunk_size
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
