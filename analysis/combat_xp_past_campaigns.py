"""Analysis: combat vs non-combat XP for two PCs from *past* campaigns.

A companion to combat_vs_noncombat_xp.py (the live-party snapshot). That script
reads the production database; this one looks backward, at two characters from
earlier campaigns that predate the character-builder app:

  - Kitsuki Tetsu     (Kitsuki Magistrate)
  - Wakuu             (Brotherhood of Shinsei Monk)

For each we have the character sheet at the *beginning* and the *end* of its
campaign (the old hand-maintained .odt sheets in old-character-sheets/), so we
can ask not just "what was the split" but "did the combat share move over the
campaign?".

------------------------------------------------------------------------------
WHY THIS IS A SEPARATE, HAND-ENCODED SCRIPT
------------------------------------------------------------------------------

These sheets predate the app, so there is no database row to read and nothing to
script the parse from - the stats below were read by hand out of the .odt files
(see old-character-sheets/*.odt). What IS reused is everything downstream of the
raw stats: the XP cost tables, the per-raise ring/knack/skill costing (including
the 4th-Dan school-ring discount), and the exact combat-vs-non-combat
categorization rules - all imported from the app and from
combat_vs_noncombat_xp.py, so these characters are measured the same way as the
live party. The hand-entered numbers are the only manual part; the arithmetic is
the engine's.

Run it:  PYTHONPATH=. python3 analysis/combat_xp_past_campaigns.py

------------------------------------------------------------------------------
TWO DELIBERATE DIFFERENCES FROM THE LIVE ANALYSIS (documented in the .md)
------------------------------------------------------------------------------

  1. Honor / Rank / Recognition contribute ZERO here. In these older campaigns
     those advanced through play, not by spending XP - and indeed each sheet's
     hand-tracked "spent" total reconciles to the computed buy-cost only when
     HRR is left out (Wakuu reconciles to the exact XP; Tetsu to within ~2%, the
     drift of a hand-maintained sheet). The live Wasp analysis counts HRR as
     non-combat, but for Wasp it is small (Rank is free and locked), so the two
     remain broadly comparable.

  2. The campaign-specific advantages/disadvantages on these sheets are not in
     the app's (Wasp) game_data, so their XP costs are read straight off the
     sheet (the number in parentheses / brackets) rather than looked up. The
     combat/non-combat call on each advantage still follows the live rules:
     combat iff it has a combat application.

Combat-advantage calls specific to these two sheets (see COMBAT_ADV below):
  - Famous Sword  -> combat. Borderline (glory + combat use); counted as combat
    by GM call, the same way Quick Healer is, and documented as debatable.
  - Great Destiny -> combat. "It takes one additional serious wound to kill you"
    is pure combat survivability, a direct parallel to Quick Healer / Strength
    of the Earth, which the live rules already bucket as combat.
  - Discerning    -> NON-combat. It boosts investigation/interrogation *rolls*,
    which are out-of-combat info-gathering. Investigation counts as a combat
    skill for Kitsuki only because the 3rd Dan turns the skill *rank* into free
    raises usable on attacks - that combat weight is captured in the skill XP,
    not the advantage. (The live rule excludes it; we follow suit.)
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.services.xp import (  # noqa: E402
    combat_skill_xp_items,
    compute_dan,
    ring_xp_items,
    school_knack_xp_items,
    skill_xp_items,
)
from combat_vs_noncombat_xp import combat_skill_names  # noqa: E402

# Advantages with a combat application on these two sheets. Lucky / Strength of
# the Earth / Quick Healer match the live COMBAT_ADVANTAGE_IDS; Famous Sword and
# Great Destiny are the campaign-specific additions justified in the docstring.
COMBAT_ADV = {
    "Lucky",
    "Strength of the Earth",
    "Quick Healer",
    "Famous Sword",
    "Great Destiny",
}


def _sum(items):
    return sum(i["xp"] for i in items)


def categorize(rec: dict) -> dict:
    """Split one hand-encoded sheet into combat vs non-combat XP."""
    dan = compute_dan(rec["knacks"])
    rings = _sum(ring_xp_items(rec["rings"], rec["school_ring"], dan=dan))
    knacks = _sum(school_knack_xp_items(rec["knacks"]))
    atk_parry = _sum(combat_skill_xp_items(rec["attack"], rec["parry"]))

    sk = skill_xp_items(rec["skills"])
    combat_skills = combat_skill_names(rec["school"])
    skill_combat = sum(
        i["xp"] for i in sk["basic"] + sk["advanced"] if i["label"] in combat_skills
    )
    skill_noncombat = _sum(sk["basic"]) + _sum(sk["advanced"]) - skill_combat

    adv_combat = sum(c for n, c in rec["advantages"] if n in COMBAT_ADV)
    adv_noncombat = sum(c for n, c in rec["advantages"] if n not in COMBAT_ADV)

    combat = rings + knacks + atk_parry + skill_combat + adv_combat
    noncombat = skill_noncombat + adv_noncombat
    total = combat + noncombat
    return {
        "combat": combat,
        "noncombat": noncombat,
        "total": total,
        "combat_pct": 100.0 * combat / total if total else 0.0,
        "stated": rec["stated"],
        "dan": dan,
    }


# ---------------------------------------------------------------------------
# Hand-encoded sheets (read from old-character-sheets/*.odt). Rings/knacks start
# at the L7R defaults (2, school ring 3); the engine applies the free school-ring
# raises and the 4th-Dan discount from the Dan implied by the knack ranks.
# ---------------------------------------------------------------------------

RECORDS = [
    ("Kitsuki Tetsu", "Kitsuki Magistrate", "beginning", dict(
        school="kitsuki_magistrate", school_ring="Water", stated=299,
        rings={"Fire": 3, "Water": 5, "Air": 3, "Earth": 3, "Void": 3},
        knacks={"discern_honor": 5, "iaijutsu": 5, "presence": 5},
        attack=3, parry=4,
        skills={"commerce": 1, "interrogation": 5, "history": 1, "underworld": 1,
                "bragging": 1, "culture": 2, "etiquette": 2, "intimidation": 1,
                "investigation": 3, "sincerity": 3, "law": 3, "precepts": 3,
                "tact": 3, "strategy": 1},
        advantages=[("Good Reputation", 3), ("Kind Eye", 3), ("Discerning", 5),
                    ("Fierce", 2), ("Famous Sword", 5), ("Equestrian", 3)],
    )),
    ("Kitsuki Tetsu", "Kitsuki Magistrate", "end", dict(
        school="kitsuki_magistrate", school_ring="Water", stated=466,
        rings={"Fire": 3, "Water": 5, "Air": 3, "Earth": 5, "Void": 5},
        knacks={"discern_honor": 5, "iaijutsu": 5, "presence": 5},
        attack=4, parry=5,
        skills={"interrogation": 5, "history": 3, "underworld": 1, "bragging": 1,
                "culture": 2, "etiquette": 2, "intimidation": 1, "investigation": 5,
                "sincerity": 3, "law": 5, "precepts": 3, "tact": 3, "strategy": 5},
        advantages=[("Good Reputation", 3), ("Great Destiny", 8), ("Kind Eye", 3),
                    ("Discerning", 5), ("Fierce", 2), ("Famous Sword", 5),
                    ("Equestrian", 3), ("Friend of the Clans", 3),
                    ("Major Ally: Battalion Commander", 2)],
    )),
    ("Wakuu", "Brotherhood of Shinsei Monk", "beginning", dict(
        school="brotherhood_of_shinsei_monk", school_ring="Air", stated=247,
        rings={"Fire": 4, "Water": 2, "Air": 4, "Earth": 3, "Void": 4},
        knacks={"conviction": 4, "otherworldliness": 4, "worldliness": 4},
        attack=4, parry=5,
        skills={"acting": 3, "commerce": 1, "sincerity": 2, "sneaking": 3,
                "precepts": 4, "tact": 1},
        advantages=[("Strength of the Earth", 8), ("Quick Healer", 3),
                    ("Worldly", 4), ("Steward", 6)],
    )),
    ("Wakuu", "Brotherhood of Shinsei Monk", "end", dict(
        school="brotherhood_of_shinsei_monk", school_ring="Air", stated=375,
        rings={"Fire": 4, "Water": 3, "Air": 4, "Earth": 4, "Void": 5},
        knacks={"conviction": 5, "otherworldliness": 5, "worldliness": 5},
        attack=5, parry=5,
        skills={"acting": 3, "commerce": 1, "underworld": 1, "bragging": 1,
                "etiquette": 1, "sincerity": 5, "sneaking": 3, "law": 2,
                "precepts": 5, "tact": 2, "strategy": 1},
        advantages=[("Strength of the Earth", 8), ("Quick Healer", 3),
                    ("Worldly", 4), ("Steward", 6)],
    )),
]


def main() -> None:
    rows = [(name, school, phase, categorize(rec))
            for name, school, phase, rec in RECORDS]

    print("| Character | School | Phase | Combat XP | Non-combat XP | Total "
          "| Combat % | Non-combat % |")
    print("|---|---|---|--:|--:|--:|--:|--:|")
    for name, school, phase, r in rows:
        print(f"| {name} | {school} | {phase} | {r['combat']} | {r['noncombat']} "
              f"| {r['total']} | {r['combat_pct']:.1f}% | {100 - r['combat_pct']:.1f}% |")

    print("\nChange over the campaign (combat share, beginning -> end):")
    by_name: dict = {}
    for name, _school, phase, r in rows:
        by_name.setdefault(name, {})[phase] = r
    for name, phases in by_name.items():
        b, e = phases["beginning"], phases["end"]
        delta = e["combat_pct"] - b["combat_pct"]
        print(f"  {name}: {b['combat_pct']:.1f}% -> {e['combat_pct']:.1f}% "
              f"({delta:+.1f} points)")

    print("\nReconciliation (computed buy-cost vs the sheet's hand-tracked "
          "'spent', HRR excluded):")
    for name, _school, phase, r in rows:
        print(f"  {name} {phase}: computed {r['total']} vs stated {r['stated']} "
              f"(diff {r['total'] - r['stated']:+d})")


if __name__ == "__main__":
    main()
