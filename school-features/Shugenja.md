# Shugenja

**School ID:** `shugenja`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** commune, pontificate, spellcasting - Commune is rollable (varies by element). Pontificate is rollable (Water). Spellcasting is rollable (varies by element).

**DISABLED IN UI:** The Shugenja school is currently disabled in the school selection dropdown with "(coming soon)" label. See `app/templates/character/edit.html:117`.

---

## Special Ability

> Your maximum number of void points is equal to your highest ring plus your school rank. You regain a number of void points equal to your lowest Ring after a full night's rest, and one void point per 2 hours for a partial night. However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Partially implemented (same as Isawa Ishi).
- VP spend cap (lowest ring - 1) is implemented in `pages.py:211`: `void_spend_cap = void_max - (1 if character.school in ("shugenja", "isawa_ishi") else 0)`.
- VP max (highest ring + school rank) is implemented in `game_data.py:872-873` via `void_points_max_shugenja()`.
- VP regen (lowest ring per night) is implemented in `game_data.py:882-884` via `void_regen_per_night_shugenja()`.
- Note: same implementation concerns as Isawa Ishi regarding VP max display.

**Implementation:**
- `app/routes/pages.py:211` (spend cap -1 for shugenja/isawa_ishi)
- `app/game_data.py:872-873` (`void_points_max_shugenja`)
- `app/game_data.py:882-884` (`void_regen_per_night_shugenja`)
- `app/game_data.py:887-889` (`void_spend_cap_shugenja`)

**Unit tests:**
- `test_game_data_helpers.py:58` - `test_shugenja_max` verifies VP max = highest ring + school rank
- `test_game_data_helpers.py:66` - `test_shugenja_regen` verifies VP regen = lowest ring
- `test_game_data_helpers.py:70` - `test_shugenja_spend_cap` verifies spend cap = min(rings) - 1

**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] **POTENTIAL BUG:** Same as Isawa Ishi - verify VP max display on sheet uses `void_points_max_shugenja` not the default.
- [ ] Enable Shugenja in the school selection dropdown (remove "coming soon" disable)
- [ ] Verify VP max display on sheet uses `void_points_max_shugenja`
- [ ] Implement spellcasting UI (commune/spellcasting knacks require element selection)

---

## 1st Dan

> Roll one extra die when rolling precepts or with commune and spellcasting for your chosen element.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the element/skill is player-chosen.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- The chosen element would need to be stored on the character and applied dynamically to commune/spellcasting rolls of that element.

**Implementation:** `app/game_data.py:2172` (`first_dan_extra_die: None`).

**Unit tests:** None.
**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Implement UI for selecting element for 1st Dan extra die
- [ ] Store chosen element on the character model
- [ ] Apply extra die to precepts or commune/spellcasting for chosen element
- [ ] Unit test for flexible 1st Dan with chosen element
- [ ] Clicktest for 1st Dan element selection

---

## 2nd Dan

> You get a free raise when rolling precepts or with commune and spellcasting for your chosen element.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the element/skill is player-chosen.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.

**Implementation:** `app/game_data.py:2173` (`second_dan_free_raise: None`).

**Unit tests:** None.
**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Implement UI for selecting element for 2nd Dan free raise
- [ ] Store chosen element on the character model
- [ ] Apply free raise to precepts or commune/spellcasting for chosen element
- [ ] Unit test for flexible 2nd Dan with chosen element
- [ ] Clicktest for 2nd Dan element selection

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your precepts skill, which may be applied to the following rolls: bragging, intimidation, precepts, tact, wound checks, and spellcasting for your chosen element. You may not spend more than X of these free raises on any single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "precepts"`
- `applicable_to: ["bragging", "intimidation", "precepts", "tact", "wound_check", "spellcasting"]`
- `formula: "2X"`, `max_per_roll: "X"`
- Note: The "for element" restriction on spellcasting is not encoded; spellcasting is listed unconditionally.

**Implementation:** `app/game_data.py:2174-2183` (third_dan dict).

**Unit tests:** None specific to Shugenja 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Implement element restriction on spellcasting free raises
- [ ] Clicktest for Shugenja-specific 3rd Dan applicable skills (after enabling school)

---

## 4th Dan

> Raise your current and maximum Ring of your chosen element by 1. Raising that Ring now costs 5 fewer XP. You may cast one spell per round as an interrupt action.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring (which represents the chosen element).
- "Cast one spell per round as an interrupt action" is NOT implemented. This is a combat-phase mechanic requiring spellcasting support.

**Unit tests:** None.
**Clicktests:** None (school is disabled in UI).

**Missing:**
- [ ] Implement interrupt spellcasting (once per round)
- [ ] UI for interrupt spell casting during combat

---

## 5th Dan

> Your non-Void rings are all considered 1 higher when rolling commune and spellcasting.

**Status:** NOT implemented. This would add +1 to Air, Fire, Earth, and Water when computing commune and spellcasting roll formulas.

**Missing:**
- [ ] Implement +1 to non-Void rings for commune/spellcasting rolls
- [ ] Unit test: commune/spellcasting formulas show ring+1 for non-Void rings at 5th Dan
- [ ] Clicktest for ring bonus display (after enabling school)
