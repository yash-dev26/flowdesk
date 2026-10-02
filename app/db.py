import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connection(db_path: str):
    """Short-lived SQLite connection; commits on success, always closes."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
