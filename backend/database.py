"""
Database setup and session management.
Uses SQLAlchemy with async support.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# Create engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}  # SQLite specific
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from . import models  # noqa: F401 - Import to register models
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        # Table might already exist - that's okay
        print(f"Database initialization warning: {e}")
