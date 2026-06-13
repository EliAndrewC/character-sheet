"""Analysis: how much XP each live PC spends on "combat" vs "non-combat".

The question: of everything a character has bought with XP, what share went
toward fighting effectiveness versus everything else (courtly, social,
economic, knowledge, status)? See CombatVsNonCombatXP.md for the writeup and
the rationale behind every categorization call.

------------------------------------------------------------------------------
TWO STEPS: capture (reads live data) then report (reads a frozen snapshot)
------------------------------------------------------------------------------

This analysis reads from the live campaign database, which is NOT in the repo
and is NOT reproducible on its own. So we freeze a point-in-time **snapshot**
(a committed JSON file under combat_xp_snapshots/) and run the report off that.
Re-run the capture whenever you want a new data point - e.g. after the party
banks another 100 XP - and a fresh dated snapshot lets you compare how the
combat/non-combat balance shifts over the campaign.

NO SECRETS LIVE IN THIS SCRIPT. It never talks to Fly or holds a token/key.
Pulling the live DB is a separate manual step you run with your own auth:

    # 1. Pull a local copy of the live SQLite DB (uses YOUR fly login; the
    #    machine auto-starts/stops). Adjust the remote path if it ever moves.
    set -a && source .env && set +a            # loads FLY_API_TOKEN locally
    export PATH="$HOME/.fly/bin:$PATH"
    fly machine start <machine-id>             # only if it is stopped
    fly ssh sftp get /data/l7r.db /tmp/l7r_live.db

    # 2. Capture a dated snapshot from that local copy (writes a committed JSON):
    DATABASE_URL=/tmp/l7r_live.db PYTHONPATH=. python3 \
        analysis/combat_vs_noncombat_xp.py capture

    # 3. Generate the Markdown table + summary stats for the writeup:
    PYTHONPATH=. python3 analysis/combat_vs_noncombat_xp.py report

The report step needs no database at all - only the committed snapshot - so
anyone with a checkout can reproduce the table. Paste its stdout into the
"## Results" section of CombatVsNonCombatXP.md, then write/refresh the prose
around it (the table is scripted; the analysis is not).

------------------------------------------------------------------------------
WHAT COUNTS AS "COMBAT" (kept in lock-step with the .md)
------------------------------------------------------------------------------

  - Rings: ALL of them (a simplification - Air on a non-parrier is mostly
    non-combat - but rings are too entangled with combat to split cleanly,
    and raising any ring feeds Void points, which help in a fight).
  - School knacks (and foreign school knacks): ALL of them. Pure-combat bushi
    schools obviously, but every school's knacks/techniques have combat uses
    too (e.g. 100% of 5th Dan techniques work in a fight), so we treat all
    school expenditure as combat.
  - Attack / Parry: always.
  - General (social/knowledge) skills: a skill is combat ONLY if it powers the
    school's combat machinery - i.e. it is the skill named in the 3rd Dan
    "X is your ___ skill" technique, or (Shosuro Actor) the skill the Special
    Ability keys off. That skill is auto-derived from the canonical rules text
    in app/game_data.py, so this stays correct as schools are added or
    reworded. Everything else (etiquette, culture, commerce, ...) is
    non-combat.
  - Advantages: combat iff it has a combat application - Lucky (reroll any
    roll), Strength of the Earth (wound checks), Quick Healer (recover from
    combat wounds), and any Specialization whose domain is a combat skill.
    Everything else (Charming, Worldly, Tactician, allies, wealth, ...) is
    non-combat.
  - Honor / Rank / Recognition: non-combat (pure status).

Disadvantages are NOT bucketed. Their refunded XP simply lets a character buy
more, so it already shows up inside the combat/non-combat totals; the
denominator (combat + non-combat) is total positive XP spent, which equals
base XP + disadvantage XP. Percentages are combat / (combat + non-combat).
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import statistics

from app.game_data import ADVANTAGES, SCHOOLS, SKILLS
from app.services.xp import calculate_xp_breakdown

HERE = pathlib.Path(__file__).resolve().parent
SNAP_DIR = HERE / "combat_xp_snapshots"

# Public production site - character names in the report link to their sheets.
SITE_URL = "https://l7r-character-sheet.fly.dev"

# --- roster ----------------------------------------------------------------
# Captured = every published, non-hidden (i.e. shared) character. The report
# then drops these ids. Currently just "Monk" (id 5): a placeholder-named
# second character of a player who already has a listed PC, not one of the
# campaign's player characters. Edit if the roster changes.
EXCLUDE_IDS = {5}

# --- categorization config (see module docstring + the .md) ----------------
# Advantages with a combat application, by game-data id (mapped to display
# names at runtime so a label re-wording can't silently break the match).
COMBAT_ADVANTAGE_IDS = {"lucky", "strength_of_the_earth", "quick_healer"}
# A Specialization is combat only if its chosen domain is a combat skill/action.
COMBAT_SPEC_RE = re.compile(
    r"fight|attack|parry|unarmed|weapon|knuckle|lunge|iaijutsu|kenjutsu|archery|brawl|grapple",
    re.I,
)
# Schools whose Special Ability (not 3rd Dan) keys off a general skill, making
# that skill combat. The 3rd-Dan-powered skill is auto-derived below; this dict
# is only for the rarer special-ability case.
SPECIAL_ABILITY_COMBAT_SKILL_IDS = {"shosuro_actor": {"acting"}}

# Fields copied into a snapshot - everything calculate_xp_breakdown needs,
# plus id/name for the table and starting/earned XP for the record.
SNAPSHOT_FIELDS = [
    "id", "name", "school", "school_ring_choice", "rings", "attack", "parry",
    "skills", "knacks", "foreign_knacks", "advantages", "disadvantages",
    "campaign_advantages", "campaign_disadvantages", "specializations",
    "honor", "rank", "rank_locked", "recognition", "recognition_halved",
    "starting_xp", "earned_xp",
]

_THIRD_DAN_RE = re.compile(r"X is your ([a-z]+) skill", re.I)
_SKILL_NAME_TO_ID = {s.name.lower(): sid for sid, s in SKILLS.items()}


def combat_skill_names(school_id: str) -> set:
    """Display names of the general skills that count as COMBAT for this school.

    The skill named in the 3rd Dan "X is your ___ skill" technique (when it is
    one of the general social/knowledge skills - attack/parry-powered schools
    add nothing here), plus any Special-Ability-powered skill.
    """
    ids = set()
    school = SCHOOLS.get(school_id)
    if school:
        m = _THIRD_DAN_RE.search(school.techniques.get(3, "") or "")
        if m and m.group(1).lower() in _SKILL_NAME_TO_ID:
            ids.add(_SKILL_NAME_TO_ID[m.group(1).lower()])
    ids |= SPECIAL_ABILITY_COMBAT_SKILL_IDS.get(school_id, set())
    return {SKILLS[sid].name for sid in ids}


def _combat_advantage_labels() -> set:
    return {ADVANTAGES[a].name for a in COMBAT_ADVANTAGE_IDS if a in ADVANTAGES}


def _advantage_is_combat(label: str, combat_labels: set) -> bool:
    if label in combat_labels:
        return True
    if label.startswith("Specialization"):
        return bool(COMBAT_SPEC_RE.search(label))
    return False


def categorize(char: dict) -> dict:
    """Split one character's XP into combat vs non-combat. Returns a row dict."""
    b = calculate_xp_breakdown(char)
    combat_skills = combat_skill_names(char["school"])
    combat_adv_labels = _combat_advantage_labels()

    rings = b["rings"]["total"]
    knacks = b["school_knacks"]["total"] + b["foreign_knacks"]["total"]
    atk_parry = b["combat_skills"]["total"]

    skill_combat = 0
    skill_total = 0
    for sub in b["skills"]["subsections"]:
        for r in sub["rows"]:
            skill_total += r["xp"]
            if r["label"] in combat_skills:
                skill_combat += r["xp"]
    skill_noncombat = skill_total - skill_combat

    adv_combat = sum(
        r["xp"] for r in b["advantages"]["rows"]
        if _advantage_is_combat(r["label"], combat_adv_labels)
    )
    adv_noncombat = b["advantages"]["total"] - adv_combat
    hrr = b["honor_rank_recognition"]["total"]  # non-combat (status)

    combat = rings + knacks + atk_parry + skill_combat + adv_combat
    noncombat = skill_noncombat + adv_noncombat + hrr
    total = combat + noncombat
    return {
        "id": char["id"],
        "name": char["name"],
        "school": char["school"],
        "school_name": SCHOOLS[char["school"]].name if char["school"] in SCHOOLS else char["school"],
        "combat": combat,
        "noncombat": noncombat,
        "total": total,
        "combat_pct": 100.0 * combat / total if total else 0.0,
    }


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

def capture(args) -> None:
    """Read the live DB copy (DATABASE_URL or --db) and write a dated snapshot."""
    import os

    if args.db:
        os.environ["DATABASE_URL"] = args.db
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit(
            "capture needs a local DB copy: set DATABASE_URL=/path/to/l7r_live.db "
            "(or pass --db). See the module docstring for how to pull it."
        )
    # Imported lazily so the report path never needs a database/engine.
    from app.database import SessionLocal
    from app.models import Character

    db = SessionLocal()
    chars = (
        db.query(Character)
        .filter(Character.is_published == True, Character.is_hidden == False)  # noqa: E712
        .order_by(Character.id)
        .all()
    )
    snapshot = {
        "captured": args.date,
        "source": "live database (published, non-hidden characters)",
        "characters": [
            {k: c.to_dict().get(k) for k in SNAPSHOT_FIELDS} for c in chars
        ],
    }
    SNAP_DIR.mkdir(exist_ok=True)
    out = SNAP_DIR / f"{args.date}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {out} ({len(snapshot['characters'])} characters).")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _latest_snapshot() -> pathlib.Path:
    snaps = sorted(SNAP_DIR.glob("*.json"))
    if not snaps:
        raise SystemExit(f"No snapshots in {SNAP_DIR}. Run the capture step first.")
    return snaps[-1]


def _load_snapshot(args) -> dict:
    if args.snapshot:
        path = pathlib.Path(args.snapshot)
    elif args.date:
        path = SNAP_DIR / f"{args.date}.json"
    else:
        path = _latest_snapshot()
    return json.loads(path.read_text())


def _md_table(rows: list) -> str:
    out = [
        "| Character | School | Combat XP | Non-combat XP | Total | Combat % | Non-combat % |",
        "|---|---|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        name = f"[{r['name']}]({SITE_URL}/characters/{r['id']})"
        out.append(
            f"| {name} | {r['school_name']} | {r['combat']} | {r['noncombat']} "
            f"| {r['total']} | {r['combat_pct']:.1f}% | {100 - r['combat_pct']:.1f}% |"
        )
    return "\n".join(out)


def report(args) -> None:
    snap = _load_snapshot(args)
    rows = [
        categorize(c) for c in snap["characters"] if c["id"] not in EXCLUDE_IDS
    ]
    rows.sort(key=lambda r: r["combat_pct"], reverse=True)
    pcts = [r["combat_pct"] for r in rows]

    print(f"## Results (snapshot: {snap['captured']}, n = {len(rows)})\n")
    print(_md_table(rows))
    print()
    mean, median = statistics.mean(pcts), statistics.median(pcts)
    print(
        f"- Combat share - mean {mean:.1f}%, median {median:.1f}%, "
        f"range {min(pcts):.1f}% to {max(pcts):.1f}% "
        f"(a {max(pcts) - min(pcts):.1f}-point spread)."
    )
    print(
        f"- Non-combat share - mean {100 - mean:.1f}%, median {100 - median:.1f}%, "
        f"range {100 - max(pcts):.1f}% to {100 - min(pcts):.1f}%."
    )
    excluded = [c["id"] for c in snap["characters"] if c["id"] in EXCLUDE_IDS]
    if excluded:
        print(f"\n_Excluded from the roster: character ids {sorted(excluded)} "
              f"(see EXCLUDE_IDS in the script)._")


def trend(args) -> None:
    """One row per committed snapshot: how the balance moves over the campaign."""
    snaps = sorted(SNAP_DIR.glob("*.json"))
    if not snaps:
        raise SystemExit(f"No snapshots in {SNAP_DIR}.")
    print("| Snapshot | PCs | Mean combat % | Median combat % | Range |")
    print("|---|--:|--:|--:|---|")
    for path in snaps:
        snap = json.loads(path.read_text())
        rows = [categorize(c) for c in snap["characters"] if c["id"] not in EXCLUDE_IDS]
        pcts = [r["combat_pct"] for r in rows]
        print(
            f"| {snap['captured']} | {len(rows)} | {statistics.mean(pcts):.1f}% "
            f"| {statistics.median(pcts):.1f}% "
            f"| {min(pcts):.1f}% - {max(pcts):.1f}% |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="freeze a dated snapshot from a live DB copy")
    p_cap.add_argument("--db", help="path to a local copy of the live SQLite DB "
                                     "(else uses $DATABASE_URL)")
    p_cap.add_argument("--date", default=datetime.date.today().isoformat(),
                       help="snapshot label (default: today, YYYY-MM-DD)")
    p_cap.set_defaults(func=capture)

    p_rep = sub.add_parser("report", help="print the Markdown table + stats from a snapshot")
    p_rep.add_argument("--snapshot", help="explicit snapshot file (default: latest)")
    p_rep.add_argument("--date", help="snapshot date YYYY-MM-DD (default: latest)")
    p_rep.set_defaults(func=report)

    p_tr = sub.add_parser("trend", help="one summary row per snapshot, over time")
    p_tr.set_defaults(func=trend)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
