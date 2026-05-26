# Suzume Overseer

**School ID:** `suzume_overseer`
**Category:** Court
**School Ring:** Water (fixed; no dropdown).
**School Knacks:** oppose_social, pontificate, worldliness.

The Suzume family of the Sparrow clan is drawn from Crane Doji Artisans and merchants. Their school techniques are literally those other schools' techniques applied without claim. Code reuse here mirrors fiction reuse: the Special Ability is wired to Merchant's `merchant_post_roll_vp` flag, the 5th Dan to Doji Artisan's `doji_5th_dan_*` flags. Search `dice.py` and `routes/pages.py` for "Shared with Suzume Overseer" comments at the relevant call sites.

---

## Special Ability

> You may spend void points after you see the results of your initial roll.

**Status:** Fully implemented (shares Merchant's wiring).

- Server: `app/routes/pages.py` sets `merchant_post_roll_vp: True` when `character.school in ("merchant", "suzume_overseer")`.
- Client: post-roll VP spending UI in `app/templates/character/sheet.html`. The pre-roll VP menu is suppressed by the same flag.
- Read-only Roll Mode: `deductVoidPoints()` in `sheet.html` already early-returns for non-editors.

**Implementation:** `app/game_data.py` (school definition), `app/routes/pages.py` (`merchant_post_roll_vp`), `app/templates/character/sheet.html` (post-roll VP buttons).

---

## 1st Dan

> Roll one extra die on precepts, commerce, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.

- `first_dan_extra_die: ["precepts", "commerce", "wound_check"]`
- Applied generically in `app/services/dice.py::_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 2nd Dan

> You get a free raise on a type of roll of your choice.

**Status:** Fully implemented as a flexible-2nd-Dan picker shared with Ide Diplomat, Isawa Ishi, and Shugenja.

- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES` triggers the flexible branch in `_apply_school_technique_bonus()` (skills/knacks/combat/athletics) plus parallel branches in `build_wound_check_formula()` and the damage block of `build_all_roll_formulas()`.
- The choice persists in `Character.technique_choices.second_dan_choice` (TEXT JSON column already on the model; no migration needed).
- Editor UI: a new generic picker in `app/templates/character/edit.html` (data-testid `flex-2nd-dan-picker`) appears when `school in {ide_diplomat, isawa_ishi, shugenja, suzume_overseer}` and `currentDan() >= 2`. Eligible roll types: skills, school knacks (rollable), and the four combat rolls (attack/parry/wound_check/damage). Initiative is excluded.
- Constant `FLEXIBLE_2ND_DAN_SCHOOLS` in `edit.html` lists the four schools that share this picker.

**Implementation:** `app/templates/character/edit.html` (picker), `app/services/dice.py` (server-side bonus), `app/game_data.py` (table entry).

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your precepts skill, which may be applied to the following rolls: commerce, heraldry, sincerity, tact, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

- `source_skill: "precepts"`
- `applicable_to: ["commerce", "heraldry", "sincerity", "tact", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`
- Reuses the existing `adventure_raises` per-adventure counter (already used by Courtier / Merchant / Doji / Brotherhood / Kitsuki / Kuni / Shugenja / Shosuro / Ikoma / Ide). Counter state lives in `Character.adventure_state["adventure_raises_used"]`; no migration needed.
- Read-only Roll Mode: per-roll spends go through `t.setCount('adventure_raises', ...)` on the bridge, which is already gated on `t.canEdit`.

**Implementation:** `app/game_data.py` (table entry), `app/routes/pages.py` (per_adventure counter wiring), `app/services/dice.py::_annotate_third_dan()` (max_per_roll stamping), `app/templates/character/sheet.html` (spend UI).

---

## 4th Dan

> Raise the current and maximum rank of any Ring by 1. Raising that Ring now costs 5 fewer XP. Your skill is considered 2 higher for the purpose of computing free raises for any contested roll you did not initiate.

**Status:** OUT OF SCOPE - intentionally not implemented.

The first half (raise any one ring by 1, with discount) is the same kind of mechanic as Merchant's 4th Dan ring raise, but the second half ("skill considered 2 higher for free raises on contested rolls you didn't initiate") depends on contested-roll-mechanics that aren't modeled in our system. To avoid implementing only one of the two halves and leaving Suzume mid-power, the entire 4th Dan is omitted.

The school's `techniques` dict in `app/game_data.py` deliberately has no key 4. The structural test `tests/test_game_data.py::TestSchools::test_all_schools_have_five_techniques` whitelists Suzume Overseer as the documented exception.

---

## 5th Dan

> When making any TN or contested roll, you receive a bonus equal to (X-10) / 5 where X is the TN or result of your opponent's contested roll.

**Status:** Fully implemented (shares Doji Artisan's wiring).

- Server: in `app/services/dice.py`, every `school_id == "doji_artisan" and dan >= 5` check at the 5th-Dan level was widened to `school_id in ("doji_artisan", "suzume_overseer")`. The `doji_5th_dan_always`, `doji_5th_dan_optional`, and `doji_5th_dan_wc` flags retain their names.
- Client: the existing `doji-5th-always` / `doji-5th-optional` UI in `sheet.html` renders for Suzume too without any template changes (the templates branch on the formula flags, not the school id).
- Read-only Roll Mode: 5th-Dan bonus is a pure roll-total visualization (no bridge mutation), so non-editors see it correctly without any state mutation.

**Implementation:** `app/services/dice.py` lines 354, 577, 656, 775, 875 (membership-test refactors).

---

## Importer Aliases

Source documents may refer to the school as "Sparrow", "Sparrow Overseer", or "Suzume". All three map to `suzume_overseer` via `_SCHOOL_ALIASES` in `app/services/import_match.py`.
