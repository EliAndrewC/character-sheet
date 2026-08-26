# Shugenja

**School ID:** `shugenja`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** commune, pontificate, spellcasting - Commune is rolled with the character's School Ring (see "Commune rolls the School Ring" below). Pontificate is rollable with whichever of Water or Air is higher at roll time. Spellcasting is rollable (varies by element).

Commune costs a void point to activate (see "Commune activation cost" below) and is rolled with the character's School Ring (see "Commune rolls the School Ring" below).

**DISABLED IN UI:** The Shugenja school is currently disabled in the school selection dropdown with "(not yet implemented)" label. See `app/templates/character/edit.html`.

---

## Special Ability

> Your maximum number of void points is equal to your highest Ring plus your school rank.  You regain a number of void points equal to your lowest Ring after a full night's rest, and one void point per 2 hours for a partial night.  However, you may not spend more void points on any one roll than your lowest Ring minus 1.

**Status:** Fully implemented (same as Isawa Ishi). Spellcasting UI and enabling the school in the dropdown are deferred until the school is enabled.
- VP max (highest ring + school rank) is implemented in `game_data.py` via `void_points_max_shugenja()`. `app/routes/pages.py` uses `void_points_max_shugenja()` for Shugenja VP max display.
- VP spend cap (`min(rings) - 1`) is computed in `app/routes/pages.py` for shugenja/isawa_ishi schools.
- VP regen (lowest ring per night) is implemented in `game_data.py` via `void_regen_per_night_shugenja()`.

**Implementation:**
- `app/routes/pages.py` (VP max via `void_points_max_shugenja()`, spend cap via `min(rings) - 1`)
- `app/game_data.py` (`void_points_max_shugenja`)
- `app/game_data.py` (`void_regen_per_night_shugenja`)
- `app/game_data.py` (`void_spend_cap_shugenja`)

---

## 1st Dan

> Roll one extra die on precepts and when rolling commune or spellcasting with your School Ring.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Missing:**

---

## 2nd Dan

> You get a free raise on precepts and when rolling commune or spellcasting with your School Ring.

**Status:** Fully implemented via technique_choices.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` (choice is player-selected, not hardcoded).
- Server: `app/models.py` stores player choice in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +5 flat bonus for the chosen skill.
- Editor UI allows selecting skill.

**Implementation:** `app/game_data.py` (`second_dan_free_raise: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Missing:**

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is your precepts skill, which may be spent on bragging, intimidation, precepts, tact, wound checks, and when rolling commune or spellcasting with your School Ring after seeing your roll.  You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`. Element restriction on spellcasting free raises is deferred until the school is enabled.
- `source_skill: "precepts"`
- `applicable_to: ["bragging", "intimidation", "precepts", "tact", "wound_check", "spellcasting"]`
- `formula: "2X"`, `max_per_roll: "X"`
- Note: The "for element" restriction on spellcasting is not encoded; spellcasting is listed unconditionally.

**Implementation:** `app/game_data.py` (third_dan dict).

**Missing:**

---

## 4th Dan

> Raise your current and maximum School Ring by 1.  Raising your School Ring now costs 5 fewer XP.  You may cast one spell per round as an interrupt action.

**Status:** Partially implemented. Ring raise is fully implemented; "cast one spell per round as an interrupt action" is out of scope (combat-phase tracking).
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring (which represents the chosen element).

---

## 5th Dan

> Your non-Void Rings are considered 1 higher when rolling commune and spellcasting.

**Status:** Fully implemented.
- Server: `app/services/dice.py:build_knack_formula()` adds +1 to non-Void ring values when computing commune and spellcasting formulas for shugenja at 5th Dan.

**Missing:**

---

## Commune rolls the School Ring

> Commune (rules 05-school_knacks): "Spend a void point and roll this knack with the Ring of the element of the spirits you are questioning."

**Status:** Fully implemented.

**GM ruling (2026-08-08):** the knack's ring "varies" in the abstract, but a character who has commune as a school knack is trained to commune with the kami of their own school element, so their commune rolls always use their School Ring. A Shugenja with School Ring Air shows Commune badged "Air" and always rolls Air.

- **Server:** `app/game_data.py::effective_knack_ring` resolves the pinned ring from `SCHOOL_RING_KNACK_IDS` (currently just commune) plus `Character.school_ring_choice`. `build_knack_formula` uses it for the dice and the "Commune (Air)" label; the sheet and Google Sheets export routes stamp it as `info["ring"]` on each knack entry.
- **Catalog unchanged:** `SCHOOL_KNACKS["commune"].ring` is still `"varies"` - only a character's copy is pinned. Spellcasting deliberately stays "varies" (its ring is per-spell, not per-character).
- **UI:** the sheet's knack row badges `info.ring`; the expanded rules text appends "Your School Ring is X, so your commune rolls always use X." The editor's school-reference panel has no character, so it badges commune with the words "School Ring".
- **Fallback:** a draft with no School Ring recorded keeps the old Earth placeholder rather than guessing.
- **Interaction with Shugenja 5th Dan:** the +1-to-non-Void-rings boost now lands on the School Ring, since that is the ring commune rolls with.
- **Tests:** `tests/test_game_data.py::TestEffectiveKnackRing`, `tests/test_dice.py` (commune School Ring group), `tests/test_routes.py::TestCommuneSchoolRing`, `tests/test_sheets.py::TestCommuneRingColumn`, `tests/e2e/test_rolls.py::test_commune_badge_*` / `test_commune_roll_menu_and_result_use_the_school_ring` / `test_commune_rules_text_names_the_school_ring`.

---

## Commune activation cost

> Commune (rules 05-school_knacks): "Spend a void point and roll this knack with the Ring of the element of the spirits you are questioning."

**Status:** Fully implemented.

- The void point is an **activation cost**, not a dice bonus: it buys the roll and adds nothing to it. With an empty void pool the roll is unavailable.
- The per-roll void-spend cap is **unchanged** - the activation point simply comes out of the pool first. A character whose cap is 2 but who has only 2 points left may put 1 into the roll (1 pays for the roll itself).
- Points are drawn in the sheet's standing order: temporary, then regular, then the Worldliness allowance.
- **Server:** `RollFormula.requires_void_point`, set for commune in `app/services/dice.py::build_knack_formula`.
- **Client:** `voidActivationCost()` / `voidPools()` in `_dice_js.html`; `computeVoidOptions(reserve)` withholds the reserved point from the extra-spend options; `executeRoll` folds the activation into a single `deductVoidPoints` call and refuses to roll with an empty pool. The menu (`roll_trigger.html`) states the cost, labels the roll row "(1 VP)", and replaces the roll rows with an explanation when the pool is empty; `modal_result.html` reports the activation in the result breakdown.
- **Read-only mode:** the cost is never deducted for a non-editor (`deductVoidPoints` early-returns), but the empty-pool gate still applies - it is a rules gate, not an edit gate.
- **Discordant:** unaffected. Per the GM ruling, Discordant blocks the generic "+1k1 per void point" menu on knacks, not school-ability void costs; a Discordant character still pays commune's activation point and still gets no extra-dice options.
- **Tests:** `tests/test_dice.py::TestCommuneVoidCost`, `tests/js/roll_math.test.js` (allocateVoidSpend), `tests/e2e/test_rolls.py` (commune group), `tests/e2e/test_readonly_rolls.py::test_non_editor_commune_*`.
