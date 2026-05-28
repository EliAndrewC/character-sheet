"""Analysis: L7R archery rules - hit rates and damage across archer skill,
target defense, distance, and evasion.

These are DRAFT archery rules not yet in the app. The model:

  - Attack roll: ``(Attack + Fire + extra_dice) k (Fire)`` with reroll-10s, plus
    a flat to-hit bonus = iaijutsu skill + free raises (the +5s several bushi
    techniques grant, which all stack onto archery) + the action investment of
    the shot (see "aim" below). Hit iff total >= TN.
  - TN to hit: ``5 + 5*Parry`` (+5 .. +20 by distance band, +5 if the target
    spends an action to bob/weave, + cover). A target who cannot see the shot
    coming has base TN 5 instead of 5 + 5*Parry; that surprise case is discussed
    in the .md but not swept here.
  - On a hit: 1 automatic serious wound (2 with Double Attack), PLUS a variable
    damage roll drawn from a profile (30/30/30/10 over 10k2/10k4/10k6/10k8) that
    shifts 10% toward 10k8 per 5 points the attack beats the TN; past +45 excess,
    extra increments add free raises (+5 each) to the damage. The damage roll
    becomes light wounds and the target makes a wound check.

Everything is computed DETERMINISTICALLY from the precomputed tables in
``app/data/`` (no live RNG), so reruns are byte-stable:

  - hit rate              = prob[True][(rolled, kept, TN - flat_bonus)]
  - attack-roll PMF       = successive differences of that survival function,
                            used to get the distribution of "excess over TN"
                            (which drives the damage profile shift)
  - expected serious wounds from the variable damage = the 10kX roll PMF
    convolved against wound_table[(light, Water+1, Water)]

Run from the repo root:

    PYTHONPATH=. python3 analysis/archery_hit_and_damage.py

Writes next to the script:

  * ArcheryHitAndDamage.csv  - every (archer x aim x target x evade x distance)
                               case, machine-readable.
  * ArcheryHitAndDamage.md   - curated formatted tables + analysis.
  * stdout                   - same as the .md.

ASSUMPTIONS / LIMITATIONS (also restated in the .md):
  - Wound checks use the standard reroll-on ``wound_table``. A target driven to
    *impaired* (serious wounds >= Earth) by the arrow's own automatic wound,
    just before its wound check, would fare slightly worse than shown - this
    affects only Double-Attack archers vs low-Earth targets.
  - "Average damage" figures are per single fresh hit. Light wounds accumulate
    across hits in real play, so the "shots to incapacitate" figure (out_at /
    expected SW per shot) is an UPPER bound; real fights end a little sooner.
  - A "free raise" on the damage roll is treated as +5 (only relevant past +45
    excess, which is rare outside elite alpha strikes).
"""

import csv
import pathlib

from app.data import prob, wound_table

REROLL = True            # archery attack & damage & (unimpaired) wound checks reroll 10s
WT_MAX_L = 150           # wound_table light-wound coverage ceiling; clamp beyond it

HERE = pathlib.Path(__file__).resolve().parent
CSV_PATH = HERE / "ArcheryHitAndDamage.csv"
MD_PATH = HERE / "ArcheryHitAndDamage.md"


# --------------------------------------------------------------------------- #
# Dice helpers (deterministic, from the precomputed tables)                   #
# --------------------------------------------------------------------------- #

def apply_cap(rolled, kept):
    """L7R 10k10 cap. Returns (rolled, kept, flat_bonus_from_overflow)."""
    flat = 0
    if rolled > 10:
        kept += rolled - 10
        rolled = 10
    if kept > 10:
        flat += 2 * (kept - 10)
        kept = 10
    kept = min(kept, rolled)
    return rolled, kept, flat


def surv(rolled, kept, t):
    """P(roll >= t). Min of an XkY roll is `kept` (all kept dice show 1)."""
    if t <= kept or t <= 1:
        return 1.0
    return prob[REROLL][(rolled, kept, t)]


_pmf_cache = {}

def pmf(rolled, kept):
    """PMF of an XkY roll as {value: probability}, from the survival function."""
    key = (rolled, kept)
    if key in _pmf_cache:
        return _pmf_cache[key]
    out = {}
    v = kept
    while True:
        p = surv(rolled, kept, v) - surv(rolled, kept, v + 1)
        if p > 1e-12:
            out[v] = p
        if surv(rolled, kept, v + 1) <= 0 and v > kept:
            break
        v += 1
        if v > 300:                       # pragma: no cover - tail guard
            break
    _pmf_cache[key] = out
    return out


BASE_PROFILE = {2: 0.3, 4: 0.3, 6: 0.3, 8: 0.1}

def shifted_profile(excess):
    """Damage profile after `floor(excess/5)` 10%-shifts toward 10k8.
    Returns (profile_dict, free_raises)."""
    incs = max(0, excess // 5)
    prof = dict(BASE_PROFILE)
    free_raises = 0
    for _ in range(incs):
        if prof.get(8, 0) >= 1.0 - 1e-9:
            free_raises += 1
            continue
        donor = next(k for k in (2, 4, 6) if prof.get(k, 0) > 1e-9)
        prof[donor] -= 0.1
        prof[8] = prof.get(8, 0) + 0.1
        if prof[donor] <= 1e-9:
            prof.pop(donor)
    return prof, free_raises


def dmg_mean(kept):
    return prob[REROLL][(10, kept)]


_esw_cache = {}

def exp_sw_from_damage(kept, dmg_flat, wc_rolled, wc_kept):
    """Expected serious wounds from a 10k(kept)+dmg_flat damage roll, against a
    (wc_rolled)k(wc_kept) wound check, via the canonical wound_table."""
    key = (kept, dmg_flat, wc_rolled, wc_kept)
    if key in _esw_cache:
        return _esw_cache[key]
    s = 0.0
    for light, p in pmf(10, kept).items():
        eff = min(WT_MAX_L, light + dmg_flat)
        s += p * wound_table[(eff, wc_rolled, wc_kept)]
    _esw_cache[key] = s
    return s


# --------------------------------------------------------------------------- #
# Resolve one (archer, target, situation) -> metrics                          #
# --------------------------------------------------------------------------- #

def resolve(rolled, kept, flat_bonus, auto_sw, flat_dmg, tn, water):
    """All-deterministic. Returns dict with hit, mean excess|hit, mean LW|hit,
    mean SW|hit, expected SW per shot."""
    wc_rolled, wc_kept = water + 1, water
    threshold = tn - flat_bonus                      # attack roll must reach this
    hit = surv(rolled, kept, threshold)
    if hit <= 0:
        return dict(hit=0.0, excess=None, lw=None, sw=None, sw_per_shot=0.0)

    tot_p = sx = slw = ssw = 0.0
    for v, pv in pmf(rolled, kept).items():
        if v < threshold:
            continue
        excess = v + flat_bonus - tn                 # >= 0 for these v
        prof, free_raises = shifted_profile(excess)
        dmg_flat = free_raises * 5 + flat_dmg
        e_lw = sum(w * (dmg_mean(k) + dmg_flat) for k, w in prof.items())
        e_sw = auto_sw + sum(
            w * exp_sw_from_damage(k, dmg_flat, wc_rolled, wc_kept)
            for k, w in prof.items()
        )
        tot_p += pv
        sx += pv * excess
        slw += pv * e_lw
        ssw += pv * e_sw

    if tot_p <= 0:                                   # pragma: no cover - hit>0 implies mass
        return dict(hit=hit, excess=None, lw=None, sw=None, sw_per_shot=0.0)
    mean_sw = ssw / tot_p
    return dict(hit=hit, excess=sx / tot_p, lw=slw / tot_p,
                sw=mean_sw, sw_per_shot=hit * mean_sw)


# --------------------------------------------------------------------------- #
# Profiles                                                                    #
# --------------------------------------------------------------------------- #

# Archer tiers. extra = extra rolled dice from knacks (+1k0 etc.); free_raise =
# the flat +5s techniques grant to attack; dmg = flat damage bonus; da = Double
# Attack (2 automatic serious wounds).
ARCHERS = [
    dict(name="Untrained",      atk=2, fire=2, iai=0, extra=0, free_raise=0,  dmg=0,  da=False),
    dict(name="Trained",        atk=3, fire=3, iai=0, extra=0, free_raise=0,  dmg=0,  da=False),
    dict(name="Iaijutsu adept", atk=3, fire=3, iai=3, extra=1, free_raise=5,  dmg=0,  da=False),
    dict(name="Veteran",        atk=4, fire=3, iai=4, extra=1, free_raise=5,  dmg=5,  da=True),
    dict(name="Elite",          atk=4, fire=4, iai=5, extra=2, free_raise=10, dmg=5,  da=True),
    dict(name="Master",         atk=5, fire=4, iai=5, extra=2, free_raise=15, dmg=10, da=True),
]

# Targets couple Parry (-> TN) with Water (-> wound check) and Earth (-> out at
# 2*Earth), spanning Parry 1..5.
TARGETS = [
    dict(name="Unarmored P1", parry=1, water=2, earth=2),
    dict(name="Light P2",     parry=2, water=2, earth=3),
    dict(name="Bushi P3",     parry=3, water=3, earth=3),
    dict(name="Heavy P4",     parry=4, water=3, earth=4),
    dict(name="Duelist P5",   parry=5, water=4, earth=4),
]

# Action investment baked into the to-hit bonus.
#   snap  = fire on your action, no holding, no extra action.
#   aimed = a committed single shot: ~+5 from holding + one +5 extra action.
AIMS = [("snap", 0), ("aimed", 10)]

DISTANCES = [("0-50ft", 5), ("50-100ft", 10), ("100-200ft", 15), ("200-400ft", 20)]


def archer_pool(a):
    """(rolled, kept, cap_flat) for the attack roll after the 10k10 cap."""
    return apply_cap(a["atk"] + a["fire"] + a["extra"], a["fire"])


def archer_flat(a, aim_bonus, cap_flat):
    return a["iai"] + a["free_raise"] + aim_bonus + cap_flat


def tn_of(target, dist_mod, evade):
    return 5 + 5 * target["parry"] + dist_mod + (5 if evade else 0)


def pool_label(a):
    r, k, f = archer_pool(a)
    return f"{r}k{k}" + (f"+{f}" if f else "")


# --------------------------------------------------------------------------- #
# Build the full sweep                                                        #
# --------------------------------------------------------------------------- #

def build_rows():
    rows = []
    for a in ARCHERS:
        rolled, kept, cap_flat = archer_pool(a)
        auto_sw = 2 if a["da"] else 1
        for aim_name, aim_bonus in AIMS:
            flat = archer_flat(a, aim_bonus, cap_flat)
            for t in TARGETS:
                out_at = 2 * t["earth"]
                for evade in (False, True):
                    for dist_name, dist_mod in DISTANCES:
                        tn = tn_of(t, dist_mod, evade)
                        m = resolve(rolled, kept, flat, auto_sw, a["dmg"], tn, t["water"])
                        shots = (out_at / m["sw_per_shot"]) if m["sw_per_shot"] > 0 else None
                        rows.append({
                            "archer": a["name"], "aim": aim_name,
                            "attack_pool": pool_label(a), "flat_to_hit": flat,
                            "double_attack": a["da"],
                            "target": t["name"], "parry": t["parry"],
                            "water": t["water"], "earth": t["earth"], "out_at": out_at,
                            "evade": evade, "distance": dist_name, "dist_mod": dist_mod,
                            "tn": tn,
                            "hit_pct": m["hit"], "mean_excess": m["excess"],
                            "mean_lw_on_hit": m["lw"], "mean_sw_on_hit": m["sw"],
                            "exp_sw_per_shot": m["sw_per_shot"],
                            "approx_shots_to_incap": shots,
                        })
    return rows


# --------------------------------------------------------------------------- #
# CSV                                                                         #
# --------------------------------------------------------------------------- #

CSV_COLS = [
    "archer", "aim", "attack_pool", "flat_to_hit", "double_attack",
    "target", "parry", "water", "earth", "out_at",
    "evade", "distance", "dist_mod", "tn",
    "hit_pct", "mean_excess", "mean_lw_on_hit", "mean_sw_on_hit",
    "exp_sw_per_shot", "approx_shots_to_incap",
]

def write_csv(rows, path):
    def f(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for r in rows:
            w.writerow([f(r[c]) for c in CSV_COLS])


# --------------------------------------------------------------------------- #
# Markdown rendering                                                          #
# --------------------------------------------------------------------------- #

def md_table(headers, data_rows, right_from=1):
    """headers: list[str]; data_rows: list[list[str]]. Columns from `right_from`
    on are right-aligned."""
    sep = []
    for i in range(len(headers)):
        sep.append("---:" if i >= right_from else ":---")
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(sep) + "|"]
    for r in data_rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def pc(x):
    return "—" if x is None else f"{100*x:.1f}%"

def f2(x):
    return "—" if x is None else f"{x:.2f}"

def f1(x):
    return "—" if x is None else f"{x:.1f}"


def get(rows, **kw):
    """First row matching all kw."""
    for r in rows:
        if all(r[k] == v for k, v in kw.items()):
            return r
    return None                                       # pragma: no cover - all cases exist


def format_markdown(rows):
    out = []
    out.append(MD_INTRO)

    # 0. Archer profile definitions
    out.append("\n## Archer tiers used in these tables\n")
    hdr = ["tier", "Attack", "Fire", "iaijutsu", "extra dice", "free-raise +",
           "dmg +", "Double Attack", "attack pool", "auto SW"]
    drows = []
    for a in ARCHERS:
        drows.append([
            a["name"], str(a["atk"]), str(a["fire"]), str(a["iai"]),
            f"+{a['extra']}k0" if a["extra"] else "-",
            f"+{a['free_raise']}" if a["free_raise"] else "-",
            f"+{a['dmg']}" if a["dmg"] else "-",
            "yes" if a["da"] else "no", pool_label(a),
            "2" if a["da"] else "1",
        ])
    out.append(md_table(hdr, drows, right_from=1))
    out.append(
        "\n*The flat to-hit bonus that always counts toward archery = iaijutsu "
        "skill + free-raise +s + the action investment of the shot. Tables below "
        "are an **aimed** shot (+10: roughly one held action plus one +5 extra "
        "action) unless the table says **snap**.*"
    )

    # 1. Hit rate by distance, evade vs Bushi P3 (aimed)
    out.append("\n## 1. Hit rate by distance - vs a standard Bushi (Parry 3), aimed shot\n")
    out.append("Each cell is *not evading / evading* (the target spending one action to bob/weave, +5 TN).\n")
    hdr = ["archer"] + [d for d, _ in DISTANCES]
    drows = []
    for a in ARCHERS:
        cells = [a["name"]]
        for dname, _ in DISTANCES:
            r0 = get(rows, archer=a["name"], aim="aimed", target="Bushi P3", evade=False, distance=dname)
            r1 = get(rows, archer=a["name"], aim="aimed", target="Bushi P3", evade=True, distance=dname)
            cells.append(f"{pc(r0['hit_pct'])} / {pc(r1['hit_pct'])}")
        drows.append(cells)
    out.append(md_table(hdr, drows))

    # 2. Hit rate by target Parry (evading, 50-100ft, aimed)
    out.append("\n## 2. Hit rate by target Parry - evading target at 50-100 ft, aimed shot\n")
    hdr = ["archer"] + [t["name"] for t in TARGETS]
    drows = []
    for a in ARCHERS:
        cells = [a["name"]]
        for t in TARGETS:
            r = get(rows, archer=a["name"], aim="aimed", target=t["name"], evade=True, distance="50-100ft")
            cells.append(pc(r["hit_pct"]))
        drows.append(cells)
    out.append(md_table(hdr, drows))

    # 3. Fire sweep (isolate kept dice): Attack 3, no other bonuses, aimed, vs Bushi P3 evading
    out.append("\n## 3. Marginal value of Fire - Attack 3, no knacks/iaijutsu, aimed, vs evading Bushi P3\n")
    out.append("Isolates the kept-dice ring. Attack roll = (3 + Fire)k(Fire).\n")
    hdr = ["Fire", "attack pool"] + [d for d, _ in DISTANCES]
    drows = []
    for fire in (2, 3, 4, 5):
        rolled, kept, cap_flat = apply_cap(3 + fire, fire)
        flat = 0 + 0 + 10 + cap_flat                  # aimed only
        cells = [str(fire), f"{rolled}k{kept}" + (f"+{cap_flat}" if cap_flat else "")]
        for dname, dmod in DISTANCES:
            tn = tn_of({"parry": 3}, dmod, True)
            h = resolve(rolled, kept, flat, 1, 0, tn, 3)["hit"]
            cells.append(pc(h))
        drows.append(cells)
    out.append(md_table(hdr, drows))

    # 4. Average damage when you hit, vs Bushi P3, 50-100ft evading, aimed
    out.append("\n## 4. Damage when you DO hit - vs evading Bushi P3 at 50-100 ft, aimed\n")
    out.append("Light wounds and serious wounds are per single fresh hit. "
               "`exp SW/shot` = hit% x SW/hit folds accuracy and damage together.\n")
    hdr = ["archer", "hit%", "mean excess", "mean LW/hit", "SW/hit", "exp SW/shot"]
    drows = []
    for a in ARCHERS:
        r = get(rows, archer=a["name"], aim="aimed", target="Bushi P3", evade=True, distance="50-100ft")
        drows.append([a["name"], pc(r["hit_pct"]), f1(r["mean_excess"]),
                      f1(r["mean_lw_on_hit"]), f2(r["mean_sw_on_hit"]), f2(r["exp_sw_per_shot"])])
    out.append(md_table(hdr, drows))

    # 5. Matchup matrix: expected SW per shot, archer x target (evading, 50-100ft, aimed)
    out.append("\n## 5. Matchup matrix - expected serious wounds per shot\n")
    out.append("Evading target at 50-100 ft, aimed shot. (Out at 2xEarth: P1=4, "
               "P2/P3=6, P4/P5=8.) Below it, the same cases as approximate shots "
               "to incapacitate.\n")
    hdr = ["archer \\ target"] + [t["name"] for t in TARGETS]
    drows = []
    for a in ARCHERS:
        cells = [a["name"]]
        for t in TARGETS:
            r = get(rows, archer=a["name"], aim="aimed", target=t["name"], evade=True, distance="50-100ft")
            cells.append(f2(r["exp_sw_per_shot"]))
        drows.append(cells)
    out.append(md_table(hdr, drows))
    out.append("")
    drows = []
    for a in ARCHERS:
        cells = [a["name"]]
        for t in TARGETS:
            r = get(rows, archer=a["name"], aim="aimed", target=t["name"], evade=True, distance="50-100ft")
            cells.append(f1(r["approx_shots_to_incap"]))
        drows.append(cells)
    out.append("**Approximate shots to incapacitate** (upper bound; ignores light-wound accumulation):\n")
    out.append(md_table(hdr, drows))

    # 6. The two named reference scenarios
    out.append("\n## 6. Two reference scenarios, across archer tiers (aimed)\n")
    out.append("**A** = Parry 3, NOT evading, close range (0-50 ft). "
               "**B** = Parry 4, evading, 75 ft (50-100 ft band).\n")
    hdr = ["archer", "A hit%", "A SW/hit", "A exp SW/shot", "B hit%", "B SW/hit", "B exp SW/shot"]
    drows = []
    for a in ARCHERS:
        ra = get(rows, archer=a["name"], aim="aimed", target="Bushi P3", evade=False, distance="0-50ft")
        rb = get(rows, archer=a["name"], aim="aimed", target="Heavy P4", evade=True, distance="50-100ft")
        drows.append([a["name"], pc(ra["hit_pct"]), f2(ra["mean_sw_on_hit"]), f2(ra["exp_sw_per_shot"]),
                      pc(rb["hit_pct"]), f2(rb["mean_sw_on_hit"]), f2(rb["exp_sw_per_shot"])])
    out.append(md_table(hdr, drows))

    # 7. Snap vs aimed, mid archer
    out.append("\n## 7. Action investment - snap vs aimed (Iaijutsu adept vs evading Bushi P3)\n")
    out.append("The gap is the +10 a committed shot buys; the uncapped extreme "
               "(holding a full round of actions into one alpha strike) is not "
               "swept here and is the system's biggest balance lever.\n")
    hdr = ["distance", "snap hit%", "aimed hit%", "snap SW/hit", "aimed SW/hit"]
    drows = []
    for dname, _ in DISTANCES:
        rs = get(rows, archer="Iaijutsu adept", aim="snap", target="Bushi P3", evade=True, distance=dname)
        ra = get(rows, archer="Iaijutsu adept", aim="aimed", target="Bushi P3", evade=True, distance=dname)
        drows.append([dname, pc(rs["hit_pct"]), pc(ra["hit_pct"]),
                      f2(rs["mean_sw_on_hit"]), f2(ra["mean_sw_on_hit"])])
    out.append(md_table(hdr, drows))

    out.append(MD_NOTES)
    return "\n".join(out) + "\n"


MD_INTRO = """\
# Archery: hit rates and damage

Draft L7R archery rules, modeled deterministically from the precomputed dice
tables in `app/data/` (`prob`, `wound_table`). Generated by
`analysis/archery_hit_and_damage.py`; the full sweep
(6 archer tiers x 2 aim levels x 5 targets x evade/no-evade x 4 distances = 480
rows) is in `ArcheryHitAndDamage.csv`.

**The model.** Attack roll `(Attack + Fire + extra dice)k(Fire)` + a flat bonus
(iaijutsu + free-raise +5s + the shot's action investment), vs TN `5 + 5*Parry`
plus distance (+5/+10/+15/+20), +5 if the target bob/weaves, + cover. A hit deals
1 automatic serious wound (2 with Double Attack) plus a variable `10k2..10k8`
damage roll whose profile shifts toward `10k8` by one 10% step per 5 points the
attack beats the TN. That damage becomes light wounds; the target makes a
`(Water+1)k(Water)` wound check. Out (mortally wounded) at serious wounds
>= 2 x Earth.

**Columns.** `hit%` = chance the shot lands. `mean excess` = average points the
attack beats the TN by, given a hit (this drives damage). `mean LW/hit` = average
light wounds from the variable damage roll. `SW/hit` = average serious wounds per
landed arrow (automatic + wound-check). `exp SW/shot` = `hit% x SW/hit`, the
single best accuracy-plus-lethality number.
"""

MD_NOTES = """\
## Reading the results

- **Goal check.** Distance and evasion now bite normal archers hard (a Trained
  archer vs an evading Bushi at 50-100 ft is well under a coin flip), while a
  landed arrow remains far more lethal than a melee blow - so "miss more, hurt
  more" holds across the skill range. The exception is the top tiers, whose flat
  technique bonuses overrun the TN at every band.
- **Lethality is high and skill-amplified.** Because beating the TN by more
  shifts the damage profile toward 10k8, the same bonuses that make elite archers
  accurate also make their hits near-maximal. `exp SW/shot` against a standard
  Bushi climbs steeply across the tiers.
- **Fire vs flat bonuses.** A point of Fire is `+1k1` - it adds both a rolled and
  a kept die, worth ~+7 to the roll average - so it beats a single +5 free raise
  on hit% at every range except point-blank (where both already auto-hit). Flat
  stacking still dominates the top tiers through *quantity*, not per-unit power:
  iaijutsu plus several technique free raises plus the shot's action investment
  pile up additively (+20 to +30) far more cheaply than buying three or four Fire
  ranks, and stack on top of already-high Fire.

## Caveats (see also the script docstring)

- Wound checks use the standard reroll-on `wound_table`; a target driven to
  *impaired* by the arrow's own automatic wound (Earth <= auto SW) would take
  slightly more - this nudges Double-Attack archers vs Earth-2 targets upward.
- Damage figures are per single fresh hit. Light wounds accumulate in real play,
  so "approx shots to incapacitate" is an upper bound.
- The **action-investment / alpha-strike** axis (holding a whole round of actions
  into one shot) is only sampled here as snap vs aimed (+0 vs +10). Its uncapped
  upper end is the system's largest balance lever: a full-round alpha strike can
  add +20 or more to a single shot, and scales with Void.
- A "free raise" on damage is treated as +5 (matters only past +45 excess).
"""


def main():
    rows = build_rows()
    write_csv(rows, CSV_PATH)
    md = format_markdown(rows)
    MD_PATH.write_text(md)
    print(f"wrote {CSV_PATH}")
    print(f"wrote {MD_PATH}")
    print(f"({len(rows)} data rows)\n")
    print(md)


if __name__ == "__main__":
    main()
