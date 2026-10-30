"""Database engine and session factory construction."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from veriagent.db.models import Base


def create_database_engine(database_url: str) -> Engine:
    """Create an engine configured safely for SQLite and test concurrency."""
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool

    engine = create_engine(database_url, **kwargs)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application session factory."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    """Create all application tables."""
    Base.metadata.create_all(engine)
