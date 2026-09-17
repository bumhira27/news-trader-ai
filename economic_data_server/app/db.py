import logging
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Production uses PostgreSQL. Tests/developer fixtures must provide an explicit
# SQLite DATABASE_URL when they want SQLite. There is intentionally no silent
# production fallback between database engines.
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _require_engine():
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL is required. Configure DATABASE_URL explicitly; "
            "the Economic Data Server does not silently fall back to SQLite."
        )
    return engine


def get_db():
    db = SessionLocal()
    if db.bind is None:
        db.close()
        raise RuntimeError(
            "DATABASE_URL is required. Configure DATABASE_URL before starting the API."
        )
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None):
    use_engine = target_engine or _require_engine()
    Base.metadata.create_all(bind=use_engine)
