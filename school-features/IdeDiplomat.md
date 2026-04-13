# Ide Diplomat

**School ID:** `ide_diplomat`
**Category:** Court
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** double_attack, feint, worldliness - Double_attack is rollable (Fire). Feint is rollable (Air). Worldliness is non-rollable (passive knack, ring=None). Feint knack means school is in `SCHOOLS_WITH_TEMP_VOID`.

---

## Special Ability

> After a feint which met its TN, lower the TN of the target by 10 the next time they are attacked, even if the feint was parried.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `ide_feint_tn_reduce: true` in school_abilities.
- Client: shows "Bank -10 TN on target" button after feint rolls. The banked TN reduction is shown in the attack modal and applied when rolling the attack.

**Implementation:** `app/game_data.py:1421-1423` (definition), `app/routes/pages.py` (ide_feint_tn_reduce flag), `app/templates/character/sheet.html` (feint result button, attack modal TN reduction).

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_ide_feint_banks_tn_reduce`

---

## 1st Dan

> Roll one extra die on precepts and any two rolls of your choice.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py:2114` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`

**Clicktests:**
- `test_school_abilities.py::test_ide_1st_dan_skill_selection`

---

## 2nd Dan

> You get a free raise on any type of roll of your choice.

**Status:** Fully implemented via technique_choices.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (choice is player-selected, not hardcoded).
- Server: `app/models.py` stores player choice in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +5 flat bonus for the chosen skill.
- Editor UI allows selecting skill.

**Implementation:** `app/game_data.py:2115` (`second_dan_free_raise: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_second_dan_free_raise`

**Clicktests:**
- `test_school_abilities.py::test_ide_2nd_dan_skill_selection`

---

## 3rd Dan

> After seeing the result of any TN or contested skill roll, you may spend a void point to subtract Xk1 from the roll, where X is equal to your tact skill. You know the result of all TN and contested rolls except sincerity and interrogation.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `ide_subtract_roll: true` and `ide_subtract_x: tact_skill` in school_abilities.
- Client: tracking section shows "Ide 3rd Dan - Subtract from Roll" button. Spending 1 VP rolls Xk1 (X = tact skill) and displays the result to subtract from an opponent's roll.
- "You know the result of all TN and contested rolls except sincerity and interrogation" is an information display mechanic (not encoded).

**Clicktests:**
- `test_school_abilities.py::test_ide_3rd_dan_subtract_button`
- `test_school_abilities.py::test_ide_subtract_button_visible`

**Questions (ANSWERED):**
- X is the tact skill rank (as stated in the rules text).
- "Subtract Xk1 from the roll" means roll Xk1 and subtract that amount from the roll result.
- "You know the result of all TN and contested rolls except sincerity and interrogation" is an information display mechanic.

---

## 4th Dan

> Raise your current and maximum in any non-Void Ring by 1. Raising that Ring now costs 5 fewer XP. You regain an extra void point every night.

**Status:** Fully implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Regain an extra void point nightly" is implemented as a display note.
  - Server: `app/routes/pages.py` passes `ide_extra_vp_regen: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` shows "+1 VP nightly (4th Dan)" text under the VP counter.
  - This is display-only since VP regeneration is tracked manually by players.

**Unit tests:** None.
**Clicktests:**
- `test_school_abilities.py::test_ide_vp_regen_display`

---

## 5th Dan

> Gain a temporary void point whenever you spend a void point that was not gained from this technique.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `ide_temp_vp_on_spend: true` in school_abilities.
- Client: `app/templates/character/sheet.html` hooks into `deductVoidPoints()` to auto-grant temp VP when non-temp VP is spent.

**Clicktests:**
- `test_school_abilities.py::test_ide_5th_dan_temp_vp_on_spend`

**Questions (ANSWERED):**
- "Not gained from this technique" means VP gained from the 5th Dan itself cannot trigger more temp VP. This prevents the infinite loop.
- Normal VP and temp VP from other sources can trigger this.

