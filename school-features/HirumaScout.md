# Hiruma Scout

**School ID:** `hiruma_scout`
**Category:** Investigator
**School Ring:** Air - Confirmed correct.
**School Knacks:** counterattack, double_attack, iaijutsu - All present and rollable. (Was previously listed as double_attack, feint, iaijutsu in `game_data.py`; corrected to match canonical `rules/04-schools.md` in the same round as the canonical-text sync. Hiruma no longer counts as a "feint school" so `feint_temp_vp` is no longer set for them, and they're no longer added to `SCHOOLS_WITH_TEMP_VOID` via the feint path — and the Hiruma Special Ability text doesn't mention temp VP either, so they're correctly out of that set now.)

---

## Special Ability

> The two allies fighting on your left and right have their TN to be hit raised by 5.

**Status:** Out of scope - requires positional tracking (who is adjacent to whom) not supported by the app.

**Implementation:** `app/game_data.py` (definition only).

---

## 1st Dan

> Roll one extra die on initiative, parry, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["initiative", "parry", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()`, `build_wound_check_formula()`, and `build_initiative_formula()`.

---

## 2nd Dan

> You get a free raise on parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> After making a successful or unsuccessful parry, add 2X to your next attack roll for any type of attack and to the damage roll for that attack if it hits, where X is your attack skill.  After your successful or unsuccessful parry resolves, you may immediately counterattack as an interrupt action at the cost of one action die, and this counterattack may be directed at anyone you can hit rather than being limited to the attacker whose strike you parried.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `hiruma_post_parry_bonus: true` and `hiruma_post_parry_amount: 2*attack_skill` in school_abilities.
- Client: auto-banks 2*attack_skill after any parry roll, applies as flat bonus to both attack roll AND damage roll on next attack via `rollAttack()` and `atkComputeDamage()`.
- The damage bonus is naturally gated on the attack hitting because damage is only rolled on hits ("to the damage roll for that attack if it hits").
- The free interrupt counterattack option ("After your successful or unsuccessful parry resolves, you may immediately counterattack...") is surfaced as a display note in `modal_result.html` via the `hiruma_post_parry_interrupt_counterattack` school_abilities flag. Not mechanized — it requires combat-phase tracking, so the player executes the counterattack manually.

**Questions (ANSWERED):**
- X is the attack skill rank.
- The bonus is a flat +2X added to the next attack AND damage roll.
- The bonus applies only to the attack against the parried attacker (the "or someone adjacent" language was removed from the canonical rules).

---

## 4th Dan

> Raise your current and maximum Air by 1.  Raising your Air now costs 5 fewer XP.  After rolling initiative, lower your action dice by 2, to a minimum of 1.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Action dice -2 is implemented in `dice.py` (`hiruma_4th_dan = school_id == "hiruma_scout" and dan >= 4`) and rendered on `sheet.html`.

**Implementation:** `app/services/dice.py` (`hiruma_4th_dan`), `app/templates/character/sheet.html` (initiative display).

---

## 5th Dan

> After making a successful or unsuccessful parry roll, the attacker deals 10 fewer light wounds on their next 2 damage rolls.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `hiruma_parry_reduce_lw: true` in school_abilities.
- Client: shows informational note after parry rolls: "the attacker deals 10 fewer light wounds on their next 2 damage rolls."

