# Priest

**School ID:** `priest`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, pontificate - Conviction is rollable (Water). Otherworldliness is non-rollable (passive knack, ring=None). Pontificate is rollable (Water).

---

## Special Ability

> You have all 10 rituals listed under the Priest profession.

**Status:** Out of scope - narrative ability (rituals are not encoded in the app).

**Implementation:** `app/game_data.py:1564` (definition only).

---

## 1st Dan

> Roll one extra die on precepts, any one skill, and any one type of combat roll.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py:2167` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`

**Clicktests:** None.

---

## 2nd Dan

> You and your allies get a free raise on all rolls for which you receive an Honor bonus (bragging, precepts, and open sincerity).

**Status:** Partially implemented. The Priest's own free raise on Honor bonus rolls (bragging, precepts, open sincerity) is implemented in `dice.py:build_skill_formula()`. The "allies" part is out of scope (cross-sheet buff).
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- "Honor bonus rolls" are: bragging (gets +2*Honor), precepts (gets +2*Honor), and open sincerity (non-contested sincerity, gets +2*Honor). Contested sincerity (lying, rolled vs interrogation) does NOT qualify.

**Implementation:** `app/game_data.py:2168` (`second_dan_free_raise: None`), `app/services/dice.py:build_skill_formula()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_priest_2nd_dan_bragging_bonus`
- `test_dice.py::TestSchoolAbilities::test_priest_2nd_dan_sincerity_conditional`
- `test_dice.py::TestSchoolAbilities::test_priest_below_2nd_dan_no_bonus`

**Clicktests:** None.

---

## 3rd Dan

> Roll X dice at the beginning of combat, where X is equal to your precepts skill. You may swap any of these dice for any rolled die on any attack, parry, wound check, or damage roll. You may swap any of these dice for any lower die on any of those types of rolls made by any ally.

**Status:** Out of scope - requires cross-sheet interaction (swapping dice into allies' rolls).

---

## 4th Dan

> Raise your current and maximum of your School's chosen Ring by 1. Raising that Ring now costs 5 fewer XP. You and your allies get a free raise on all contested rolls for which your opponent has an equal or higher skill rank.

**Status:** Partially implemented. Ring raise is fully implemented; "free raise for self and allies on contested rolls" is out of scope (cross-sheet ally buff).
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.

**Unit tests:** None.
**Clicktests:** None.

---

## 5th Dan

> You may spend the points from your Conviction knack on your allies' rolls, and your Conviction points refresh after each conversation and combat round. You may also spend these points to lower action dice in order for you or an ally to counterattack or parry.

**Status:** Out of scope - requires cross-sheet resource spending (Conviction points on allies' rolls).
