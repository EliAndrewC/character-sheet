# Courtier

**School ID:** `courtier`
**Category:** Court
**School Ring:** Air - Confirmed correct.
**School Knacks:** discern_honor, oppose_social, worldliness - Discern_honor is rollable (Air). Oppose_social is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Add your Air to attack and damage rolls.

**Status:** Fully implemented.
- `dice.py` adds Air ring value as flat bonus to damage rolls when `school_id == "courtier"`.
- `dice.py` adds Air ring value as flat bonus to attack rolls when `school_id == "courtier"`.
- Both include labeled bonus sources (e.g., "+3 from Courtier (Air)").

**Implementation:** `app/services/dice.py` (damage flat bonus), `app/services/dice.py` (attack flat bonus).

---

## 1st Dan

> Roll one extra die on tact, manipulation, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["tact", "manipulation", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 2nd Dan

> You get a free raise on manipulation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "manipulation"`
- Applied as +5 flat bonus on manipulation rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is your tact skill, which may be spent on heraldry, manipulation, sincerity, tact, attack, and wound checks after seeing your roll.  You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "tact"`
- `applicable_to: ["heraldry", "manipulation", "sincerity", "tact", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py` (third_dan dict).

**Missing:** None - 3rd Dan is fully tested.

---

## 4th Dan

> Raise your current and maximum Air by 1.  Raising your Air now costs 5 fewer XP.  Once per target per conversation or fight, you get a temporary void point after a successful attack or manipulation roll.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Temporary Void Points are tracked (school has `SCHOOLS_WITH_TEMP_VOID` via the technique text mentioning "temporary void").
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Server: `app/routes/pages.py` passes `courtier_temp_vp_on_hit: true` in school_abilities.
- Client: shows "Gain 1 temp VP (once per target)" button on attack HIT result and after manipulation skill rolls.

**Implementation:** Temp VP counter in `app/templates/character/sheet.html`, `app/routes/pages.py` (courtier_temp_vp_on_hit flag).

---

## 5th Dan

> Add your Air to TN and contested rolls.  This stacks with your Special Ability for attack rolls.

**Status:** Fully implemented.
- Skills: `app/services/dice.py:build_skill_formula()` adds +Air flat when courtier and dan >= 5.
- Knacks: `app/services/dice.py:build_knack_formula()` adds +Air flat when courtier and dan >= 5.
- Combat: `app/services/dice.py:build_combat_formula()` adds +Air flat when courtier and dan >= 5.
- Stacks with the Special Ability +Air on attacks (applied via _annotate_attack_type).

