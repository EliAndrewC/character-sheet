# Mirumoto Bushi

**School ID:** `mirumoto_bushi`
**Category:** Bushi
**School Ring:** Void - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable.

---

## Special Ability

> Your successful or unsuccessful parries give you a temporary void point.

**Status:** Fully implemented.
- Temporary Void Points are tracked for Mirumoto Bushi (school is in `SCHOOLS_WITH_TEMP_VOID` via the "temporary void" text in the special ability).
- The Temp Void counter appears on the View Sheet page with +/- buttons.
- Auto-grant of temp VP after parry is implemented.
  - Server: `app/routes/pages.py` passes `mirumoto_temp_vp_on_parry: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` auto-increments temp VP after parry rolls in `runRoll()`.

**Implementation:** `app/game_data.py`, `app/game_data.py` (SCHOOLS_WITH_TEMP_VOID membership), `app/routes/pages.py` (mirumoto_temp_vp_on_parry flag), `app/templates/character/sheet.html` (Temp Void counter, auto-grant in runRoll).

---

## 1st Dan

> Roll one extra die on parry, double attack, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["parry", "double_attack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

---

## 2nd Dan

> You get a free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> At the beginning of each round, you get 2X points, where X is your attack skill.  Each point may be spent to decrease the phase of one of your actions by 1 in order to parry, or to provide a bonus of +2 on a parry or any type of attack after seeing your roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `mirumoto_round_points: true` and `mirumoto_round_points_max: 2*attack_skill`. Client: tracking section shows a per-round points counter with +/- and Reset. "Spend 3rd Dan Point (+2)" button appears on attack and parry roll results. Points can be spent for +2 flat on the roll.
- Pool is auto-refilled to max when the character rolls initiative (new combat round), with a "Mirumoto 3rd Dan points refreshed for the new combat round" message in the initiative result modal. See `_resetPerRoundAbilities` in `app/templates/character/sheet.html`. No message appears when the pool was already full.

**Questions (ANSWERED):**
- X = attack skill rank. So 2 * attack_skill points per round.
- Per-round (reset each combat round).
- Points can be spent to lower action phase for a parry OR spent as +2 per point on attack/parry rolls.
- Points can be split between uses within a round.

---

## 4th Dan

> Raise your current and maximum Void by 1.  Raising your Void now costs 5 fewer XP.  Failed parries against your double attacks do not prevent the automatic serious wound, and against your regular attacks the number of extra rolled damage dice the failed parry reduced is cut in half (rounded down).

**Status:** Fully implemented.
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Failed parries" modification is implemented.
  - Server: `app/routes/pages.py` passes `mirumoto_parry_modifier: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` in `atkComputeDamage()` - vs double attacks: no parry reduction (auto SW preserved); vs regular attacks: parry reduction halved (rounded down).

---

## 5th Dan

> Your void points provide an extra +10 when spent on combat rolls.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `combat_vp_flat_bonus: 10` in void_spend_config when mirumoto_bushi and dan >= 5.
- Client: `app/templates/character/sheet.html` applies +10 per VP flat bonus on attack, wound check, and duel VP spending paths.

**Questions (ANSWERED):**
- The +10 is IN ADDITION to the normal +1k1 from void points. So each VP = +1k1 + 10 flat.
- "Combat rolls" includes wound checks (still need to confirm with user which specific roll types qualify).
- Does this apply to temporary void points as well?

No unit test for the pages.py flag (it's a template context variable), but the behavior is tested through the UI.

---

## Test References

