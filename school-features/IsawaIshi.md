# Isawa Ishi

**School ID:** `isawa_ishi`
**Category:** Spellcaster
**School Ring:** Void - Confirmed correct.
**School Knacks:** absorb_void, kharmic_spin, otherworldliness - Absorb_void is rollable (Void). Kharmic_spin is rollable (Void). Otherworldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Maximum void points equals highest ring plus school rank. Regain lowest Ring per night, one per 2 hours partial. May not spend more than lowest Ring minus 1 per roll.

**Status:** Partially implemented.
- VP spend cap (lowest ring - 1) is implemented in `pages.py:211`: `void_spend_cap = void_max - (1 if character.school in ("shugenja", "isawa_ishi") else 0)`.
- VP max (highest ring + school rank) is implemented in `game_data.py:872-873` via `void_points_max_shugenja()`.
- VP regen (lowest ring per night) is implemented in `game_data.py:882-884` via `void_regen_per_night_shugenja()`.
- Note: The spend cap in `pages.py:211` uses `void_max - 1` which is `min(rings) - 1` since `void_max = min(ring_vals)`. However, the actual VP max for Isawa Ishi should be `max(rings) + school_rank`, not `min(rings)`. The spend cap formula appears to correctly compute `min(rings) - 1` despite the max being different.

**Implementation:**
- `app/routes/pages.py:211` (spend cap -1 for shugenja/isawa_ishi)
- `app/game_data.py:872-873` (`void_points_max_shugenja`)
- `app/game_data.py:882-884` (`void_regen_per_night_shugenja`)
- `app/game_data.py:887-889` (`void_spend_cap_shugenja`)

**Unit tests:**
- `test_game_data_helpers.py:58` - `test_shugenja_max` verifies VP max = highest ring + school rank
- `test_game_data_helpers.py:66` - `test_shugenja_regen` verifies VP regen = lowest ring
- `test_game_data_helpers.py:70` - `test_shugenja_spend_cap` verifies spend cap = min(rings) - 1

**Clicktests:** `test_sheet_js_errors.py:19` includes `isawa_ishi` in the sheet JS error check list.

**Questions:**
- Is the VP max (highest ring + school rank) being used in the sheet display? The `pages.py:210` line uses `min(ring_vals)` as `void_max` for all schools, then subtracts 1 for the spend cap. The actual max VP for Isawa Ishi should use the shugenja-specific max function.

**Missing:**
- [ ] Verify VP max display on sheet uses `void_points_max_shugenja` not `void_points_max`
- [ ] Verify VP regen display on sheet uses `void_regen_per_night_shugenja`
- [ ] Clicktest: VP max display shows highest ring + school rank
- [ ] Clicktest: VP spend cap shows min(rings) - 1

---

## 1st Dan

> Roll an extra die on precepts and two chosen skill rolls.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the two skill rolls are player-chosen.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- The "chosen skill rolls" would need to be stored on the character and applied dynamically.

**Implementation:** `app/game_data.py:2162` (`first_dan_extra_die: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement UI for selecting two skill rolls for 1st Dan extra die
- [ ] Store chosen skill rolls on the character model
- [ ] Apply chosen extra die in roll formula computation
- [ ] Unit test for flexible 1st Dan with chosen skills
- [ ] Clicktest for 1st Dan skill selection

---

## 2nd Dan

> Free raise on all rolls for a chosen skill.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the skill is player-chosen.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.

**Implementation:** `app/game_data.py:2163` (`second_dan_free_raise: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement UI for selecting skill for 2nd Dan free raise
- [ ] Store chosen skill on the character model
- [ ] Apply chosen free raise in roll formula computation
- [ ] Unit test for flexible 2nd Dan with chosen skill
- [ ] Clicktest for 2nd Dan skill selection

---

## 3rd Dan

> After an ally's roll, spend a void point to roll Xk1 and add the result (X = precepts skill); once per roll.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`. It is a support ability that affects allies' rolls.

**Questions:**
- Is this triggered via the Isawa's UI or the ally's UI?
- Does the Xk1 roll use the Isawa's precepts rank or the ally's?
- "Once per roll" means each of the Isawa's allies can only receive this once per roll they make?

**Missing:**
- [ ] Implement ally-support roll mechanic
- [ ] UI for triggering the Xk1 roll on behalf of an ally
- [ ] VP cost tracking

---

## 4th Dan

> +1 Void; Void ring costs 5 fewer XP to raise; contested opponents can't spend void points.

**Status:** Partially implemented.
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Contested opponents can't spend void points" is NOT implemented. This is a debuff on opponents during contested rolls.

**Unit tests:** None specific to Isawa Ishi 4th Dan.
**Clicktests:** None.

**Missing:**
- [ ] Implement opponent VP spending restriction during contested rolls
- [ ] UI indicator for the VP restriction effect

---

## 5th Dan

> Negate another character's school for a conversation or fight; costs 2X void for school rank X, or experience/50 for non-school.

**Status:** NOT implemented. This is a powerful debuff ability.

**Questions:**
- Does "negate" mean all school techniques, special ability, and knack bonuses are suppressed?
- Does "experience/50 for non-school" mean it can affect non-school abilities too?
- What is the UI for targeting another character?

**Missing:**
- [ ] Implement school negation mechanic
- [ ] VP cost calculation based on target's school rank
- [ ] UI for targeting characters and activating negation
- [ ] Duration tracking (conversation or fight)
