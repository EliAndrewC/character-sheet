"""Pre-generated name pool for the character name generator.

Names are stored as JSONL files under ``app/data/names/``, one file per
gender. Each record has the shape:

    {"name": "...", "gender": "male"|"female", "format": int,
     "explanation": "...", "notes": "...", "peasant": bool}

Only ``name``, ``gender``, and ``explanation`` are exposed to the UI.
The pools are loaded once on first access and cached in-process.
"""

import json
import os
import random
from functools import lru_cache

SUPPORTED_GENDERS = ("male", "female")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "names")


@lru_cache(maxsize=2)
def _load_pool(gender: str) -> list[dict]:
    path = os.path.join(_DATA_DIR, f"pool-{gender}.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def pick_random_name(gender: str) -> dict:
    """Return a random {name, gender, explanation} entry for the given gender.

    Raises ``ValueError`` on an unsupported gender.
    """
    if gender not in SUPPORTED_GENDERS:
        raise ValueError(f"unsupported gender: {gender!r}")
    entry = random.choice(_load_pool(gender))
    return {
        "name": entry["name"],
        "gender": entry["gender"],
        "explanation": entry["explanation"],
    }
