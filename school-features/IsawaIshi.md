# Isawa Ishi

**School ID:** `isawa_ishi`
**Category:** Spellcaster
**School Ring:** Void - Confirmed correct.
**School Knacks:** absorb_void, kharmic_spin, otherworldliness - Absorb_void is non-rollable; per-adventure counter where each use regains 1 spent VP. Kharmic_spin is rollable (Void). Otherworldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Your maximum number of void points is equal to your highest ring plus your school rank. After a full night's rest, your Absorb Void school knack resets to full usage and you regain spent void points equal to your lowest Ring. A partial night's rest restores 1 spent void point and 1 use of Absorb Void per 90 minutes of sleep, up to the per-night total you can regain. However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Fully implemented.
- VP max (highest ring + school rank) is implemented in `game_data.py` via `void_points_max_shugenja()`. `app/routes/pages.py` uses `void_points_max_shugenja()` for Isawa Ishi VP max display.
- VP spend cap (`min(rings) - 1`) is computed in `app/routes/pages.py` for shugenja/isawa_ishi schools.
- VP regen (lowest ring per night) is implemented in `game_data.py` via `void_regen_per_night_shugenja()`.
- Absorb Void is per-day for Isawa Ishi (override in `app/routes/pages.py` adds `per_day=True` only when `character.school == "isawa_ishi"`), so the tracker renders the "Reset" button alongside the +/- buttons. Kitsune Warden's Absorb Void stays per-adventure (the default).

**Implementation:**
- `app/routes/pages.py` (VP max via `void_points_max_shugenja()`, spend cap via `min(rings) - 1`)
- `app/game_data.py` (`void_points_max_shugenja`)
- `app/game_data.py` (`void_regen_per_night_shugenja`)
- `app/game_data.py` (`void_spend_cap_shugenja`)

---

## 1st Dan

> Roll one extra die on precepts and any two types of rolls of your choice.

**Status:** Fully implemented.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`. The two player-chosen rolls are stored in `technique_choices.first_dan_choices` (List[str], length up to 2). Eligible roll types match the Kitsune Warden 1st Dan picker: every skill (except precepts, which is auto-applied), every rollable school/foreign knack, plus attack/damage/initiative/parry/wound_check.
- Precepts is auto-applied server-side: `app/services/dice.py:_apply_school_technique_bonus()` adds +1 rolled die to precepts for `school == "isawa_ishi"` regardless of the player's picks (with dedup so a redundant explicit pick never doubles the bonus).
- Editor UI: `app/templates/character/edit.html` renders the `ishi-1st-dan-picker` block with two `<select>` slots when `school === 'isawa_ishi' && currentDan() >= 1`. Persistence and slot-uniqueness mirror the Kitsune Warden 1st Dan helpers.

**Implementation:** `app/game_data.py` (`first_dan_extra_die: None`), `app/services/dice.py:_apply_school_technique_bonus()` (auto-precepts + flexible picks), `app/templates/character/edit.html` (`ishi-1st-dan-picker` block + `setIshi1stDanChoice` Alpine helpers).

---

## 2nd Dan

> You get a free raise on all rolls for any skill of your choice.

**Status:** Fully implemented via technique_choices.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (choice is player-selected, not hardcoded).
- Server: `app/models.py` stores player choice in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +5 flat bonus for the chosen skill.
- Editor UI allows selecting skill.

**Implementation:** `app/game_data.py` (`second_dan_free_raise: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

---

## 3rd Dan

> After another character makes a roll for which void points may be spent, you may spend one void point to roll Xk1 and add the result to their total, where X is your precepts skill. You may only do this once per roll.

**Status:** Implemented on the Isawa's side; the cross-sheet auto-add stays manual.
- `school_abilities` exposes `ishi_add_roll` (true when `school == "isawa_ishi"` and Dan >= 3) and `ishi_add_x` (= precepts skill rank) in `app/routes/pages.py`.
- The Isawa's sheet shows a "Isawa Ishi 3rd Dan - Add to Roll" button ("Spend 1 VP to add Xk1"); clicking it calls `rollSpendVPForXk1({ x, title })` in `app/templates/character/sheet.html`, which deducts 1 VP (temp > regular > worldliness) and rolls Xk1 (10s reroll on).
- The roll **is recorded to Roll History** with `roll_key = "spend_vp_xk1:isawa_ishi"` and label "Isawa Ishi 3rd Dan". The history tooltip resolves that key to this school's actual 3rd Dan technique rules text via the `spend_vp_xk1:<school_id>` branch in `app/services/roll_descriptions.py` (which reads `school.techniques[3]`); a bare `spend_vp_xk1` key falls back to a generic blurb. (Before the fix, `rollSpendVPForXk1` filled the modal but never called `_saveRollHistoryCreate()`, so these rolls never appeared in the history at all.)
- Still manual / out of scope: actually adding the rolled result to the *other* character's total is a cross-sheet interaction; the Isawa player relays the result verbally. Same shape as the Ide Diplomat 3rd Dan subtract-from-roll (which shares `rollSpendVPForXk1`).

**Questions (ANSWERED):**
- Triggered from the Isawa's side (the Isawa decides to spend their VP to help another character).
- Uses the Isawa's precepts skill rank for X.
- "Once per roll" means each roll can only receive this bonus once.

---

## 4th Dan

> Raise your current and maximum Void by 1. Raising your Void now costs 5 fewer XP. Characters opposing you in contested rolls may not spend void points. If someone is opposing both you and someone else, they may spend void points, but the bonus will only count against whoever else they're opposing.

**Status:** Partially implemented. Ring raise is fully implemented; "opponents can't spend VP in contested rolls" is out of scope (requires tracking opponent VP spending).
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.

---

## 5th Dan

> You may completely negate another character's school or profession for the remainder of one conversation or fight. Against characters with a school, you must spend void points equal to twice their school rank. Against characters with no school, you must spend void points equal to their experience divided by 50, rounded down. This is instantaneous and does not require spending an action.

**Status:** Out of scope - requires targeting another character to negate their school (cross-character debuff mechanic).
