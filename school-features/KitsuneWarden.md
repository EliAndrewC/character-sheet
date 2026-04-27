# Kitsune Warden

**School ID:** `kitsune_warden`
**Category:** Bushi (carries iaijutsu, so bucketed with the Bushi schools).
**School Ring:** Any non-Void (player picks at character creation; persists in `Character.school_ring_choice`).
**School Knacks:** absorb_void, commune, iaijutsu.

---

## Special Ability

> Once per target per combat round or conversation, you may substitute your School Ring in place of the usual ring when making a roll involving that target.

**Status:** Server-side foundation (Phase 7), skill-roll submenu (Phase 8), and Attack/Wound-Check modal checkboxes (Phase 9) complete; parry menu pending Phase 10; final exclusion sweep + importer integration pending Phase 11.

Scope decisions:
- Usage is **not tracked** - attack rolls etc. carry no target identity, so the once-per-target-per-round limit is enforced by player honor.
- **In-scope rolls** (formula builders accept `ring_override`): skill rolls, rollable knack rolls (excluding iaijutsu), attack rolls (non-iaijutsu variants), parry rolls, wound check rolls.
- **Out-of-scope rolls** (no `ring_override` support): damage rolls, initiative rolls, iaijutsu, athletics. Damage and initiative are excluded by the rules; iaijutsu is excluded by the rules; athletics uses `(2*Ring)k(Ring)` which already factors the ring into both rolled and kept counts (the swap would be ambiguous and the UI never offers it).

Phase 7 deliverables:
- `app/routes/pages.py` exposes `kitsune_warden_ring_swap_available: bool` and `kitsune_warden_school_ring: str` in `school_abilities`. Available iff school is `kitsune_warden` AND a school ring is chosen.
- `app/services/dice.py` formula builders accept `ring_override: Optional[str] = None`:
  - `build_skill_formula`
  - `build_knack_formula` (raises `ValueError` if called with `ring_override` for iaijutsu)
  - `build_combat_formula` (attack and parry)
  - `build_wound_check_formula`
- New `RollFormula` fields `kitsune_swap_from_ring` and `kitsune_swap_to_ring` record the swap for the UI breakdown. `build_wound_check_formula` returns the same metadata in its dict shape. Empty strings when no swap is in effect.

**Unit tests:** `test_dice.py::TestKitsuneWarden::test_*ring_override*` plus `test_*ring_swap*`, `test_iaijutsu_attack_rejects_ring_override`, and three negative tests asserting the out-of-scope formula builders do NOT expose a `ring_override` param (signature-level guards).

### Phase 8: Skill-roll dropdown submenu

For each in-scope formula (skills + rollable knacks excluding iaijutsu + attack + parry + wound check), the server attaches a compact `kitsune_swap` sub-dict containing the swap-ring rolled/kept/label values. The post-pass lives in `app/services/dice.py::_attach_kitsune_swaps` and runs at the tail of `build_all_roll_formulas`. The sub-dict is omitted when the swap would be a no-op (the override ring's value equals the natural ring's value), so the UI gate is automatic.

The skill click menu (`app/templates/character/sheet.html`) gets a new `kitsune-skill-swap-block` template, visible when the formula has a `kitsune_swap` sub-dict and the menu is the basic skill/knack menu (not parry / attack-choice / etc.). It contains:
- A label "Kitsune Warden: {SchoolRing} instead of {DefaultRing}"
- A "Roll {Skill} ({SchoolRing})" button (`data-kitsune-swap-roll`)
- One "{VP option} (using {SchoolRing})" button per available VP option (`data-kitsune-swap-vp="{count}"`)

`executeRoll` accepts a fifth parameter `useKitsuneSwap` (default false). When true, it merges `formula.kitsune_swap` fields into the local formula copy before running the roll, so the swap's rolled/kept/label/swap-metadata propagate into `this.formula` and post-roll bonuses (raises, conviction, etc.) stack on top correctly.

The roll-result panel renders a `kitsune-swap-result-annotation` div when `formula.kitsune_swap_to_ring` is non-empty: "Kitsune Warden Special Ability: rolled with X instead of Y."

**Clicktests:** 8 cases — visibility on different ring values, hidden when natural ring already matches, hidden when values equal, hidden for iaijutsu, swap formula correctness, annotation visible after swap, annotation hidden without swap, void spend carries through swap.

### Phase 9: Attack & Wound Check modal checkboxes

The Attack modal and Wound Check modal each get a Kitsune ring-swap checkbox above their probability table. Checkbox visibility gates on `formula.kitsune_swap` being attached, so equal-ring-value cases (e.g. Kitsune with school ring Fire AND attack default ring Fire) automatically hide the option.

Server-side, `app/routes/pages.py` extends both `attack_probs[key]` and `wc_probs` with parallel `kitsune_swap` sub-dicts containing the swap-baseline `void_keys` / `probs` / `avgs`. The client's `_atkProbsForCurrent()` helper and `wcProbRow` switch between default and swap data based on the modal's `atkKitsuneSwap` / `wcKitsuneSwap` state.

When the user rolls with the checkbox checked, `rollAttack` and `rollWoundCheck` merge the formula's `kitsune_swap` fields (rolled, kept, label, swap-metadata) before void/raises/etc. stack on top. The result panel shows a `kitsune-attack-swap-annotation` or `kitsune-wc-swap-annotation` div mirroring the Phase 8 skill-roll annotation.

iaijutsu rolls intentionally bypass the Attack modal (Kitsune lacks the Kakita-specific `knack:iaijutsu:attack` formula), so the iaijutsu exclusion happens upstream in formula construction rather than via UI gating.

**Clicktests:** 7 cases — attack-modal checkbox visible + swaps prob table, attack hidden when ring values equal, iaijutsu knack roll has no swap, WC modal checkbox visible + swaps prob table, WC hidden when school ring is Water (default), attack swap annotation, WC swap annotation.

---

## 1st Dan

> Roll one extra die on three rolls of your choice.

**Status:** Fully implemented.

- Eligible picks: all skills + all rollable knacks (iaijutsu IS eligible here, unlike for the 3rd Dan picker and the special ability) + attack + parry + wound_check + damage + initiative. Picks must be distinct.
- Stored in `Character.technique_choices.first_dan_choices` (list of up to 3 strings; existing JSON column, no migration needed).
- Server: `app/services/dice.py` flexible-1st-Dan branches in `_apply_school_technique_bonus()` (skills/knacks/attack/parry — already existed pre-Kitsune), `build_wound_check_formula()`, `build_initiative_formula()`, the damage block of `build_all_roll_formulas()`, and the `_annotate_attack_type()` bonus_sources display path.
- Editor UI: `app/templates/character/edit.html` `kitsune-1st-dan-picker` block with three dropdowns (`kitsune-1st-dan-slot-0/1/2`); each slot disables values picked in the other two slots. Constants `KITSUNE_1ST_DAN_COMBAT_ROLLS` and `KITSUNE_1ST_DAN_LABELS` define the combat-roll subset (initiative is included alongside attack/parry/wound_check/damage). Helper methods: `kitsune1stDanEligibleKnacks()`, `kitsune1stDanIsTakenInOtherSlot()`, `setKitsune1stDanChoice()`.

**Implementation:** `app/game_data.py` (`SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["first_dan_extra_die"] = None`), `app/services/dice.py` (flexible-1st-Dan branches), `app/templates/character/edit.html` (picker UI + helpers).

**Unit tests:** `test_dice.py::TestKitsuneWarden::test_first_dan_*` (14 cases covering single/triple picks, all 8 roll-type branches including iaijutsu knack, no-bonus-below-Dan-1, persistence through technique_choices, empty/missing pick lists).

**Clicktests:**
- `test_school_abilities.py::test_kitsune_1st_dan_three_picker_dropdowns_visible_at_dan_1`
- `test_school_abilities.py::test_kitsune_1st_dan_picker_includes_iaijutsu_option`
- `test_school_abilities.py::test_kitsune_1st_dan_picks_distinct_no_duplicates`
- `test_school_abilities.py::test_kitsune_1st_dan_pick_extra_die_applied_to_roll`
- `test_school_abilities.py::test_kitsune_1st_dan_picks_persist_across_reload`

---

## 2nd Dan

> You get a free raise on a type of roll of your choice.

**Status:** Fully implemented (reuses the existing flexible-2nd-Dan wiring).

- `SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["second_dan_free_raise"] = None` (set in Phase 1) triggers the existing flexible branch in `_apply_school_technique_bonus()`, plus parallel branches in `build_wound_check_formula()` and the damage block of `build_all_roll_formulas()`. No server-side code changes — Kitsune was added to the comments next to the existing Ide / Ishi / Shugenja / Suzume comment blocks.
- Choice persists in `Character.technique_choices.second_dan_choice` (existing JSON column).
- Editor UI: `kitsune_warden` was added to the `FLEXIBLE_2ND_DAN_SCHOOLS` set in `app/templates/character/edit.html`. The existing picker (data-testid `flex-2nd-dan-picker`, select `flex-2nd-dan-select`) renders for Kitsune at Dan >= 2 with no template change. Eligible roll types: skills + rollable knacks + attack/parry/wound_check/damage (initiative is excluded - free raise is meaningless on an initiative roll).

**Implementation:** `app/templates/character/edit.html` (FLEXIBLE_2ND_DAN_SCHOOLS membership), `app/services/dice.py` (existing flexible branches; comments updated to mention Kitsune), `app/game_data.py` (Phase 1 stub).

**Unit tests:** `test_dice.py::TestKitsuneWarden::test_second_dan_*` (6 cases: chosen skill / no choice / wound check / damage / attack / no-bonus-below-Dan-2).

**Clicktests:**
- `test_school_abilities.py::test_kitsune_2nd_dan_picker_visible_and_saves`

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your precepts skill, which may be applied to the following rolls: attack, wound checks, and three skills of your choice. You may not spend more than X of these free raises on a single roll. You may also perform priest rituals at the cost of one free raise per ritual.

**Status:** Fully implemented.

- `SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["third_dan"]` extends the standard 3rd Dan dict shape with a new field `applicable_to_choices_count: 3`. The `applicable_to` list is the always-on `["attack", "wound_check"]`; player picks add to that set at runtime.
- Server: `app/services/dice.py::_annotate_third_dan` reads `Character.technique_choices.third_dan_skill_choices` (List[str]) when `applicable_to_choices_count` is set, unioning the picks into `third_dan_applicable`. Iaijutsu is dropped defensively (the picker excludes it; this is belt-and-braces).
- Per-adventure counter: the existing `adventure_raises` entry in `app/routes/pages.py` (line ~320) automatically picks Kitsune up since the `tech_bonuses.get("third_dan")` test fires on any school whose `SCHOOL_TECHNIQUE_BONUSES` entry has a `third_dan` dict.
- Editor UI: new `kitsune-3rd-dan-picker` block in `app/templates/character/edit.html` with three skill dropdowns (`kitsune-3rd-dan-slot-0/1/2`). Options are sourced from `KITSUNE_3RD_DAN_SKILL_IDS`, which is `MANTIS_2ND_DAN_SKILL_IDS` minus iaijutsu. Picks must be distinct (each slot disables values picked in the other two). Helper methods `kitsune3rdDanIsTakenInOtherSlot()` and `setKitsune3rdDanChoice()`.
- "Priest rituals at cost of one free raise per ritual" is narrative-only (out of scope for the sheet).

**Implementation:** `app/game_data.py` (third_dan dict with applicable_to_choices_count), `app/services/dice.py::_annotate_third_dan` (union with player picks), `app/templates/character/edit.html` (picker UI + KITSUNE_3RD_DAN_SKILL_IDS constant + helpers).

**Unit tests:** `test_dice.py::TestKitsuneWarden::test_third_dan_*` (9 cases: attack always, WC always, chosen skills, unpicked skill, iaijutsu exclusion, pool size, max_per_roll, no-bonus-below-Dan-3, no-picks-only-attack-and-wound-check).

**Clicktests:**
- `test_school_abilities.py::test_kitsune_3rd_dan_skill_picker_excludes_iaijutsu`
- `test_school_abilities.py::test_kitsune_3rd_dan_chosen_skill_offers_raise_button`
- `test_school_abilities.py::test_kitsune_3rd_dan_unpicked_skill_no_raise_button`
- `test_school_abilities.py::test_kitsune_3rd_dan_attack_always_offers_raise`
- `test_school_abilities.py::test_kitsune_3rd_dan_wound_check_always_offers_raise`
- `test_school_abilities.py::test_kitsune_3rd_dan_per_adventure_counter_visible`

---

## 4th Dan

> Raise your current and maximum School Ring by 1. Raising your School Ring now costs 5 fewer XP. When you would roll fewer than 10 dice on athletics actions (i.e. when you roll (2 * Ring)k(Ring) for physical actions), roll 10 dice instead.

**Status:** Fully implemented.

- **Ring raise + 5 XP discount:** reuses the existing 4th-Dan school-ring pattern. `app/services/xp.py::calculate_ring_xp` already keys off `dan` and `school_ring`, with no school-specific code. `enforceFourthDanRing()` in `app/templates/character/edit.html` auto-raises the player-chosen school ring (Air/Fire/Earth/Water for Kitsune) from 3 to 4 when reaching Dan 4. `ringMax()` returns 7 for the school ring at Dan 4. Smoke-tested: Dan 4 Water=4 costs 0 XP; Dan 4 Water=5 costs 20 XP (5*5 - 5 discount).
- **10-dice athletics floor:** new flag `kitsune_athletics_10_dice_floor` exposed from `app/routes/pages.py` when `school == "kitsune_warden" && dan >= 4`. Applied in `app/services/dice.py::build_athletics_formula` and `build_athletics_combat_formula` — when the formula's rolled count is below 10, set rolled = 10. **Rolled count only; kept stays at the ring value** (Ring 2 -> 4k2 becomes 10k2, not 10k10). Mirrors Ikoma Bard's `ikoma_10_dice_floor` pattern. The athletics-combat formulas (athletics-attack / athletics-parry) also get the floor as defense in depth, but the View Sheet does not surface those options to Kitsune Warden by default (no athletics in school knacks; existing baseline gates athletics-attack/parry on `athletics_combat_everywhere` which is Togashi-only).

**Implementation:** `app/services/xp.py` (existing), `app/templates/character/edit.html` (existing 4th Dan ring logic), `app/routes/pages.py` (new `kitsune_athletics_10_dice_floor` flag), `app/services/dice.py` (10-dice floor in both athletics formulas).

**Unit tests:** `test_dice.py::TestKitsuneWarden::test_4th_dan_*` (8 cases: ring xp discount, athletics floor raises rolled to 10, doesn't lower above 10, doesn't change kept, applies to athletics-attack, applies to athletics-parry, no floor below Dan 4, floor only for Kitsune).

**Clicktests:**
- `test_school_abilities.py::test_kitsune_4th_dan_athletics_roll_shows_10_dice_floor`
- `test_school_abilities.py::test_kitsune_below_4th_dan_athletics_uses_normal_formula`
- `test_school_abilities.py::test_kitsune_4th_dan_athletics_attack_hidden_without_athletics_knack`
- `test_school_abilities.py::test_kitsune_4th_dan_school_ring_auto_raise_for_water_choice`

---

## 5th Dan

> Select a spell from the shugenja spell list from your School Ring's element. Gain a modified version of that spell.

**Status:** OUT OF SCOPE - spell list not modeled in the character sheet. Rules text only; no UI affordance.

---

## Importer Aliases

Source documents may refer to the school as "Fox", "Fox Warden", or "Kitsune". All three map to `kitsune_warden` via `_SCHOOL_ALIASES` in `app/services/import_match.py`. The canonical "Kitsune Warden" string is matched directly.
