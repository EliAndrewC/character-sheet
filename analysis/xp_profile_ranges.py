"""EXPLORATORY (not wired into the .md): a three-number XP profile per character.

For NPC-building guidance we want to know, of a character's total spent XP:
  1. combat %        (combat / total - the existing baseline split)
  2. rings %         (ring XP / total)            - freestanding
  3. school knacks % (school-knack XP / total)    - freestanding

(2) and (3) are subsets of combat, so they do NOT sum to 100 with anything; they
are independent "where did the XP go" readings. This script prints every
character (live party + all past-campaign PCs, beginning and end) and then the
ranges + suggested low/medium/high bands over the *final* state of each distinct
character (the population a GM would calibrate an NPC against).

Run:  PYTHONPATH=. python3 analysis/xp_profile_ranges.py
(needs xlrd for the .xls ledgers)
"""

from __future__ import annotations

import json
import re
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


def prof(rec):
    """combat%, rings%, knacks% from a record's raw XP totals."""
    t = rec["total"]
    if not t:
        return 0.0, 0.0, 0.0
    return (100.0 * rec["combat"] / t, 100.0 * rec["rings"] / t,
            100.0 * rec["knacks"] / t)


# ---------------------------------------------------------------------------
# builders -> {name, phase, school_id, total, combat, noncombat, rings, knacks}
# ---------------------------------------------------------------------------

def live_records():
    snap = json.loads(live._latest_snapshot().read_text())
    combat_adv = live._combat_advantage_labels()
    out = []
    for c in snap["characters"]:
        if c["id"] in live.EXCLUDE_IDS:
            continue
        b = calculate_xp_breakdown(c)
        cskills = live.combat_skill_names(c["school"])
        rings = b["rings"]["total"]
        foreign = b["foreign_knacks"]["total"]
        knacks = b["school_knacks"]["total"] + foreign  # school knacks incl. other-school
        skill_combat = sum(r["xp"] for sub in b["skills"]["subsections"]
                           for r in sub["rows"] if r["label"] in cskills)
        skill_total = sum(r["xp"] for sub in b["skills"]["subsections"] for r in sub["rows"])
        adv_combat = sum(r["xp"] for r in b["advantages"]["rows"]
                         if live._advantage_is_combat(r["label"], combat_adv))
        combat = (rings + knacks + b["combat_skills"]["total"]  # knacks already incl. foreign
                  + skill_combat + adv_combat)
        noncombat = ((skill_total - skill_combat)
                     + (b["advantages"]["total"] - adv_combat)
                     + b["honor_rank_recognition"]["total"])
        out.append({"name": c["name"], "phase": "current", "school_id": c["school"],
                    "total": combat + noncombat, "combat": combat, "noncombat": noncombat,
                    "rings": rings, "knacks": knacks})
    return out


def odt_records():
    out = []
    for name, _label, phase, rec in odt.RECORDS:
        dan = compute_dan(rec["knacks"])
        rings = sum(i["xp"] for i in ring_xp_items(rec["rings"], rec["school_ring"], dan=dan))
        knacks = sum(i["xp"] for i in school_knack_xp_items(rec["knacks"]))
        cskills = odt.combat_skill_names(rec["school"])
        sk = skill_xp_items(rec["skills"])
        skill_combat = sum(i["xp"] for i in sk["basic"] + sk["advanced"] if i["label"] in cskills)
        skill_total = sum(i["xp"] for i in sk["basic"] + sk["advanced"])
        adv_combat = sum(c for n, c in rec["advantages"] if n in odt.COMBAT_ADV)
        adv_total = sum(c for _n, c in rec["advantages"])
        atk = sum(i["xp"] for i in combat_skill_xp_items(rec["attack"], rec["parry"]))
        combat = rings + knacks + atk + skill_combat + adv_combat
        noncombat = (skill_total - skill_combat) + (adv_total - adv_combat)
        out.append({"name": name, "phase": phase, "school_id": rec["school"],
                    "total": combat + noncombat, "combat": combat, "noncombat": noncombat,
                    "rings": rings, "knacks": knacks})
    return out


_RINGS = {"fire", "water", "air", "earth", "void"}


def _is_ring(l):
    return l.split(" to ")[0].strip() in _RINGS and " to " in l


def _is_knack(l):
    if re.match(r"(second|third|fourth|fifth) dan$", l):
        return True
    if any(l.startswith(t) for t in led.KNACK_ALIASES):
        return True
    return any(l.startswith(kn) for kn in led.KNACK_NAMES)


def _ledger_detailed(name, school, override):
    import xlrd
    sh = xlrd.open_workbook(str(led.SHEETS / f"{name}Points.xls")).sheet_by_index(0)
    combat_skill = next(iter(led.combat_skill_names(school)), None)
    rows = []
    for r in range(sh.nrows):
        label = str(sh.cell_value(r, 0)).strip()
        xp = led.num(sh.cell_value(r, 1))
        if label == "" and xp == 0:
            continue
        rows.append((label, xp))
    earned_pos = [i for i, (l, _) in enumerate(rows) if l.lower().startswith("earned")]
    second = earned_pos[1] if len(earned_pos) >= 2 else len(rows)
    bal = 0.0
    boundary = second
    seen = False
    for i, (l, x) in enumerate(rows):
        if i >= second:
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
        return dict(rings=0.0, knacks=0.0, other_combat=0.0, noncombat=0.0)
    begin, end = blank(), blank()
    for i, (label, x) in enumerate(rows):
        b = led.bucket(label, x, combat_skill)
        if b == "budget" or x >= 0:
            continue
        amt = -x
        l = label.lower()
        if _is_ring(l):
            key = "rings"
        elif _is_knack(l):
            key = "knacks"
        elif b == "combat":
            key = "other_combat"
        else:
            key = "noncombat"
        end[key] += amt
        if i < boundary:
            begin[key] += amt
    return begin, end


def _tozasu_detailed():
    import xlrd
    sh = xlrd.open_workbook(str(led.SHEETS / "TozasuPoints.xls")).sheet_by_index(0)

    def pool(cl, cv):
        d = dict(rings=0.0, knacks=0.0, other_combat=0.0, noncombat=0.0)
        for r in range(1, sh.nrows):
            lab = str(sh.cell_value(r, cl)).strip()
            v = sh.cell_value(r, cv)
            if not isinstance(v, (int, float)) or lab == "":
                continue
            v = float(v)
            if v <= 0:
                continue
            l = lab.lower()
            if _is_ring(l):
                d["rings"] += v
            elif led._tozasu_is_combat(lab):
                d["other_combat"] += v
            else:
                d["noncombat"] += v
        return d
    cp, xp = pool(0, 1), pool(2, 3)
    end = {k: cp[k] + xp[k] for k in cp}
    return cp, end


def _pack(name, phase, school_id, d):
    combat = d["rings"] + d["knacks"] + d["other_combat"]
    total = combat + d["noncombat"]
    return {"name": name, "phase": phase, "school_id": school_id, "total": total,
            "combat": combat, "noncombat": d["noncombat"],
            "rings": d["rings"], "knacks": d["knacks"]}


def ledger_records():
    out = []
    for name, (school, override) in led.LEDGERS.items():
        begin, end = _ledger_detailed(name, school, override)
        phases = [("beginning", begin)] if name == "Masumune" else \
                 [("beginning", begin), ("end", end)]
        for phase, d in phases:
            out.append(_pack(name, phase, school, d))
    tb, te = _tozasu_detailed()
    out.append(_pack("Tozasu", "beginning", None, tb))
    out.append(_pack("Tozasu", "end", None, te))
    return out


def band(values):
    """low/med/high tertile cutoffs (33rd / 67th percentile)."""
    s = sorted(values)
    n = len(s)
    p33 = s[int(round(0.333 * (n - 1)))]
    p67 = s[int(round(0.667 * (n - 1)))]
    return p33, p67


def main():
    live_recs = live_records()
    past = odt_records() + ledger_records()

    def row(rec):
        c, rg, kn = prof(rec)
        label = SCHOOLS[rec["school_id"]].name if rec["school_id"] else "none (peasant)"
        return (f"| {rec['name']} | {rec['phase']} | {label} | {rec['total']:.0f} "
                f"| {c:.1f}% | {rg:.1f}% | {kn:.1f}% |")

    print("### Live party (current)\n")
    print("| Character | Phase | School | Total XP | Combat % | Rings % | Knacks % |")
    print("|---|---|---|--:|--:|--:|--:|")
    for r in live_recs:
        print(row(r))

    print("\n### Past-campaign characters\n")
    print("| Character | Phase | School | Total XP | Combat % | Rings % | Knacks % |")
    print("|---|---|---|--:|--:|--:|--:|")
    for r in past:
        print(row(r))

    # ranges + bands over each distinct character's FINAL state
    finals = list(live_recs)
    seen = set()
    for r in past:
        if r["phase"] in ("end", "beginning") and r["name"] not in seen:
            pass
    # pick end state if present else beginning (Masumune/Tozasu handled by name)
    by_name = {}
    for r in past:
        by_name.setdefault(r["name"], {})[r["phase"]] = r
    for name, phases in by_name.items():
        finals.append(phases.get("end", phases.get("beginning")))

    print(f"\n### Ranges and suggested bands (over each character's final state, "
          f"n={len(finals)})\n")
    print("| Metric | Min | Median | Mean | Max | low <= | high > |")
    print("|---|--:|--:|--:|--:|--:|--:|")
    for key, fn in [("Combat %", lambda r: prof(r)[0]),
                    ("Rings %", lambda r: prof(r)[1]),
                    ("Knacks %", lambda r: prof(r)[2])]:
        vals = [fn(r) for r in finals]
        lo, hi = band(vals)
        print(f"| {key} | {min(vals):.1f}% | {statistics.median(vals):.1f}% "
              f"| {statistics.mean(vals):.1f}% | {max(vals):.1f}% "
              f"| {lo:.1f}% | {hi:.1f}% |")

    print("\n(low/medium/high = below the 33rd percentile / between / above the "
          "67th percentile of the final-state population.)")

    # --- XP-tiered bands -----------------------------------------------------
    # rings% drifts up with total XP and knacks% drifts down, so a single band
    # mislabels low-XP builds. Split the population at a natural gap (the live
    # party sits at <=270 XP; the "finished" past PCs at >=319) and band each
    # tier separately. Combat% is XP-stable, so it keeps one band.
    TIER_BREAK = 300
    dev = [r for r in finals if r["total"] <= TIER_BREAK]
    vet = [r for r in finals if r["total"] > TIER_BREAK]
    print(f"\n### XP-tiered bands (break at {TIER_BREAK} total XP)\n")
    print(f"| Tier | n | Rings median | Rings low<=/high> | Knacks median "
          f"| Knacks low<=/high> |")
    print("|---|--:|--:|--:|--:|--:|")
    for label, recs in [("developing (<=300)", dev), ("veteran (>300)", vet)]:
        rv = [prof(r)[1] for r in recs]
        kv = [prof(r)[2] for r in recs]
        rl, rh = band(rv)
        kl, kh = band(kv)
        print(f"| {label} | {len(recs)} | {statistics.median(rv):.1f}% "
              f"| {rl:.1f} / {rh:.1f} | {statistics.median(kv):.1f}% "
              f"| {kl:.1f} / {kh:.1f} |")


if __name__ == "__main__":
    main()
