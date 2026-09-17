import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/economic_data")

def create_configured_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})

    # Test PostgreSQL connectivity; if not reachable, use SQLite fallback for local developer environment
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect():
            pass
        return eng
    except Exception as e:
        logger.warning(f"PostgreSQL not reachable at {url} ({e}). Using SQLite fallback for local environment.")
        return create_engine("sqlite:///./economic_data.db", connect_args={"check_same_thread": False})

engine = create_configured_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(target_engine=None):
    use_engine = target_engine or engine
    Base.metadata.create_all(bind=use_engine)
