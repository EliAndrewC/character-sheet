"""Shared fixtures for the L7R test suite."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Set auth env vars before importing app
os.environ.setdefault("DISCORD_WHITELIST_IDS", "183026066498125825")
os.environ.setdefault("ADMIN_DISCORD_IDS", "183026066498125825")
os.environ.setdefault("TEST_AUTH_BYPASS", "true")

from app.database import Base, get_db
from app.main import app
from app.models import Character


@pytest.fixture()
def engine():
    """Create a fresh in-memory SQLite engine with tables."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def db(engine):
    """Yield a SQLAlchemy session backed by the in-memory test database."""
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(engine):
    """Yield a FastAPI TestClient wired to the in-memory test database.

    Uses a shared connection so that data written by routes is visible
    to queries within the same test, and vice versa.
    """
    from fastapi.testclient import TestClient

    # Use a single connection for the entire test so all sessions
    # see each other's writes (important for in-memory SQLite).
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, headers={"X-Test-User": "183026066498125825:testplayer"}) as c:
        # Attach a helper to query the same connection
        c._test_session_factory = TestSession
        yield c

    transaction.rollback()
    connection.close()
    app.dependency_overrides.clear()


def query_db(client, model=Character):
    """Get a session from the test client's connection for assertions."""
    session = client._test_session_factory()
    return session.query(model)


def make_character_data(**overrides) -> dict:
    """Return a minimal valid character data dict, with optional overrides."""
    data = {
        "name": "Test Samurai",
        "player_name": "Test Player",
        "school": "akodo_bushi",
        "school_ring_choice": "Water",
        "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        "attack": 1,
        "parry": 1,
        "skills": {},
        "knacks": {"double_attack": 1, "feint": 1, "iaijutsu": 1},
        "advantages": [],
        "disadvantages": [],
        "honor": 1.0,
        "rank": 1.0,
        "recognition": 1.0,
        "recognition_halved": False,
        "campaign_advantages": [],
        "campaign_disadvantages": [],
        "earned_xp": 0,
        "starting_xp": 150,
    }
    data.update(overrides)
    return data


def make_character_form(**overrides) -> dict:
    """Return form data (flat key-value pairs) for creating/updating a character via POST."""
    form = {
        "name": "Test Samurai",
        "player_name": "Test Player",
        "school": "akodo_bushi",
        "school_ring_choice": "Water",
        "ring_air": "2",
        "ring_fire": "2",
        "ring_earth": "2",
        "ring_water": "3",
        "ring_void": "2",
        "attack": "1",
        "parry": "1",
        "knack_double_attack": "1",
        "knack_feint": "1",
        "knack_iaijutsu": "1",
        "honor": "1.0",
        "rank": "1.0",
        "recognition": "1.0",
        "starting_xp": "150",
        "earned_xp": "0",
    }
    form.update(overrides)
    return form
