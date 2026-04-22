"""Tests for the name generator service and endpoint.

The pools are shipped as JSONL fixtures under ``app/data/names/``. These
tests exercise:

- pool loading (both genders, cache hits)
- pick_random_name for each gender + ValueError on unsupported input
- /api/names/random response shape and 400 on bad gender
"""

import random

import pytest

from app.services import names as names_svc


def test_load_pool_male_is_nonempty():
    pool = names_svc._load_pool("male")
    assert len(pool) > 0
    # Every entry has the fields the service exposes.
    for entry in pool:
        assert "name" in entry
        assert "gender" in entry
        assert "explanation" in entry
        assert entry["gender"] == "male"


def test_load_pool_female_is_nonempty():
    pool = names_svc._load_pool("female")
    assert len(pool) > 0
    for entry in pool:
        assert entry["gender"] == "female"


def test_load_pool_is_cached():
    # lru_cache returns the same list object for repeat calls.
    first = names_svc._load_pool("male")
    second = names_svc._load_pool("male")
    assert first is second


def test_pick_random_name_male_shape():
    entry = names_svc.pick_random_name("male")
    assert set(entry.keys()) == {"name", "gender", "explanation"}
    assert entry["gender"] == "male"
    assert entry["name"]
    assert entry["explanation"]


def test_pick_random_name_female_shape():
    entry = names_svc.pick_random_name("female")
    assert entry["gender"] == "female"
    assert entry["name"]


def test_pick_random_name_rejects_unknown_gender():
    with pytest.raises(ValueError):
        names_svc.pick_random_name("nonbinary")


def test_random_name_route_returns_male_by_default(client):
    resp = client.get("/api/names/random")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gender"] == "male"
    assert data["name"]
    assert data["explanation"]


def test_random_name_route_supports_female(client):
    resp = client.get("/api/names/random?gender=female")
    assert resp.status_code == 200
    assert resp.json()["gender"] == "female"


def test_random_name_route_rejects_bad_gender(client):
    resp = client.get("/api/names/random?gender=martian")
    assert resp.status_code == 400
    assert "gender" in resp.json()["error"].lower()


def test_random_name_route_is_actually_random(client, monkeypatch):
    # Force the pool shuffle to be deterministic by patching random.choice
    # so we can confirm the route delegates to the service layer rather
    # than always returning the first entry.
    male_pool = names_svc._load_pool("male")
    target = male_pool[-1]
    monkeypatch.setattr(random, "choice", lambda seq: target)
    resp = client.get("/api/names/random?gender=male")
    assert resp.json()["name"] == target["name"]
