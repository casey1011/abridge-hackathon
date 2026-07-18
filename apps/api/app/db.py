"""Database engine + session helpers (SQLite via SQLModel).

Hackathon default: a single on-disk SQLite file next to the API.
Swap the URL for Postgres when you outgrow it — the models don't change.
"""
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

# apps/api/abridge.db — resolved absolutely so it loads regardless of cwd.
_DB_PATH = Path(__file__).resolve().parent.parent / "abridge.db"

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    # SQLite + FastAPI background tasks touch the connection from other threads.
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables. Import models first so they register on SQLModel.metadata."""
    from . import models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
