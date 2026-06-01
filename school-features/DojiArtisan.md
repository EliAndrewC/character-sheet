# Doji Artisan

**School ID:** `doji_artisan`
**Category:** Court
**School Ring:** "Air or Water" - Player chooses Air or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** counterattack, oppose_social, worldliness - Counterattack is rollable (varies). Oppose_social is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> You may spend a void point to counterattack as an interrupt action at the cost of one action die; this void point still gives your counterattack +1k1.  Your counterattack rolls receive a bonus equal to the attacker's roll divided by 5 (rounded down).

**Status:** Out of scope - requires combat-phase tracking (interrupt counterattack with VP cost and attacker-roll-based bonus).

**Implementation:** `app/game_data.py` (definition only).

---

## 1st Dan

> Roll one extra die on counterattack, manipulation, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["counterattack", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 2nd Dan

> You get a free raise on manipulation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is your culture skill, which may be spent on bragging, culture, heraldry, manipulation, counterattack, and wound checks after seeing your roll.  You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "culture"`
- `applicable_to: ["bragging", "culture", "heraldry", "manipulation", "counterattack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py` (third_dan dict).

---

## 4th Dan

> Raise your current and maximum School Ring by 1.  Raising your School Ring now costs 5 fewer XP.  When attacking a target who has not attacked you this round, or counterattacking a target who is attacking you for the first time this round, you receive a bonus equal to the current phase.

**Status:** Fully implemented.
- Ring raise (+1 to the chosen school ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "Air or Water", the 4th Dan ring raise applies to whichever ring was chosen.
- First-attack-of-the-round bonus: attack-type formulas (attack, counterattack, double_attack, lunge, athletics:attack) get a `doji_4th_dan_untouched_target` flag server-side. The attack modal's pre-roll page shows a checkbox labeled "Target's current attack is their first against me this round" for Doji Artisan 4th Dan characters. The checkbox covers both rule cases: regular attacks where the target hasn't attacked yet, and counterattacks where the target's incoming attack is their first this round. Ticking it reveals a 1-10 phase dropdown; the picked phase becomes a flat bonus that feeds the probability chart (`atkHitChance` / `atkAvgAttackRoll`), is auto-applied to the roll via `formula.flat`, and surfaces in the post-roll breakdown as a labeled "+N from Doji 4th Dan (phase N, target's first attack against you this round)" line.

---

## 5th Dan

> Add (X-10) / 5 to TN and contested rolls, where X is the TN or your opponent's roll.

**Status:** Fully implemented with three-tier skill grouping and auto-apply on combat/wound checks.

**Implementation:**
- Server: `app/services/dice.py` sets `doji_5th_dan_always` (always-TN skills/knacks/combat) or `doji_5th_dan_optional` (sometimes-TN skills) flags on `RollFormula`. Wound check formula gets `doji_5th_dan_wc` flag. Uses shared `_5TH_DAN_TN_ALWAYS` / `_5TH_DAN_TN_NEVER` constants (same groupings as Courtier 5th Dan).
- Client skill rolls: always-TN skills show TN input directly; sometimes-TN skills show checkbox then input; never-TN skills show nothing. Computes `floor((X - 10) / 5)` and displays adjusted total.
- Client attack rolls: bonus auto-calculated from selected TN, reflected in probability chart (`atkHitChance`, `atkAvgAttackRoll`), auto-applied to roll, shown in result breakdown.
- Client wound checks: bonus auto-calculated from light wounds, reflected in probability chart (`wcProbRow`), auto-applied to roll, shown in `bonus_sources`.

