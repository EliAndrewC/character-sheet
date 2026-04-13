# Hiruma Scout

**School ID:** `hiruma_scout`
**Category:** Investigator
**School Ring:** Air - Confirmed correct.
**School Knacks:** double_attack, feint, iaijutsu - All present and rollable. Feint knack means school is in `SCHOOLS_WITH_TEMP_VOID`.

---

## Special Ability

> The two allies fighting on your left and right have their TN to be hit raised by 5.

**Status:** Out of scope - requires positional tracking (who is adjacent to whom) not supported by the app.

**Implementation:** `app/game_data.py:1279-1281` (definition only).

**Unit tests:** None.
**Clicktests:** None.

---

## 1st Dan

> Roll an extra die on initiative, parry, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["initiative", "parry", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()`, `build_wound_check_formula()`, and `build_initiative_formula()`.

**Unit tests:** None specific to Hiruma 1st Dan initiative logic.
**Clicktests:**
- `test_school_abilities.py::test_hiruma_1st_dan_formula_extra_die`

**Missing:**
- [ ] Behavioral clicktest: roll initiative, verify extra die from 1st Dan in dice count

---

## 2nd Dan

> You get a free raise to all parry rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "parry"`
- Applied as +5 flat bonus on parry rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_hiruma_2nd_dan_parry_bonus`

**Missing:**
- [ ] Behavioral clicktest: roll parry, verify +5 from 2nd Dan in result breakdown

---

## 3rd Dan

> After making a successful or unsuccessful parry, add 2X to your next attack and damage roll against the attacker or someone adjacent to them, where X is your attack skill.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `hiruma_post_parry_bonus: true` and `hiruma_post_parry_amount: 2*attack_skill` in school_abilities.
- Client: auto-banks 2*attack_skill after any parry roll, applies as flat bonus to both attack roll AND damage roll on next attack via `rollAttack()` and `atkComputeDamage()`.

**Clicktests:**
- `test_school_abilities.py::test_hiruma_post_parry_bonus`

**Missing:**
- [ ] Behavioral clicktest: roll a parry, verify bonus is auto-banked, then roll an attack and verify the bonus is applied to the attack total

**Questions (ANSWERED):**
- X is the attack skill rank.
- The bonus is a flat +2X added to the next attack AND damage roll.
- "Against the attacker or someone adjacent to them" means the bonus applies to the next attack against the original attacker or their neighbors.

---

## 4th Dan

> Raise your current and maximum Air by 1. Raising your Air now costs 5 fewer XP. After rolling initiative, lower all of your action dice by 2, to a minimum of 1.

**Status:** Fully implemented.
- Ring raise (+1 Air, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Action dice -2 is implemented in `dice.py:503` (`hiruma_4th_dan = school_id == "hiruma_scout" and dan >= 4`) and rendered on `sheet.html`.

**Implementation:** `app/services/dice.py:503` (`hiruma_4th_dan`), `app/templates/character/sheet.html` (initiative display).

**Unit tests:** None specific to Hiruma 4th Dan action dice.
**Clicktests:**
- `test_school_abilities.py::test_hiruma_initiative_action_dice_info`

**Missing:**
- [ ] Behavioral clicktest: roll initiative, verify action dice display shows the -2 adjustment note

---

## 5th Dan

> After making a successful or unsuccessful parry roll, the attacker deals 10 fewer light wounds on their next 2 damage rolls.

**Status:** Fully implemented (display note).
- Server: `app/routes/pages.py` passes `hiruma_parry_reduce_lw: true` in school_abilities.
- Client: shows informational note after parry rolls: "the attacker deals 10 fewer light wounds on their next 2 damage rolls."

**Clicktests:**
- `test_school_abilities.py::test_hiruma_5th_dan_parry_note`

