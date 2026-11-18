"""Database engine and session factory configuration."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all ParkTwin persistence models."""


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine compatible with PostgreSQL and SQLite."""
    kwargs: dict[str, object] = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **kwargs)


class Database:
    """Thin wrapper owning an Engine and Session factory for clean dependency injection."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.engine = build_engine(database_url)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    def create_all(self) -> None:
        """Create tables directly (used in local dev/tests; production uses Alembic migrations)."""
        from app.persistence import models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)

    def session(self) -> Session:
        return self.session_factory()

    def session_dependency(self) -> Iterator[Session]:
        db = self.session()
        try:
            yield db
        finally:
            db.close()

    def check_health(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def dispose(self) -> None:
        self.engine.dispose()
