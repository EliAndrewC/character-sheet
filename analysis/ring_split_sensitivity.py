"""EXPLORATORY (not wired into the .md): how sensitive is the combat-vs-non-combat
split to how we treat RING XP?

The baseline analysis counts all ring XP as combat. But Air and Water have real
non-combat uses, while Fire / Earth / Void are essentially pure combat. This
script re-scores every character (the live party + all past-campaign PCs) under
several alternative ring rules and reports how each one's combat share moves.

Run:  PYTHONPATH=. python3 analysis/ring_split_sensitivity.py
(needs xlrd for the .xls ledgers: pip install --break-system-packages xlrd)

MODELS (only the treatment of ring XP differs; everything else is identical to
the baseline categorization):

  M0  baseline        - all rings combat (current analysis)
  M1  AW-50           - Air & Water count 50% combat / 50% non-combat
  M2  AW-offschool    - Air & Water non-combat UNLESS that ring is the school
                        ring (school-ring Air/Water stays combat); F/E/V combat
  M3  AW-all-nc       - Air & Water fully non-combat (upper bound on the effect)
  M4  PC-Air>=4       - the player's idea: every 2->3 raise is combat (it buys a
                        Void point), but raising AIR to 4+ is non-combat unless
                        you are an Air school or Mirumoto (a parry school). All
                        other ring XP (incl. all Water, all F/E/V) stays combat.
  M5  PC-AirWater>=4  - as M4, plus Water to 4+ non-combat unless Water school.

Every model only ever moves ring XP OUT of combat, so a character's combat share
can only fall or stay vs M0; the questions are how much, who moves, and whether
the party orderings/spread change.
"""

from __future__ import annotations

import json
import statistics
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.services.xp import (  # noqa: E402
    calculate_xp_breakdown, ring_xp_items, school_knack_xp_items,
    combat_skill_xp_items, skill_xp_items, compute_dan,
)
from app.game_data import SCHOOLS  # noqa: E402
import combat_vs_noncombat_xp as live  # noqa: E402
import combat_xp_past_campaigns as odt  # noqa: E402
import combat_xp_past_ledgers as led  # noqa: E402

DUAL = ("Air", "Water")


def cap(s):
    return (s or "").strip().capitalize()


def frac_combat(model, ring, to_val, school_ring, school_id):
    """Fraction of a single ring raise's XP that counts as combat, per model."""
    sr = cap(school_ring)
    if model == "M0":
        return 1.0
    if model == "M1":
        return 0.5 if ring in DUAL else 1.0
    if model == "M2":
        return 0.0 if (ring in DUAL and ring != sr) else 1.0
    if model == "M3":
        return 0.0 if ring in DUAL else 1.0
    if model == "M4":
        if ring == "Air" and to_val >= 4 and sr != "Air" and school_id != "mirumoto_bushi":
            return 0.0
        return 1.0
    if model == "M5":
        if ring == "Air" and to_val >= 4 and sr != "Air" and school_id != "mirumoto_bushi":
            return 0.0
        if ring == "Water" and to_val >= 4 and sr != "Water":
            return 0.0
        return 1.0
    raise ValueError(model)


MODELS = ["M0", "M1", "M2", "M3", "M4", "M5"]


def score(rec, model):
    combat = rec["nonring_combat"]
    noncombat = rec["nonring_noncombat"]
    for ring, to_val, xp in rec["ring_raises"]:
        f = frac_combat(model, ring, to_val, rec["school_ring"], rec["school_id"])
        combat += xp * f
        noncombat += xp * (1 - f)
    total = combat + noncombat
    return 100.0 * combat / total if total else 0.0


# ---------------------------------------------------------------------------
# record builders -> normalized {name, source, school_id, school_ring,
#   nonring_combat, nonring_noncombat, ring_raises:[(ring, to_val, xp)]}
# ---------------------------------------------------------------------------

def ring_of(label):
    l = label.strip().lower()
    first = l.split(" to ")[0].strip()
    if first in {"fire", "water", "air", "earth", "void"} and " to " in l:
        import re
        m = re.search(r"to\s+(\d+)", l)
        if m:
            return first.capitalize(), int(m.group(1))
    return None


def live_records():
    snap = json.loads(live._latest_snapshot().read_text())
    combat_adv = live._combat_advantage_labels()
    out = []
    for c in snap["characters"]:
        if c["id"] in live.EXCLUDE_IDS:
            continue
        b = calculate_xp_breakdown(c)
        cskills = live.combat_skill_names(c["school"])
        ring_raises = [(r["label"], r["to_val"], r["xp"]) for r in b["rings"]["rows"]]
        skill_combat = sum(r["xp"] for sub in b["skills"]["subsections"]
                           for r in sub["rows"] if r["label"] in cskills)
        skill_total = sum(r["xp"] for sub in b["skills"]["subsections"] for r in sub["rows"])
        adv_combat = sum(r["xp"] for r in b["advantages"]["rows"]
                         if live._advantage_is_combat(r["label"], combat_adv))
        nonring_combat = (b["school_knacks"]["total"] + b["foreign_knacks"]["total"]
                          + b["combat_skills"]["total"] + skill_combat + adv_combat)
        nonring_noncombat = ((skill_total - skill_combat)
                             + (b["advantages"]["total"] - adv_combat)
                             + b["honor_rank_recognition"]["total"])
        out.append({
            "name": c["name"], "source": "live", "phase": "current",
            "school_id": c["school"], "school_ring": c.get("school_ring_choice", ""),
            "nonring_combat": nonring_combat, "nonring_noncombat": nonring_noncombat,
            "ring_raises": ring_raises,
        })
    return out


def odt_records():
    out = []
    for name, school_label, phase, rec in odt.RECORDS:
        dan = compute_dan(rec["knacks"])
        ring_raises = [(r["label"], r["to_val"], r["xp"])
                       for r in ring_xp_items(rec["rings"], rec["school_ring"], dan=dan)]
        cskills = odt.combat_skill_names(rec["school"])
        sk = skill_xp_items(rec["skills"])
        skill_combat = sum(i["xp"] for i in sk["basic"] + sk["advanced"] if i["label"] in cskills)
        skill_total = sum(i["xp"] for i in sk["basic"] + sk["advanced"])
        adv_combat = sum(c for n, c in rec["advantages"] if n in odt.COMBAT_ADV)
        adv_total = sum(c for _n, c in rec["advantages"])
        nonring_combat = (sum(i["xp"] for i in school_knack_xp_items(rec["knacks"]))
                          + sum(i["xp"] for i in combat_skill_xp_items(rec["attack"], rec["parry"]))
                          + skill_combat + adv_combat)
        nonring_noncombat = (skill_total - skill_combat) + (adv_total - adv_combat)
        out.append({
            "name": name, "source": "odt", "phase": phase,
            "school_id": rec["school"], "school_ring": rec["school_ring"],
            "nonring_combat": nonring_combat, "nonring_noncombat": nonring_noncombat,
            "ring_raises": ring_raises,
        })
    return out


def _ledger_detailed(name, school, override):
    import xlrd
    sh = xlrd.open_workbook(str(led.SHEETS / f"{name}Points.xls")).sheet_by_index(0)
    cs = led.combat_skill_names(school)
    combat_skill = next(iter(cs), None)
    rows = []
    for r in range(sh.nrows):
        label = str(sh.cell_value(r, 0)).strip()
        xp = led.num(sh.cell_value(r, 1))
        if label == "" and xp == 0:
            continue
        rows.append((label, xp))
    earned_pos = [i for i, (l, _) in enumerate(rows) if l.lower().startswith("earned")]
    second_earned = earned_pos[1] if len(earned_pos) >= 2 else len(rows)
    bal = 0.0
    boundary = second_earned
    seen = False
    for i, (l, x) in enumerate(rows):
        if i >= second_earned:
            break
        if l.lower().startswith("earned"):
            if not seen and override is not None:
                x = override
            seen = True
            bal += x
            continue
        if x < 0 and bal + x < 0:
            boundary = i
            break
        bal += x

    def blank():
        return {"nonring_combat": 0.0, "nonring_noncombat": 0.0, "ring_raises": []}
    begin, end = blank(), blank()
    for i, (l, x) in enumerate(rows):
        b = led.bucket(l, x, combat_skill)
        if b == "budget" or x >= 0:
            continue
        amt = -x
        ring = ring_of(l)
        for tgt, active in ((end, True), (begin, i < boundary)):
            if not active:
                continue
            if ring:
                tgt["ring_raises"].append((ring[0], ring[1], amt))
            elif b == "combat":
                tgt["nonring_combat"] += amt
            else:
                tgt["nonring_noncombat"] += amt
    return begin, end


def _tozasu_detailed():
    import xlrd
    sh = xlrd.open_workbook(str(led.SHEETS / "TozasuPoints.xls")).sheet_by_index(0)

    def blank():
        return {"nonring_combat": 0.0, "nonring_noncombat": 0.0, "ring_raises": []}

    def pool(col_label, col_val):
        d = blank()
        for r in range(1, sh.nrows):
            lab = str(sh.cell_value(r, col_label)).strip()
            v = sh.cell_value(r, col_val)
            if not isinstance(v, (int, float)) or lab == "":
                continue
            v = float(v)
            if v <= 0:
                continue
            ring = ring_of(lab)
            if ring:
                d["ring_raises"].append((ring[0], ring[1], v))
            elif led._tozasu_is_combat(lab):
                d["nonring_combat"] += v
            else:
                d["nonring_noncombat"] += v
        return d

    cp = pool(0, 1)
    xp = pool(2, 3)
    begin = cp
    end = {"nonring_combat": cp["nonring_combat"] + xp["nonring_combat"],
           "nonring_noncombat": cp["nonring_noncombat"] + xp["nonring_noncombat"],
           "ring_raises": cp["ring_raises"] + xp["ring_raises"]}
    return begin, end


def ledger_records():
    out = []
    for name, (school, override) in led.LEDGERS.items():
        begin, end = _ledger_detailed(name, school, override)
        sr = SCHOOLS[school].school_ring
        phases = [("beginning", begin)] if name == "Masumune" else \
                 [("beginning", begin), ("end", end)]
        for phase, d in phases:
            out.append({"name": name, "source": "xls", "phase": phase,
                        "school_id": school, "school_ring": sr, **d})
    tb, te = _tozasu_detailed()
    for phase, d in (("beginning", tb), ("end", te)):
        out.append({"name": "Tozasu", "source": "xls", "phase": phase,
                    "school_id": None, "school_ring": None, **d})
    return out


def ring_xp_by_kind(rec):
    """(dual-ring XP = Air+Water, pure-ring XP = F/E/V) for context."""
    dual = sum(xp for ring, _t, xp in rec["ring_raises"] if ring in DUAL)
    pure = sum(xp for ring, _t, xp in rec["ring_raises"] if ring not in DUAL)
    return dual, pure


def main():
    records = live_records() + odt_records() + ledger_records()

    hdr = "| Character | Phase | School | Air+Wtr / ring XP | " + " | ".join(MODELS) + " | M0->M3 |"
    print(hdr)
    print("|---|---|---|--:|" + "--:|" * len(MODELS) + "--:|")
    for rec in records:
        dual, pure = ring_xp_by_kind(rec)
        pcts = {m: score(rec, m) for m in MODELS}
        cells = " | ".join(f"{pcts[m]:.1f}%" for m in MODELS)
        drop = pcts["M0"] - pcts["M3"]
        label = SCHOOLS[rec["school_id"]].name if rec["school_id"] else "none (peasant)"
        print(f"| {rec['name']} | {rec['phase']} | {label} "
              f"| {dual:.0f}/{dual + pure:.0f} | {cells} | -{drop:.1f} |")

    # party-level summary on the LIVE party only (the headline numbers)
    print("\n### Live party (n=10) summary per model\n")
    print("| Stat | " + " | ".join(MODELS) + " |")
    print("|---|" + "--:|" * len(MODELS))
    livex = [r for r in records if r["source"] == "live"]
    for stat, fn in [("mean", statistics.mean), ("median", statistics.median),
                     ("min", min), ("max", max)]:
        vals = {m: fn([score(r, m) for r in livex]) for m in MODELS}
        print(f"| {stat} | " + " | ".join(f"{vals[m]:.1f}%" for m in MODELS) + " |")
    spreads = {m: max(score(r, m) for r in livex) - min(score(r, m) for r in livex) for m in MODELS}
    print(f"| spread | " + " | ".join(f"{spreads[m]:.1f}" for m in MODELS) + " |")


if __name__ == "__main__":
    main()
