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
    """Create all tables and add any missing columns."""
    import app.models  # noqa: F401 — ensure models are registered

    Base.metadata.create_all(bind=engine)

    # Simple migration: add columns that may be missing from older schemas.
    # SQLite supports ADD COLUMN but not ALTER/DROP, which is fine for us.
    _migrate_add_columns()


def _migrate_add_columns():
    """Add any columns that exist in the model but not yet in the DB."""
    import sqlite3

    db_url = engine.url.render_as_string(hide_password=False)
    # Strip the sqlite:/// prefix to get the file path
    db_path = db_url.replace("sqlite:///", "")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(characters)")
    existing = {row[1] for row in cursor.fetchall()}

    # Columns to ensure exist: (name, type, default)
    needed = [
        ("attack", "INTEGER", "1"),
        ("parry", "INTEGER", "1"),
        ("rank_locked", "BOOLEAN", "0"),
        ("owner_discord_id", "TEXT", "NULL"),
        ("editor_discord_ids", "TEXT", "'[]'"),
        ("is_published", "BOOLEAN", "0"),
        ("published_state", "TEXT", "NULL"),
        ("campaign_advantages", "TEXT", "'[]'"),
        ("campaign_disadvantages", "TEXT", "'[]'"),
        ("advantage_details", "TEXT", "'{}'"),
        ("adventure_state", "TEXT", "'{}'"),
    ]

    for col_name, col_type, default in needed:
        if col_name not in existing:
            cursor.execute(
                f"ALTER TABLE characters ADD COLUMN {col_name} {col_type} DEFAULT {default}"
            )

    # Character versions table migrations
    cursor.execute("PRAGMA table_info(character_versions)")
    version_cols = {row[1] for row in cursor.fetchall()}
    if version_cols and "author_discord_id" not in version_cols:
        cursor.execute(
            "ALTER TABLE character_versions ADD COLUMN author_discord_id TEXT DEFAULT NULL"
        )

    # Users table migrations
    cursor.execute("PRAGMA table_info(users)")
    user_cols = {row[1] for row in cursor.fetchall()}
    user_needed = [
        ("granted_account_ids", "TEXT", "'[]'"),
    ]
    for col_name, col_type, default in user_needed:
        if user_cols and col_name not in user_cols:
            cursor.execute(
                f"ALTER TABLE users ADD COLUMN {col_name} {col_type} DEFAULT {default}"
            )

    conn.commit()
    conn.close()
