import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

db_path = os.environ.get("DATABASE_URL", "l7r.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables defined on Base.metadata."""
    import app.models  # noqa: F401 — ensure models are registered

    Base.metadata.create_all(bind=engine)
