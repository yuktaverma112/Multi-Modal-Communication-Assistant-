"""
backend/database/database.py

SQLite for the MVP (per the project guide, section 4: "SQLite
initially; PostgreSQL later"). Swapping to PostgreSQL later only
means changing DATABASE_URL in .env -- SQLAlchemy handles the rest.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session, always closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.database import models  # noqa: F401  (register tables)
    Base.metadata.create_all(bind=engine)
