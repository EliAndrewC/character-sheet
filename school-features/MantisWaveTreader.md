# Mantis Wave-Treader

**School ID:** `mantis_wave_treader`
**Category:** Bushi
**School Ring:** "Any" - Player chooses from Air, Fire, Earth, Water, or Void. Requires a new value in the `school_ring` → `SCHOOL_RING_OPTIONS` mapping ("Any" expands to all five rings, unlike "any non-Void" which excludes Void). Default ring is Void - Mantis Wave-Treader is the only school with a Void default; every other variable-ring school continues to default to Water.
**School Knacks:** athletics, iaijutsu, worldliness - Athletics is rollable (varies by ring used; opens the four-ring picker with void submenus - same as Togashi). Iaijutsu is rollable (Air during stance phase; see `dice.py`). Worldliness is the existing non-rollable knack (passive, `ring=None`) already used by Priest.

---

## Special Ability

> Each phase you select an "offensive" or "defensive" posture. While fighting with an offensive posture, you get a free raise to all attack and damage rolls, and while fighting in a defensive posture you get a free raise to wound checks and your TN to be hit is increased by 5.

**Status:** Not yet implemented. Requires a new per-phase posture tracker in the Tracking section (where discretionary bonuses currently live) with two buttons - "Offensive Posture for Phase X" and "Defensive Posture for Phase X" - that increment X from 1 through 10 and then disable. Making an initiative roll resets X back to 1 and clears the phase/posture history. The current phase's posture drives:
- Offensive: +5 free raise on attack rolls and damage rolls.
- Defensive: +5 free raise on wound checks, +5 to TN to be hit.

The "Clear bonuses" button clears all posture-accumulated bonuses AND clears the action dice (equivalent to clicking the action-dice "Clear" button). The action-dice "Clear" button is wired to also clear posture bonuses.

**Implementation:** TBD - see MantisWaveTreaderImplementationPlan.md.

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 1st Dan

> Roll one extra die on initiative, athletics, and wound checks.

**Status:** Will be implemented via the existing `SCHOOL_TECHNIQUE_BONUSES` mechanism.
- `first_dan_extra_die: ["initiative", "athletics", "wound_check"]`
- Applied by `app/services/dice.py:_apply_school_technique_bonus()` for athletics, `build_wound_check_formula()` for wound checks, and `build_initiative_formula()` for initiative. No new code required beyond the `game_data.py` entry.

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 2nd Dan

> You get a free raise on a type of roll of your choice.

**Status:** Not yet implemented. Needs the same player-chosen-skill pattern used by Priest's 1st Dan:
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (flexible - player picks at Dan 2 advancement).
- The chosen roll is stored in the existing `technique_choices` JSON column and applied as a +5 flat bonus in `_apply_school_technique_bonus()` / `build_*_formula()`.
- Editor UI adds a picker under the 2nd Dan technique when the character is Mantis Wave-Treader.
- **Choice set:** any roll type for which a free raise is mechanically meaningful. This means:
  - All rollable skills.
  - Rollable school knacks (for Mantis Wave-Treader: `athletics` and `iaijutsu` are eligible; `worldliness` is NOT, since it's passive and never rolled).
  - Combat rolls: attack, damage, parry, wound check.
  - Excluded: `initiative` (a free raise has no meaning on an initiative roll) and any other non-rollable knack.

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 3rd Dan

> After making an attack roll during a phase in which you have chosen an offensive posture, you may spend one action die from any phase to give yourself +X to all attack and damage rolls for the rest of the round, where X is your attack skill.
>
> After seeing the result of an attack roll made against you while fighting with a defensive posture, you may spend one action die from any phase to increase your wound checks and TN to be hit by X for the remainder of the round, where X is your attack skill.

**Status:** Not yet implemented. Non-standard 3rd Dan (no `third_dan` config block - too bespoke). Requires:
- **Offensive branch** - The attack-roll result modal shows a button "Spend another action to increase attack and damage by X for the round" (X = attack skill) when the character is Mantis Wave-Treader at Dan >= 3, the current phase's posture is offensive, and at least one action die is still unspent. Tooltip carries the rules text verbatim. Clicking marks the lowest unspent action die spent and adds X to an `offensive3rdDan` accumulator that applies to all subsequent attack rolls and damage rolls until the next initiative roll.
- **Defensive branch** - A button "Spend action to increase TN and wound checks by X" (X = attack skill) shown in the Tracking section below the posture-bonus list while in a defensive posture, with rules-text tooltip. Clicking spends one action die and adds X to a `defensive3rdDan` accumulator that applies to all wound checks and to the displayed TN until the next initiative roll.
- Both accumulators reset on initiative roll, and both are zeroed by the "Clear bonuses" button and by the action-dice "Clear" button.
- The wound check modal's probability table displays these accumulators as additive bonuses and factors them into the "% chance" and "average serious wounds" computations.

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 4th Dan

> Raise the current and maximum rank of any Ring by 1. Raising that Ring now costs 5 fewer XP. Begin each combat round with an athletics action die set to 1, which may only be spent on movement, athletics actions, or your 3rd Dan technique.

**Status:** Not yet implemented.
- **Ring raise** - Since `school_ring` is "Any" the player's chosen school ring is what the Dan 4 raise applies to. The existing `enforceFourthDanRing()` / `calculate_ring_xp()` pair already supports variable school rings (see Priest's "any non-Void" handling), so it should generalize once "Any" is added to `SCHOOL_RING_OPTIONS`.
- **Bonus athletics action die** - After rolling initiative, render a blue "1" die (always value 1, never rolled) alongside the standard action dice. This is analogous to the Togashi Ise Zumi's "1 athletics action" die, but it is always a literal 1 and is always present regardless of which initiative variant the player picks. The die is restricted in spending to movement, athletics rolls, or the Mantis 3rd Dan technique (offensive or defensive branch). The app tracks the restriction as a label/tooltip; action-die spending enforcement is lightweight (display-only, same approach as Togashi's athletics-only dice today).

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## 5th Dan

> For each phase in which you declare an offensive posture, you gain +1 to all attack and damage rolls for the remainder of the round. For each phase in which you choose a defensive posture, you gain +1 to your wound checks and your TN to be hit for the remainder of the round.

**Status:** Not yet implemented. Built on top of the posture tracker:
- Track two running counters per round: `offensivePhaseCount`, `defensivePhaseCount`. Incremented each time the player clicks the respective posture button.
- Display "Accumulated 5th Dan bonuses" under the posture list:
  - +`offensivePhaseCount` to attack and damage rolls (all subsequent rolls this round).
  - +`defensivePhaseCount` to wound checks and TN to be hit.
- Both counters reset to 0 on initiative roll. They are NOT cleared by the posture "Clear bonuses" button (since those bonuses are already "spent into" the round and the player wouldn't want to retroactively unwind them) - but see implementation plan for the open question.
- Accumulators integrate into the same pathways as the 3rd Dan accumulators (attack/damage bonuses on attack roll modal; wound-check bonuses and TN display on the sheet; wound check probability table).

**Unit tests:** TBD.
**Clicktests:** TBD.

---

## Test References

To be populated as the phases land.
