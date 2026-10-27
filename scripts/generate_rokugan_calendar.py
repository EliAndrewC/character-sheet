#!/usr/bin/env python3
"""Regenerate ``app/data/rokugan_calendar.json`` from the setting notes.

The Night's Rest date picker labels its months and days from "The Festival
Calendar" in the GM's ``setting/l7r.md`` (``#### 3rd Month: Yayoi ("new
life")`` and ``##### 3rd Day (7 Apr): Hinamatsuri ...`` headings). The
deployed app cannot read the host repo, so the parsed result is committed;
``tests/test_game_calendar.py`` fails when the two drift apart.

    python3 scripts/generate_rokugan_calendar.py [path/to/l7r.md]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.game_calendar import CALENDAR_PATH, SOURCE_PATH, parse_calendar  # noqa: E402


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE_PATH
    data = parse_calendar(source.read_text(encoding="utf-8"))
    CALENDAR_PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"Wrote {CALENDAR_PATH} ({len(data['months'])} months)")


if __name__ == "__main__":
    main()
