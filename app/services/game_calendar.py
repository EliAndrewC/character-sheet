"""Rokugan's calendar, for dating a Night's Rest in game time.

Rokugan's year is exactly 12 months of exactly 30 days (``setting/l7r.md``,
"Rokugan's Calendar"), so a game date is just ``(month, day)`` and the next
night is simple arithmetic: no leap years, no months of other lengths.

The dropdown labels come from that file's "Festival Calendar": each month's
heading (``3rd month - Yayoi ("new life")``) and each festival day's
(``3 - Hinamatsuri (Doll Festival) or ...``). The app reads them from the
committed ``app/data/rokugan_calendar.json``, regenerated from the setting
notes by ``scripts/generate_rokugan_calendar.py``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

MONTHS = 12
DAYS_PER_MONTH = 30

CALENDAR_PATH = Path(__file__).resolve().parent.parent / "data" / "rokugan_calendar.json"
SOURCE_PATH = Path("/host-l7r-repo/setting/l7r.md")

_MONTH_HEADING = re.compile(r"^#### (\d+)(?:st|nd|rd|th) Month: (.+?)\s*$")
_DAY_HEADING = re.compile(r"^##### (\d+)(?:st|nd|rd|th) Day(?: \([^)]*\))?: (.+?)\s*$")
_ONE_GLOSS = re.compile(r"^([^()]+) \(([^()]+)\)$")


def ordinal(n: int) -> str:
    """1 -> "1st", 2 -> "2nd", 11 -> "11th", 23 -> "23rd"."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _day_name(text: str) -> str:
    """A festival heading as the dropdown shows it: a single trailing gloss
    is quoted like the month names (``Seimei ("clear and bright")``); a
    heading with several is left as written."""
    m = _ONE_GLOSS.match(text)
    return f'{m.group(1)} ("{m.group(2)}")' if m else text


def parse_calendar(markdown: str) -> Dict[str, Any]:
    """Parse "The Festival Calendar" section of ``l7r.md`` into the JSON the
    app commits: 12 months, each with its label and all 30 day labels."""
    start = markdown.index("### The Festival Calendar")
    end = markdown.find("\n## ", start)
    section = markdown[start:end if end != -1 else None]

    months: Dict[int, Dict[str, Any]] = {}
    current: Optional[int] = None
    for line in section.splitlines():
        mm = _MONTH_HEADING.match(line)
        if mm:
            current = int(mm.group(1))
            months[current] = {
                "n": current,
                "name": mm.group(2).split(" ", 1)[0],
                "label": f"{ordinal(current)} month - {mm.group(2)}",
                "festivals": {},
            }
            continue
        dm = _DAY_HEADING.match(line)
        if dm and current is not None:
            day = int(dm.group(1))
            months[current]["festivals"][day] = _day_name(dm.group(2))

    if sorted(months) != list(range(1, MONTHS + 1)):
        raise ValueError(f"expected months 1-{MONTHS}, found {sorted(months)}")
    out = []
    for n in range(1, MONTHS + 1):
        m = months[n]
        out.append({
            "n": n,
            "name": m["name"],
            "label": m["label"],
            "days": [
                f"{d} - {m['festivals'][d]}" if d in m["festivals"] else str(d)
                for d in range(1, DAYS_PER_MONTH + 1)
            ],
        })
    return {"months": out}


@lru_cache(maxsize=1)
def load_calendar() -> Dict[str, Any]:
    """The committed calendar (``app/data/rokugan_calendar.json``)."""
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))


def parse_game_date(body: Dict[str, Any]) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    """Read an optional in-game night from a request body.

    Returns ``((month, day), None)``, ``(None, None)`` when neither
    ``game_month`` nor ``game_day`` was sent (or both are null), or
    ``(None, error)`` when only one was, or either is out of range.
    """
    month, day = body.get("game_month"), body.get("game_day")
    if month is None and day is None:
        return None, None
    if month is None or day is None:
        return None, "game_month and game_day go together"
    for value, top, name in ((month, MONTHS, "game_month"),
                             (day, DAYS_PER_MONTH, "game_day")):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
            return None, f"{name} must be a whole number from 1 to {top}"
    return (month, day), None


def next_night(month: int, day: int) -> Tuple[int, int]:
    """The night after ``(month, day)``; the 30th of the 12th month wraps to
    the 1st of the 1st."""
    if day < DAYS_PER_MONTH:
        return month, day + 1
    return (month % MONTHS) + 1, 1


def date_label(month: int, day: int) -> str:
    """``14th day of the 3rd month (Yayoi)``."""
    name = load_calendar()["months"][month - 1]["name"]
    return f"{ordinal(day)} day of the {ordinal(month)} month ({name})"


def game_date_json(month: Optional[int], day: Optional[int]) -> Optional[Dict[str, Any]]:
    """``{"month", "day", "label"}`` for a stored date, or None."""
    if not month or not day:
        return None
    return {"month": month, "day": day, "label": date_label(month, day)}
