# Kakita Duelist

**School ID:** `kakita_duelist`
**Category:** Duelist
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Your 10s on initiative rolls are considered to be in a special Phase 0. You may use interrupt actions to attack using iaijutsu, and any Phase 0 attacks use iaijutsu.

**Status:** Fully implemented.
- `dice.py:497` sets `kakita_phase_zero = school_id == "kakita_duelist"`.
- The flag is passed through the initiative formula and used on the sheet to display Phase 0 behavior.
- `sheet.html` renders the Phase 0 information for Kakita initiative rolls.

**Implementation:** `app/services/dice.py:497` (`kakita_phase_zero`), `app/templates/character/sheet.html` (initiative display).

**Unit tests:** None specific to Phase 0 mechanic.
**Clicktests:** `test_sheet_js_errors.py` includes `kakita_duelist` in the school list. `test_school_selection.py` references `kakita_duelist` for selection testing.

**Missing:**
- [ ] Unit test: initiative formula for Kakita includes `kakita_phase_zero: True`
- [ ] Clicktest: initiative display shows Phase 0 information

---

## 1st Dan

> Roll one extra die on double attack, iaijutsu, and initiative rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "iaijutsu", "initiative"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_initiative_formula()`.

**Unit tests:** None specific to Kakita 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for double_attack/iaijutsu/initiative

---

## 2nd Dan

> You get a free raise on all iaijutsu rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "iaijutsu"`
- Applied as +5 flat bonus on iaijutsu rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Kakita at 2nd Dan gets +5 flat on iaijutsu formula
- [ ] Clicktest: iaijutsu roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Your attacks get a bonus of X for each phase before the defender's next action they occur, where X is equal to your attack skill. If a defender does not have an action remaining in this round, they are considered to act in phase 11. This applies to all types of attacks, and you know the next action of everyone within striking range.

**Status:** Out of scope - requires knowing opponent's initiative phase, which requires combat-phase tracking.

**Questions (ANSWERED):**
- The bonus is X per phase before the defender's next action, where X is the attack skill rank.
- Phase tracking is needed: if defender's next action is phase 7 and you attack in phase 4, bonus = 3X.
- "Defender is considered to act in phase 11" if they have no remaining actions.
- "You know the next action of everyone within striking range" is an information display mechanic.

---

## 4th Dan

> Raise your current and maximum Fire by 1. Raising your Fire now costs 5 fewer XP. You get a free raise to all damage rolls from attacks using iaijutsu.

**Status:** Fully implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Free raise on iaijutsu DAMAGE rolls" is fully implemented via `app/services/dice.py:build_all_roll_formulas()` (iaijutsu damage metadata with +5 flat bonus when school_id == "kakita_duelist" and dan >= 4).

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_kakita_duelist_4th_dan_iaijutsu_damage_bonus` - verifies +5 flat on iaijutsu damage at 4th Dan
- `test_dice.py::TestSchoolAbilities::test_kakita_duelist_below_4th_dan_no_damage_bonus` - verifies no bonus below 4th Dan
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying damage modal shows the +5 bonus for iaijutsu attacks

---

## 5th Dan

> At the beginning of phase 0 in each combat round, make a contested iaijutsu roll against an opponent. If the opponent doesn't have iaijutsu, they may roll attack instead, and you get an extra free raise. Make a damage roll against this opponent; if you won the contested roll then roll 1 extra damage die for every 5 by which your roll exceeded your opponent's, and if you lost then roll 1 fewer damage die for every 5 by which their roll exceeded yours.

**Status:** Out of scope - requires Phase 0 combat-start mechanics and contested roll with automatic damage scaling.
