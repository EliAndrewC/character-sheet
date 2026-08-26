# Kitsune Warden

**School ID:** `kitsune_warden`
**Category:** Bushi (carries iaijutsu, so bucketed with the Bushi schools).
**School Ring:** Any non-Void (player picks at character creation; persists in `Character.school_ring_choice`).
**School Knacks:** absorb_void, commune, iaijutsu. Absorb_void is non-rollable; per-adventure counter where each use regains 1 spent VP. Commune is rolled with the character's School Ring (see "Commune rolls the School Ring" below).

Commune costs a void point to activate (see "Commune activation cost" below) and is rolled with the character's School Ring (see "Commune rolls the School Ring" below).

---

## Special Ability

> Once per target per combat round or conversation, you may substitute your School Ring in place of the usual ring when making a roll involving that target.

**Status:** Fully implemented across server + UI (Phases 7-11). Iaijutsu rolls and equal-value swaps are excluded server-side via `_attach_kitsune_swaps`; UI gates are defensive. The importer recognizes `third_dan_skill_choices` in source documents.

Scope decisions:
- Usage is **not tracked** - attack rolls etc. carry no target identity, so the once-per-target-per-round limit is enforced by player honor.
- **In-scope rolls** (formula builders accept `ring_override`): skill rolls, rollable knack rolls (excluding iaijutsu), attack rolls (non-iaijutsu variants), parry rolls, wound check rolls.
- **No school knack of this school is actually swappable**, so `_attach_kitsune_swaps` has no school-knack loop: absorb_void is not rolled, iaijutsu is rules-excluded, and commune already rolls the School Ring so the substitution is a no-op. `tests/test_dice.py::TestKitsuneWarden::test_no_school_knack_is_swappable` pins that list; the foreign-knack loop still runs.
- **Out-of-scope rolls** (no `ring_override` support): damage rolls, initiative rolls, iaijutsu, athletics. Damage and initiative are excluded by the rules; iaijutsu is excluded by the rules; athletics uses `(2*Ring)k(Ring)` which already factors the ring into both rolled and kept counts (the swap would be ambiguous and the UI never offers it).

Phase 7 deliverables:
- `app/routes/pages.py` exposes `kitsune_warden_ring_swap_available: bool` and `kitsune_warden_school_ring: str` in `school_abilities`. Available iff school is `kitsune_warden` AND a school ring is chosen.
- `app/services/dice.py` formula builders accept `ring_override: Optional[str] = None`:
  - `build_skill_formula`
  - `build_knack_formula` (raises `ValueError` if called with `ring_override` for iaijutsu)
  - `build_combat_formula` (attack and parry)
  - `build_wound_check_formula`
- New `RollFormula` fields `kitsune_swap_from_ring` and `kitsune_swap_to_ring` record the swap for the UI breakdown. `build_wound_check_formula` returns the same metadata in its dict shape. Empty strings when no swap is in effect.

### Phase 8: Skill-roll dropdown submenu

For each in-scope formula (skills + rollable knacks excluding iaijutsu + attack + parry + wound check), the server attaches a compact `kitsune_swap` sub-dict containing the swap-ring rolled/kept/label values. The post-pass lives in `app/services/dice.py::_attach_kitsune_swaps` and runs at the tail of `build_all_roll_formulas`. The sub-dict is omitted when the swap would be a no-op (the override ring's value equals the natural ring's value), so the UI gate is automatic.

The skill click menu (`app/templates/character/sheet.html`) gets a new `kitsune-skill-swap-block` template, visible when the formula has a `kitsune_swap` sub-dict and the menu is the basic skill/knack menu (not parry / attack-choice / etc.). It contains:
- A label "Kitsune Warden: {SchoolRing} instead of {DefaultRing}"
- A "Roll {Skill} ({SchoolRing})" button (`data-kitsune-swap-roll`)
- One "{VP option} (using {SchoolRing})" button per available VP option (`data-kitsune-swap-vp="{count}"`)

`executeRoll` accepts a fifth parameter `useKitsuneSwap` (default false). When true, it merges `formula.kitsune_swap` fields into the local formula copy before running the roll, so the swap's rolled/kept/label/swap-metadata propagate into `this.formula` and post-roll bonuses (raises, conviction, etc.) stack on top correctly.

The roll-result panel renders a `kitsune-swap-result-annotation` div when `formula.kitsune_swap_to_ring` is non-empty: "Kitsune Warden Special Ability: rolled with X instead of Y."

### Phase 9: Attack & Wound Check modal checkboxes

The Attack modal and Wound Check modal each get a Kitsune ring-swap checkbox above their probability table. Checkbox visibility gates on `formula.kitsune_swap` being attached, so equal-ring-value cases (e.g. Kitsune with school ring Fire AND attack default ring Fire) automatically hide the option.

Server-side, `app/routes/pages.py` extends both `attack_probs[key]` and `wc_probs` with parallel `kitsune_swap` sub-dicts containing the swap-baseline `void_keys` / `probs` / `avgs`. The client's `_atkProbsForCurrent()` helper and `wcProbRow` switch between default and swap data based on the modal's `atkKitsuneSwap` / `wcKitsuneSwap` state.

When the user rolls with the checkbox checked, `rollAttack` and `rollWoundCheck` merge the formula's `kitsune_swap` fields (rolled, kept, label, swap-metadata) before void/raises/etc. stack on top. The result panel shows a `kitsune-attack-swap-annotation` or `kitsune-wc-swap-annotation` div mirroring the Phase 8 skill-roll annotation.

iaijutsu rolls intentionally bypass the Attack modal (Kitsune lacks the Kakita-specific `knack:iaijutsu:attack` formula), so the iaijutsu exclusion happens upstream in formula construction rather than via UI gating.

### Phase 10: Parry top-level menu entries

The parry roll menu (`rollMenuHasParry` template) gains a `kitsune-parry-swap-block` containing two extra top-level entries — "Roll Parry ({SchoolRing})" and "Predeclared {SchoolRing}-Parry (+5)" — each with its own VP submenu mirroring the existing Air parry entries. Visibility gate: `formulas.parry.kitsune_swap` is attached AND `kitsune_swap.kept > parry.kept` (i.e., the swap is an upgrade). The `kept > kept` check covers both the spec's "school ring isn't Air" requirement (server already excludes equal-value swaps) and the "school ring's value > Air's value" requirement (downgrade swaps don't appear).

The predeclared swap entry calls a new 6-arg form of `executeRollWithExtraFlat(key, voidSpent, option, extraFlat, reason, useKitsuneSwap)`. The swap is applied before the +5 stacks. The Roll-swap entry uses the existing `executeRoll(key, voidSpent, option, owSpent, useKitsuneSwap=true)` from Phase 8.

### Phase 11: Polish + importer

**Iaijutsu exclusion sweep:** every UI surface (skill submenu, attack-modal checkbox, WC-modal checkbox, parry submenu) gates on the formula's `kitsune_swap` sub-dict, which `_attach_kitsune_swaps` server-side never attaches to iaijutsu paths (`knack:iaijutsu`, `knack:iaijutsu:strike`, `knack:iaijutsu:attack`). The iaijutsu duel modal is a separate self-contained flow with no Kitsune UI.

**Equal-ring suppression sweep:** `_diff_or_none` server-side returns None when the swap's rolled/kept matches the original's, so equal-value swaps are never attached. Confirmed working for the edge case Air=Water=3 with school ring Water.

**Importer integration:** the LLM extraction schema (`app/services/import_schema.py`) gained a `third_dan_skill_choices: List[str]` field with a Kitsune-specific description. `app/services/import_validate.py::_resolve_technique_choices` resolves the source-stated skill names against the SKILLS catalog, dropping iaijutsu (rules-excluded — surfaces a "iaijutsu is not eligible" reason) and unknown names ("unknown skill name" reason). Stub payloads in `app/services/import_llm.py` updated to keep schema consistent. Existing `Fox` / `Fox Warden` / `Kitsune` school-name aliases (Phase 1) continue to resolve to `kitsune_warden`.

---

## 1st Dan

> Roll one extra die on any three rolls.

**Status:** Fully implemented.

- Eligible picks: all skills + all rollable knacks (iaijutsu IS eligible here, unlike for the 3rd Dan picker and the special ability) + attack + parry + wound_check + damage + initiative. Picks must be distinct.
- Stored in `Character.technique_choices.first_dan_choices` (list of up to 3 strings; existing JSON column, no migration needed).
- Server: `app/services/dice.py` flexible-1st-Dan branches in `_apply_school_technique_bonus()` (skills/knacks/attack/parry — already existed pre-Kitsune), `build_wound_check_formula()`, `build_initiative_formula()`, the damage block of `build_all_roll_formulas()`, and the `_annotate_attack_type()` bonus_sources display path.
- Editor UI: `app/templates/character/edit.html` `kitsune-1st-dan-picker` block with three dropdowns (`kitsune-1st-dan-slot-0/1/2`); each slot disables values picked in the other two slots. Constants `KITSUNE_1ST_DAN_COMBAT_ROLLS` and `KITSUNE_1ST_DAN_LABELS` define the combat-roll subset (initiative is included alongside attack/parry/wound_check/damage). Helper methods: `kitsune1stDanEligibleKnacks()`, `kitsune1stDanIsTakenInOtherSlot()`, `setKitsune1stDanChoice()`.

**Implementation:** `app/game_data.py` (`SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["first_dan_extra_die"] = None`), `app/services/dice.py` (flexible-1st-Dan branches), `app/templates/character/edit.html` (picker UI + helpers).

---

## 2nd Dan

> You get a free raise on any type of roll.

**Status:** Fully implemented (reuses the existing flexible-2nd-Dan wiring).

- `SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["second_dan_free_raise"] = None` (set in Phase 1) triggers the existing flexible branch in `_apply_school_technique_bonus()`, plus parallel branches in `build_wound_check_formula()` and the damage block of `build_all_roll_formulas()`. No server-side code changes — Kitsune was added to the comments next to the existing Ide / Ishi / Shugenja / Suzume comment blocks.
- Choice persists in `Character.technique_choices.second_dan_choice` (existing JSON column).
- Editor UI: `kitsune_warden` was added to the `FLEXIBLE_2ND_DAN_SCHOOLS` set in `app/templates/character/edit.html`. The existing picker (data-testid `flex-2nd-dan-picker`, select `flex-2nd-dan-select`) renders for Kitsune at Dan >= 2 with no template change. Eligible roll types: skills + rollable knacks + attack/parry/wound_check/damage (initiative is excluded - free raise is meaningless on an initiative roll).

**Implementation:** `app/templates/character/edit.html` (FLEXIBLE_2ND_DAN_SCHOOLS membership), `app/services/dice.py` (existing flexible branches; comments updated to mention Kitsune), `app/game_data.py` (Phase 1 stub).

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is your precepts skill, which may be spent on attack, wound checks, and any three skills after seeing your roll.  You may not spend more than X of these free raises on a single roll.  You may also perform priest rituals at the cost of one free raise per ritual.

**Status:** Fully implemented.

- `SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["third_dan"]` extends the standard 3rd Dan dict shape with a new field `applicable_to_choices_count: 3`. The `applicable_to` list is the always-on `["attack", "wound_check"]`; player picks add to that set at runtime.
- Server: `app/services/dice.py::_annotate_third_dan` reads `Character.technique_choices.third_dan_skill_choices` (List[str]) when `applicable_to_choices_count` is set, unioning the picks into `third_dan_applicable`. Iaijutsu is dropped defensively (the picker excludes it; this is belt-and-braces).
- Per-adventure counter: the existing `adventure_raises` entry in `app/routes/pages.py` (line ~320) automatically picks Kitsune up since the `tech_bonuses.get("third_dan")` test fires on any school whose `SCHOOL_TECHNIQUE_BONUSES` entry has a `third_dan` dict.
- Editor UI: new `kitsune-3rd-dan-picker` block in `app/templates/character/edit.html` with three skill dropdowns (`kitsune-3rd-dan-slot-0/1/2`). Options are sourced from `KITSUNE_3RD_DAN_SKILL_IDS`, which is `MANTIS_2ND_DAN_SKILL_IDS` minus iaijutsu. Picks must be distinct (each slot disables values picked in the other two). Helper methods `kitsune3rdDanIsTakenInOtherSlot()` and `setKitsune3rdDanChoice()`.
- "Priest rituals at cost of one free raise per ritual" is narrative-only (out of scope for the sheet).

**Implementation:** `app/game_data.py` (third_dan dict with applicable_to_choices_count), `app/services/dice.py::_annotate_third_dan` (union with player picks), `app/templates/character/edit.html` (picker UI + KITSUNE_3RD_DAN_SKILL_IDS constant + helpers).

---

## 4th Dan

> Raise your current and maximum School Ring by 1.  Raising your School Ring now costs 5 fewer XP.  When you would roll fewer than 10 dice on athletics actions (i.e. when you roll (2 * Ring)k(Ring) for physical actions), roll 10 dice instead.

**Status:** Fully implemented.

- **Ring raise + 5 XP discount:** reuses the existing 4th-Dan school-ring pattern. `app/services/xp.py::calculate_ring_xp` already keys off `dan` and `school_ring`, with no school-specific code. `enforceFourthDanRing()` in `app/templates/character/edit.html` auto-raises the player-chosen school ring (Air/Fire/Earth/Water for Kitsune) from 3 to 4 when reaching Dan 4. `ringMax()` returns 7 for the school ring at Dan 4. Smoke-tested: Dan 4 Water=4 costs 0 XP; Dan 4 Water=5 costs 20 XP (5*5 - 5 discount).
- **10-dice athletics floor:** new flag `kitsune_athletics_10_dice_floor` exposed from `app/routes/pages.py` when `school == "kitsune_warden" && dan >= 4`. Applied in `app/services/dice.py::build_athletics_formula` and `build_athletics_combat_formula` — when the formula's rolled count is below 10, set rolled = 10. **Rolled count only; kept stays at the ring value** (Ring 2 -> 4k2 becomes 10k2, not 10k10). Mirrors Ikoma Bard's `ikoma_10_dice_floor` pattern. The athletics-combat formulas (athletics-attack / athletics-parry) also get the floor as defense in depth, but the View Sheet does not surface those options to Kitsune Warden by default (no athletics in school knacks; existing baseline gates athletics-attack/parry on `athletics_combat_everywhere` which is Togashi-only).

**Implementation:** `app/services/xp.py` (existing), `app/templates/character/edit.html` (existing 4th Dan ring logic), `app/routes/pages.py` (new `kitsune_athletics_10_dice_floor` flag), `app/services/dice.py` (10-dice floor in both athletics formulas).

---

## 5th Dan

> Select a spell from the shugenja spell list from your School Ring's element.  Gain a modified version of that spell.

**Status:** OUT OF SCOPE - spell list not modeled in the character sheet. Rules text only; no UI affordance.

---

## Commune rolls the School Ring

> Commune (rules 05-school_knacks): "Spend a void point and roll this knack with the Ring of the element of the spirits you are questioning."

**Status:** Fully implemented.

**GM ruling (2026-08-08):** the knack's ring "varies" in the abstract, but a character who has commune as a school knack is trained to commune with the kami of their own school element, so their commune rolls always use their School Ring. A Fox with School Ring Air shows Commune badged "Air" and always rolls Air.

- **Server:** `app/game_data.py::effective_knack_ring` resolves the pinned ring from `SCHOOL_RING_KNACK_IDS` (currently just commune) plus `Character.school_ring_choice`. `build_knack_formula` uses it for the dice and the "Commune (Air)" label; the sheet and Google Sheets export routes stamp it as `info["ring"]` on each knack entry.
- **Catalog unchanged:** `SCHOOL_KNACKS["commune"].ring` is still `"varies"` - only a character's copy is pinned. Spellcasting deliberately stays "varies" (its ring is per-spell, not per-character).
- **UI:** the sheet's knack row badges `info.ring`; the expanded rules text appends "Your School Ring is X, so your commune rolls always use X." The editor's school-reference panel has no character, so it badges commune with the words "School Ring".
- **Fallback:** a draft with no School Ring recorded keeps the old Earth placeholder rather than guessing.
- **Interaction with the special ability:** the School Ring swap is a no-op on commune (it already uses that ring), so no swap row is offered.
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

---

## Importer Aliases

Source documents may refer to the school as "Fox", "Fox Warden", or "Kitsune". All three map to `kitsune_warden` via `_SCHOOL_ALIASES` in `app/services/import_match.py`. The canonical "Kitsune Warden" string is matched directly.
