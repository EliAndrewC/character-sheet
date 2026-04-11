# Kakita Duelist

**School ID:** `kakita_duelist`
**Category:** Duelist
**School Ring:** Fire - Confirmed correct.
**School Knacks:** double_attack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> Your 10s on initiative rolls are in Phase 0 and can be used for interrupt attacks.

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

> Roll an extra die on double attack, iaijutsu, and initiative rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["double_attack", "iaijutsu", "initiative"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_initiative_formula()`.

**Unit tests:** None specific to Kakita 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for double_attack/iaijutsu/initiative

---

## 2nd Dan

> Free raise on iaijutsu rolls.

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

> Attacks gain a bonus per phase before the defender's next action; know the next action of enemies in range.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is the bonus per phase? Is it +1 per phase, +5 per phase, or some other value?
- How is "the defender's next action" tracked? This requires combat-phase tracking.
- Does "know the next action of enemies in range" have a UI component?

**Missing:**
- [ ] Implement phase-based attack bonus
- [ ] Implement enemy action awareness display
- [ ] Combat phase tracking integration

---

## 4th Dan

> +1 Fire; Fire ring costs 5 fewer XP to raise; free raise on iaijutsu damage rolls.

**Status:** Partially implemented.
- Ring raise (+1 Fire, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Free raise on iaijutsu DAMAGE rolls" is NOT implemented. Note: this is specifically on damage rolls from iaijutsu, not on the iaijutsu attack roll itself (which already gets a free raise from 2nd Dan).

**Unit tests:** None specific to Kakita 4th Dan damage bonus.
**Clicktests:** None.

**Missing:**
- [ ] Implement +5 flat bonus on iaijutsu damage rolls at 4th Dan
- [ ] Unit test for iaijutsu damage formula showing the free raise
- [ ] Clicktest verifying damage modal shows the +5 bonus for iaijutsu attacks

---

## 5th Dan

> At Phase 0, contested iaijutsu with bonus damage dice per 5 excess or penalty per 5 deficit.

**Status:** NOT implemented. This is a Phase 0 combat-start ability.

**Questions:**
- Is this an automatic contested roll at the start of combat (Phase 0)?
- How does the bonus/penalty scale? Is it +1 damage die per 5 excess?
- Does "penalty per 5 deficit" mean fewer damage dice or a flat penalty?

**Missing:**
- [ ] Implement Phase 0 contested iaijutsu mechanic
- [ ] Damage dice scaling based on excess/deficit
- [ ] UI for Phase 0 iaijutsu resolution
