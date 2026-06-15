"""Analysis: combat vs non-combat XP for seven PCs from past campaigns, read
from XP-ledger spreadsheets.

A second companion to combat_vs_noncombat_xp.py (the live party) and
combat_xp_past_campaigns.py (Wakuu / Kitsuki Tetsu, hand-encoded from .odt
sheets). The characters here come from a *different player*, who tracked builds
not as character sheets but as XP ledgers - one row per purchase, with the
actual XP cost in a column (`old-character-sheets/*Points.xls`):

    Isamu (Kuni Witch Hunter), Naritsugu (Kakita Duelist), Junichiro (Merchant),
    Takumi (Courtier), Masumune (Mirumoto Bushi), Shori (Kitsuki Magistrate),
    Tozasu (peasant - no school).

Run it:  PYTHONPATH=. python3 analysis/combat_xp_past_ledgers.py
Needs xlrd to read the legacy .xls files:  pip install --break-system-packages xlrd

------------------------------------------------------------------------------
WHY A LEDGER IS BETTER THAN RE-COSTING, AND HOW WE SPLIT BEGINNING vs END
------------------------------------------------------------------------------

Because every row carries its *actual* XP cost, we do not recompute anything
from the rank tables - we just read the number and bucket it. That sidesteps the
fact that these campaigns used different conventions than the live app (rings
maxing at 6, different free-ring placement, rings starting at rank 1 for the
peasant, a separate "character points" pool at creation, etc.).

The ledgers are chronological: the first rows are character creation, then each
subsequent "Earned" row is one adventure's XP award. So "beginning" (the
creation build) = every purchase made before the creation budget runs out, and
"ending" = the whole ledger. We find the boundary with a running balance: the
creation budget is Starting + the creation "Earned" + disadvantages/other grants
listed at creation; we walk the rows in order and creation ends at the first
purchase that budget cannot afford (i.e. the player had to wait for the next
adventure), or at the second "Earned" row, whichever comes first.

Per-campaign creation-earned amounts come straight from each sheet's row-2
"Earned" and reconcile to the XP, with one exception: NARITSUGU. His sheet front-
loads 150 of creation earned, but per the player it was 100; we override to 100,
which moves ~50 XP of late "creation" purchases (starting at Fire to 6) into the
campaign phase. Masumune has no "Earned" rows at all - he died at creation, so he
is a single data point (beginning == ending), and his accumulated total is what
Shori (his replacement cousin) was rebuilt on (Shori's creation total ~324 vs
Masumune's ~319 confirms it).

------------------------------------------------------------------------------
CATEGORIZATION (identical rules to the live analysis, plus ledger specifics)
------------------------------------------------------------------------------

  - Rings, school knacks (incl. the "Nth Dan" rows that raise all three knacks
    one rank), Attack, Parry: combat.
  - General skills: non-combat, except the one skill that powers the school's
    combat machinery (auto-derived from game_data via combat_skill_names) -
    Investigation for Kuni/Kitsuki, Sincerity for Merchant, Tact for Courtier.
    Tozasu is a peasant with no school, so no general skill is combat.
  - Honor / Rank / Recognition: non-combat. NOTE these ledgers DO spend XP on
    them (unlike the .odt characters), so HRR shows up in the non-combat total
    here. That is faithful to what was actually bought.
  - Advantages: combat iff combat application. Combat: Lucky, Quick Healer,
    Strength of the Earth, Great Destiny ("one more SW to kill you"), Reroll
    Wound Check, Avoid Death, "Wound Check to live", and Specializations whose
    domain is combat (Arrows, Ogres). Non-combat: everything social/status
    (Discerning, Fierce, Good Reputation, Kind Eye, Charming, Worldly, Virtue,
    Imperial Favor, Tactician, allies, reputations, ...).
  - Disadvantages, vows, "Possession Points" and other grants: positive XP that
    feeds the budget; not bucketed, exactly as in the live analysis.

"Deployment" (Tozasu) is the old name for Strategy - non-combat. A handful of
sheet typos are aliased (Iajitsu -> Iaijutsu, Worldiness -> Worldliness).
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from combat_vs_noncombat_xp import combat_skill_names  # noqa: E402
from app.game_data import SKILLS, SCHOOL_KNACKS  # noqa: E402

try:
    import xlrd
except ImportError:  # pragma: no cover - dev dependency, documented in docstring
    raise SystemExit("This analysis needs xlrd: pip install --break-system-packages xlrd")

HERE = pathlib.Path(__file__).resolve().parent
SHEETS = HERE / "old-character-sheets"

SKILL_NAMES = {s.name.lower() for s in SKILLS.values()}
KNACK_NAMES = {k.name.lower() for k in SCHOOL_KNACKS.values()}
RINGS = {"fire", "water", "air", "earth", "void"}

COMBAT_ADV = {
    "lucky", "quick healer", "strength of the earth", "great destiny",
    "famous sword", "reroll wound check", "avoid death", "wound check to live",
}
COMBAT_SPEC = re.compile(r"arrow|ogre|fight|attack|parry|weapon|archery|lunge|"
                         r"iaijutsu|kenjutsu|brawl|unarmed", re.I)
KNACK_ALIASES = ("worldiness", "iajitsu", "iaijitsu")  # sheet typos -> knacks
ADV_OVERRIDE = {"tactician": "noncombat"}              # collide with a skill prefix

# name -> (school_id, creation-earned override or None)
# School only affects which (if any) general skill counts as combat. Kakita
# Duelist and Mirumoto Bushi both key their 3rd Dan off Attack, so neither has a
# general combat skill - the labels below are for the table, not the math.
# Masumune was a Mirumoto Bushi (a Void-ring dueling line) who invested in Fire,
# an off-school ring, to duel better; his ledger pumps Fire accordingly.
LEDGERS = {
    "Isamu":     ("kuni_witch_hunter", None),
    "Naritsugu": ("kakita_duelist", 100),  # override: built on 100 earned, not the sheet's 150
    "Junichiro": ("merchant", None),
    "Takumi":    ("courtier", None),
    "Masumune":  ("mirumoto_bushi", None),  # died at creation -> single data point
    "Shori":     ("kitsuki_magistrate", None),
}
SCHOOL_LABEL = {
    "kuni_witch_hunter": "Kuni Witch Hunter", "kakita_duelist": "Kakita Duelist",
    "merchant": "Merchant", "courtier": "Courtier",
    "mirumoto_bushi": "Mirumoto Bushi", "kitsuki_magistrate": "Kitsuki Magistrate",
}


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return 0.0


def bucket(label, xp, combat_skill):
    """Return 'combat', 'noncombat', or 'budget' for one ledger line."""
    l = label.strip().lower()
    if (l.startswith("earned") or l.startswith("starting")
            or l.startswith("possession points") or "vow" in l or l == ""):
        return "budget"
    if any(l.startswith(t) for t in KNACK_ALIASES):
        return "combat"
    if l in ADV_OVERRIDE:
        return ADV_OVERRIDE[l]
    first = l.split(" to ")[0].split(" (")[0].strip()
    if first in RINGS and " to " in l:
        return "combat"                                   # ring raise
    if l.startswith("attack") or l.startswith("parry"):
        return "combat"
    if re.match(r"(second|third|fourth|fifth) dan$", l):
        return "combat"                                   # raises all 3 knacks
    if any(l.startswith(kn) for kn in KNACK_NAMES):
        return "combat"
    for sk in SKILL_NAMES:
        if l.startswith(sk):
            return "combat" if sk == (combat_skill or "").lower() else "noncombat"
    if l.startswith(("honor", "rank", "recognition")):
        return "noncombat"
    if xp > 0:
        return "budget"                                   # disadvantage / grant
    if l.startswith("specialization"):
        return "combat" if COMBAT_SPEC.search(label) else "noncombat"
    return "combat" if l in COMBAT_ADV else "noncombat"   # advantage


def parse_ledger(name, school, earned_override):
    sh = xlrd.open_workbook(str(SHEETS / f"{name}Points.xls")).sheet_by_index(0)
    cs = combat_skill_names(school)
    combat_skill = next(iter(cs), None)
    rows = []
    for r in range(sh.nrows):
        label = str(sh.cell_value(r, 0)).strip()
        xp = num(sh.cell_value(r, 1))
        if label == "" and xp == 0:
            continue
        rows.append((label, xp))

    earned_pos = [i for i, (l, _) in enumerate(rows) if l.lower().startswith("earned")]
    second_earned = earned_pos[1] if len(earned_pos) >= 2 else len(rows)

    # running-balance boundary
    bal = 0.0
    boundary = second_earned
    seen_first_earned = False
    for i, (l, x) in enumerate(rows):
        if i >= second_earned:
            break
        if l.lower().startswith("earned"):
            if not seen_first_earned and earned_override is not None:
                x = earned_override
            seen_first_earned = True
            bal += x
            continue
        if x < 0 and bal + x < 0:          # creation budget can't afford this
            boundary = i
            break
        bal += x

    begin = {"combat": 0.0, "noncombat": 0.0}
    end = {"combat": 0.0, "noncombat": 0.0}
    for i, (l, x) in enumerate(rows):
        b = bucket(l, x, combat_skill)
        if b == "budget" or x >= 0:
            continue
        end[b] += -x
        if i < boundary:
            begin[b] += -x
    return begin, end


def _tozasu_is_combat(label):
    """Tozasu's columns use positive=spend, so we can't reuse bucket() (which
    treats positive as a budget grant). Peasant - no school - so combat is only
    rings, Attack, Parry, and combat advantages; everything else (all skills,
    incl. Deployment=Strategy, Honor, social advantages) is non-combat."""
    l = label.strip().lower()
    first = l.split(" to ")[0].split(" (")[0].strip()
    if first in RINGS and " to " in l:
        return True
    if l.startswith("attack") or l.startswith("parry"):
        return True
    if l in COMBAT_ADV:
        return True
    if l.startswith("specialization") and COMBAT_SPEC.search(label):
        return True
    return False


def parse_tozasu():
    """Tozasu used a two-pool sheet: a CP column (creation) and an XP column
    (campaign), both with positive=spend, negative=disadvantage (gain)."""
    sh = xlrd.open_workbook(str(SHEETS / "TozasuPoints.xls")).sheet_by_index(0)

    def tally(col_label, col_val):
        c = nc = 0.0
        for r in range(1, sh.nrows):
            lab = str(sh.cell_value(r, col_label)).strip()
            v = sh.cell_value(r, col_val)
            if not isinstance(v, (int, float)) or lab == "":
                continue
            v = float(v)
            if v <= 0:                     # disadvantage (gain) - not bucketed
                continue
            if _tozasu_is_combat(lab):
                c += v
            else:
                nc += v
        return c, nc

    cp_c, cp_nc = tally(0, 1)              # creation pool (CP)
    xp_c, xp_nc = tally(2, 3)             # campaign pool (XP)
    begin = {"combat": cp_c, "noncombat": cp_nc}
    end = {"combat": cp_c + xp_c, "noncombat": cp_nc + xp_nc}
    return begin, end


def pct(d):
    t = d["combat"] + d["noncombat"]
    return 100.0 * d["combat"] / t if t else 0.0


def main():
    rows = []  # (name, school_label, begin, end, single_point)
    for name, (school, override) in LEDGERS.items():
        begin, end = parse_ledger(name, school, override)
        single = (name == "Masumune")
        rows.append((name, SCHOOL_LABEL[school], begin, end, single))
    tb, te = parse_tozasu()
    rows.append(("Tozasu", "none (peasant)", tb, te, False))

    print("| Character | School | Phase | Combat XP | Non-combat XP | Total "
          "| Combat % | Non-combat % |")
    print("|---|---|---|--:|--:|--:|--:|--:|")
    for name, school, begin, end, single in rows:
        phases = [("beginning", begin)] if single else [("beginning", begin), ("end", end)]
        for phase, d in phases:
            t = d["combat"] + d["noncombat"]
            print(f"| {name} | {school} | {phase} | {d['combat']:.0f} | {d['noncombat']:.0f} "
                  f"| {t:.0f} | {pct(d):.1f}% | {100 - pct(d):.1f}% |")

    print("\nChange over the campaign (combat share, beginning -> end):")
    for name, _school, begin, end, single in rows:
        if single:
            print(f"  {name}: {pct(begin):.1f}% (died at creation - single data point)")
        else:
            print(f"  {name}: {pct(begin):.1f}% -> {pct(end):.1f}% "
                  f"({pct(end) - pct(begin):+.1f} points)")


if __name__ == "__main__":
    main()
