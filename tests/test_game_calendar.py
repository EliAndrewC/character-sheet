"""Rokugan's calendar (``app/services/game_calendar.py``) and the committed
``app/data/rokugan_calendar.json`` the Night's Rest date picker reads."""

import pytest

from app.services import game_calendar as gc

SAMPLE = """# Notes

### The Festival Calendar

Intro.

#### 1st Month: Mutsuki ("affection month")

##### 1st Day (4 Feb): Risshun (first day of spring)
##### 12th Day (18 Mar): Haru Higan festival
""" + "".join(
    f'\n#### {gc.ordinal(n)} Month: Name{n} ("gloss {n}")\n' for n in range(2, 13)
) + """
##### 3rd Day (7 Apr): Hinamatsuri (Doll Festival) or Momo no sekku (Peach Festival), and Gotou (Holy Light)

## Oaths and Vows

#### 13th Month: Nope ("not in the section")
"""


def test_ordinal():
    assert [gc.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "30th"]


def test_parse_labels_months_and_festival_days():
    months = gc.parse_calendar(SAMPLE)["months"]
    assert len(months) == 12
    first = months[0]
    assert first["label"] == '1st month - Mutsuki ("affection month")'
    assert first["name"] == "Mutsuki"
    assert len(first["days"]) == 30
    # One trailing gloss is quoted; the Gregorian date is dropped.
    assert first["days"][0] == '1 - Risshun ("first day of spring")'
    assert first["days"][1] == "2"
    # No gloss: as written.
    assert first["days"][11] == "12 - Haru Higan festival"
    # Several glosses: as written.
    assert months[11]["days"][2] == (
        "3 - Hinamatsuri (Doll Festival) or Momo no sekku (Peach Festival), "
        "and Gotou (Holy Light)")


def test_parse_refuses_a_missing_month():
    with pytest.raises(ValueError):
        gc.parse_calendar(SAMPLE.replace("#### 5th Month", "#### Fifth"))


def test_committed_calendar_has_twelve_months_of_thirty_days():
    months = gc.load_calendar()["months"]
    assert [m["n"] for m in months] == list(range(1, 13))
    assert all(len(m["days"]) == 30 for m in months)
    yayoi = months[2]
    assert yayoi["label"] == '3rd month - Yayoi ("new life")'
    assert yayoi["days"][:3] == [
        '1 - Seimei ("clear and bright")', "2",
        "3 - Hinamatsuri (Doll Festival) or Momo no sekku (Peach Festival), "
        "and Gotou (Holy Light)"]


def test_committed_calendar_matches_the_setting_notes():
    """Fails when l7r.md's calendar changes: rerun
    scripts/generate_rokugan_calendar.py and commit the JSON."""
    if not gc.SOURCE_PATH.exists():
        pytest.skip("/host-l7r-repo is not mounted")
    assert gc.parse_calendar(gc.SOURCE_PATH.read_text(encoding="utf-8")) == \
        gc.load_calendar(), (
        "app/data/rokugan_calendar.json is out of date with setting/l7r.md: "
        "run python3 scripts/generate_rokugan_calendar.py and commit it")


@pytest.mark.parametrize("body,expected", [
    ({}, (None, None)),
    ({"game_month": None, "game_day": None}, (None, None)),
    ({"game_month": 3, "game_day": 14}, ((3, 14), None)),
    ({"game_month": 12, "game_day": 30}, ((12, 30), None)),
])
def test_parse_game_date_accepts(body, expected):
    assert gc.parse_game_date(body) == expected


@pytest.mark.parametrize("body", [
    {"game_month": 3},
    {"game_day": 14},
    {"game_month": 0, "game_day": 1},
    {"game_month": 13, "game_day": 1},
    {"game_month": 1, "game_day": 31},
    {"game_month": 1, "game_day": 0},
    {"game_month": "3", "game_day": 14},
    {"game_month": True, "game_day": 14},
    {"game_month": 3, "game_day": 1.5},
])
def test_parse_game_date_refuses(body):
    date, error = gc.parse_game_date(body)
    assert date is None and error


def test_next_night_wraps_months_and_the_year():
    assert gc.next_night(3, 14) == (3, 15)
    assert gc.next_night(3, 30) == (4, 1)
    assert gc.next_night(12, 30) == (1, 1)


def test_date_label():
    assert gc.date_label(3, 14) == "14th day of the 3rd month (Yayoi)"
    assert gc.game_date_json(3, 14) == {
        "month": 3, "day": 14, "label": "14th day of the 3rd month (Yayoi)"}
    assert gc.game_date_json(None, None) is None
