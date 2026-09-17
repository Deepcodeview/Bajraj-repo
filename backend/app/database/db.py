"""
database/db.py — SQLite session factory + table creation.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from app.database.models import Base
from typing import Generator

DATABASE_URL = "sqlite:///./retail_ai.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=20,
    max_overflow=30,
    pool_timeout=10,
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables if they don't exist, and purge stale PROCESSING jobs on restart."""
    Base.metadata.create_all(bind=engine)
    import sqlite3, time
    db_path = DATABASE_URL.replace("sqlite:///", "")
    for attempt in range(10):
        try:
            con = sqlite3.connect(db_path, timeout=10)
            con.execute("DELETE FROM analytics_jobs WHERE status = 'processing'")
            con.commit()
            con.close()
            break
        except sqlite3.OperationalError:
            time.sleep(0.5)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
