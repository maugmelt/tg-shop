from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

metadata = MetaData()

products = Table(
    "products",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(160), nullable=False),
    Column("price", Integer, nullable=False),
    Column("category", String(60), nullable=False),
    Column("sizes", Text, nullable=False),
    Column("photo", LargeBinary),
    Column("photo_mime", String(40)),
    Column("active", Integer, nullable=False, default=1),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

drafts = Table(
    "drafts",
    metadata,
    Column("chat_id", String(32), primary_key=True),
    Column("step", String(20), nullable=False),
    Column("title", Text, nullable=False, default=""),
    Column("price", Integer),
    Column("category", Text, nullable=False, default=""),
    Column("sizes", Text, nullable=False, default="[]"),
)

_engine: Engine | None = None


def build_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=NullPool)
    return create_engine(url, pool_pre_ping=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
        metadata.create_all(_engine)
    return _engine


def init_db() -> None:
    get_engine()
    from app.catalog import seed_demo

    seed_demo()


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
