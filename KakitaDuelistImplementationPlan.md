# Kakita Duelist Implementation Plan

This plan brings the Kakita Duelist school to full feature parity with the rest of the game. Each phase is independently shippable; later phases build on earlier ones.

**School abilities recap** (from `app/game_data.py` and `school-features/KakitaDuelist.md`):
- **Special Ability** — 10s on initiative rolls go into Phase 0. Phase 0 action dice are spent on iaijutsu attacks. Interrupt attacks (Phase 0) are iaijutsu.
- **1st Dan** — extra die on double_attack / iaijutsu / initiative (done, keep as-is).
- **2nd Dan** — free raise on iaijutsu rolls (done, keep as-is).
- **3rd Dan** — attack bonus = X × (defender's next phase - attacker's phase), where X = attack skill; defenders with no remaining action count as phase 11; applies to all attacks; know the next action of everyone in striking range.
- **4th Dan** — Fire ring raise + free raise on iaijutsu damage (done, keep as-is).
- **5th Dan** — at the start of phase 0, make a contested iaijutsu roll against an opponent; damage scales by ±1 die per 5-point contest difference.

---

## Phase 1 — Verify & strengthen the Phase 0 Special Ability

Today the initiative path in `sheet.html` already maps `value === 10` to `0` when `formula.kakita_phase_zero` is set, and an initiative-result note mentions Phase 0. That logic has no unit tests and the UI barely calls out phase-0 dice on the Actions panel. This phase locks the foundation down so every downstream feature has something reliable to key off.

### What to do

1. **Server**
   - Confirm `build_initiative_formula()` in `app/services/dice.py` sets `kakita_phase_zero = True` for `kakita_duelist`.
   - Add a `school_abilities.kakita_phase_zero` flag in `app/routes/pages.py` (true for Kakita Duelist) so the client can gate UI without reading the initiative formula from the dice roller cross-scope.

2. **Client**
   - Walk through `runRoll()` around the existing `v === 10 ? 0 : v` mapping and make sure the converted value persists to `actionDice`, `window._trackingBridge`, and the server-saved `action_dice` payload (so the 0 survives a reload — relies on the earlier `_sanitize_action_dice` fix that already preserves `value`).
   - In the Actions-panel per-die rendering (`sheet.html` around the action-die SVG), add a gold/phase-zero visual class when `die.value === 0` *and* `schoolAbilities.kakita_phase_zero` (CSS already has `.phase-zero .die-text`).
   - Tooltip on a value-0 die should read "Phase 0 (Kakita interrupt): iaijutsu attacks only."

### COVERAGE.md additions

Unit tests (`test_dice.py`):
- [ ] `test_kakita_initiative_formula_has_phase_zero_flag` — `build_initiative_formula` stamps `kakita_phase_zero=True` for Kakita, not for other schools.
- [ ] `test_non_kakita_initiative_no_phase_zero_flag` — the flag is absent for every other school.
- [ ] `test_routes_pages_exposes_kakita_phase_zero_ability` — `school_abilities["kakita_phase_zero"]` is `True` for Kakita, `False` otherwise.

Clicktests (`test_school_abilities.py`):
- [ ] `test_kakita_initiative_10s_become_phase_0_dice` — Kakita initiative roll with mocked-high dice produces action dice with `value === 0` flagged as phase-zero.
- [ ] `test_kakita_phase_zero_die_survives_reload` — roll initiative, reload the page, the 0 die is still present and still carries its visual marker.
- [ ] `test_non_kakita_10s_stay_as_10s_on_initiative` — regression: non-Kakita initiative keeps 10s at 10 (no Phase 0).
- [ ] `test_kakita_phase_zero_die_has_gold_svg_class` — the rendered SVG for a value-0 die carries the `.phase-zero` class.

---

## Phase 2 — Phase 0 dice may only spend on iaijutsu attacks

The Special Ability text says Phase-0 actions are iaijutsu attacks. Today the per-die menu on a value-0 die shows every normal option (Roll Attack, Roll Parry, Feint, …) just like any other die. This phase makes the restriction real.

### What to do

1. **Client — per-die menu (`sheet.html`)**
   - Add a new template branch inside the `<template x-if="!die.spent">` block that runs *first* when `die.value === 0 && schoolAbilities.kakita_phase_zero`:
     - Only render a single "Iaijutsu Attack" item plus "Mark as spent" (and preserve the existing Togashi/Mantis 3rd-Dan items where they legitimately apply — for Kakita neither of those fire, so the menu is effectively one item).
     - Suppress Roll Attack, Double Attack, Counterattack, Lunge, Feint, Parry, Predeclared Parry, Athletics Attack/Parry for value-0 dice when the flag is set.
   - Iaijutsu as attack: iaijutsu is currently a non-attack-type knack that opens the dice-roller modal. For Kakita phase-0 we want the attack modal. Route this menu item through a new entrypoint (e.g. `rollForActionDie('knack:iaijutsu:attack', i)`) that either (a) stamps `is_attack_type=True` on a duplicated formula at build time server-side, or (b) has the client open `openAttackModal('knack:iaijutsu')` with a special flag noting it's a phase-0 attack. Option (a) is cleaner — add `knack:iaijutsu:attack` to `build_all_roll_formulas` for Kakita only, flagged with `is_attack_type=True` and `attack_variant='iaijutsu'`.

2. **Server (`app/services/dice.py`)**
   - In `build_all_roll_formulas`, when the character is Kakita Duelist and has iaijutsu rank >= 1, expose a `knack:iaijutsu:attack` key mirroring the existing iaijutsu knack formula but with `is_attack_type=True` and `attack_variant='iaijutsu'`. Damage fields should match the iaijutsu-damage metadata already computed at `dice.py:1087+`.

3. **Attack modal adjustments**
   - The attack modal needs to accept `knack:iaijutsu:attack` as a valid key. Verify `labelMap` and `atkFormula.attack_variant` branches handle "iaijutsu"; update the title, damage display, and result breakdown to read "Iaijutsu Attack".
   - When opened for a phase-0 die (detectable via `_preSpentDieIndex` pointing at a die with `value === 0`), render a small note: "Phase 0 Kakita interrupt attack."

### COVERAGE.md additions

Unit tests (`test_dice.py`):
- [ ] `test_kakita_iaijutsu_attack_formula_exposed` — `build_all_roll_formulas` returns `knack:iaijutsu:attack` for Kakita only, with `is_attack_type=True` and `attack_variant="iaijutsu"`.
- [ ] `test_non_kakita_no_iaijutsu_attack_formula` — other schools don't get the attack-variant key.
- [ ] `test_kakita_iaijutsu_attack_formula_mirrors_iaijutsu_knack_rolled_kept` — rolled/kept match the regular iaijutsu knack formula.
- [ ] `test_kakita_iaijutsu_attack_formula_respects_4th_dan_damage_bonus` — iaijutsu-damage metadata on the attack formula inherits the Kakita 4th Dan +5 flat on damage.

Clicktests (`test_school_abilities.py`):
- [ ] `test_kakita_phase_zero_die_menu_shows_only_iaijutsu_attack` — value-0 die's per-die menu shows "Iaijutsu Attack" and "Mark as spent" and nothing else.
- [ ] `test_kakita_non_zero_die_menu_unchanged` — a normal (value 1-10) die for a Kakita still exposes the full regular menu.
- [ ] `test_kakita_phase_zero_menu_opens_attack_modal_for_iaijutsu` — clicking the Iaijutsu Attack item on a 0 die opens the attack modal with `atkFormula.attack_variant === 'iaijutsu'`.
- [ ] `test_kakita_phase_zero_attack_modal_notes_interrupt` — the pre-roll page shows a "Phase 0 Kakita interrupt attack" note.
- [ ] `test_kakita_phase_zero_attack_spends_the_clicked_die` — rolling from that modal spends the phase-0 die (not some other one).

---

## Phase 3 — 3rd Dan defender-next-phase bonus on attack rolls

Mirror the Shinjo-phase-bonus wiring from the recent commit. The attack modal asks the player for the defender's next phase, uses the spent action die's value as the attacker's phase, and computes `max(0, defender_phase - attacker_phase) × attack_skill`. Live probability-chart updates apply.

### What to do

1. **Server**
   - Add `school_abilities.kakita_3rd_dan_defender_phase_bonus_x = attack_skill` (non-zero only when `kakita_duelist` + dan >= 3).
   - Stamp `kakita_3rd_dan_defender_phase_bonus = True` on every attack-type formula (base attack, attack-type knacks including `knack:iaijutsu:attack` from Phase 2, athletics-attack) for Kakita 3rd Dan+.

2. **Client — attack modal pre-roll**
   - New state: `atkKakitaDefenderPhase: 11` (default = "defender has no actions" = phase 11, per the rules).
   - New block shown when `atkFormula.kakita_3rd_dan_defender_phase_bonus && schoolAbilities.kakita_phase_zero` (Kakita-only) AND `initiativeWarningVariant() === null` AND `_shinjoDieToSpend() !== null` (reuse the existing "which die is about to be spent" helper, or pull it out into a shared `_dieToSpend()`):
     - Display: "Kakita 3rd Dan: defender's next action in phase [select]. Die [value] held for X phases (+X×attack to roll)."
     - Dropdown options: 1-10 and an 11 labeled "no remaining actions".
   - Compute bonus helpers (`_kakita3rdDanBonus()` → number) and plumb into `atkHitChance`, `atkAvgAttackRoll`.
   - `rollAttack()` stamps the bonus onto the formula (`kakita_3rd_dan_bonus`, `kakita_3rd_dan_defender_phase`, `kakita_3rd_dan_attacker_phase`) and adds to `formula.flat`.
   - Post-roll breakdown: "+N from Kakita 3rd Dan (die V, defender phase P-A)".

3. **Edge cases**
   - Defender acts before attacker (bonus would be negative) → clamp to 0.
   - No unspent action dice → no bonus control shown (existing warning fires instead), same pattern as Shinjo.
   - Phase-0 attacks: attacker_phase = 0. If defender acts in phase 5, bonus = 5 × attack.

### COVERAGE.md additions

Unit tests (`test_dice.py`):
- [ ] `test_kakita_3rd_dan_attack_flag_set` — every attack-type formula carries `kakita_3rd_dan_defender_phase_bonus=True` for Kakita 3rd Dan+.
- [ ] `test_kakita_3rd_dan_parry_no_flag` — parry doesn't carry the flag.
- [ ] `test_kakita_3rd_dan_knack_flags` — counterattack / double_attack / lunge / iaijutsu-as-attack formulas all carry the flag.
- [ ] `test_kakita_3rd_dan_athletics_attack_flag` — athletics-as-attack carries the flag.
- [ ] `test_kakita_below_3rd_dan_no_flag` — Kakita at Dan 1/2 does not carry the flag.
- [ ] `test_kakita_3rd_dan_flag_only_for_kakita_school` — other schools never carry it.

Clicktests (`test_school_abilities.py`):
- [ ] `test_kakita_3rd_dan_defender_phase_control_hidden_without_initiative` — no action dice ⇒ no bonus control (warning shows instead).
- [ ] `test_kakita_3rd_dan_defender_phase_control_hidden_out_of_dice` — every die spent ⇒ no bonus control.
- [ ] `test_kakita_3rd_dan_defender_phase_control_visible_with_action_dice` — action die present ⇒ control rendered, dropdown defaulted to 11 ("no remaining actions").
- [ ] `test_kakita_3rd_dan_bonus_applied_to_attack_roll` — with attacker die=4, defender phase=10, attack skill=2 ⇒ +12 stamped on `formula.kakita_3rd_dan_bonus`, labeled in breakdown.
- [ ] `test_kakita_3rd_dan_bonus_clamps_when_defender_acts_first` — attacker die=7, defender phase=3 ⇒ +0 (clamp).
- [ ] `test_kakita_3rd_dan_bonus_shifts_probability_chart` — picking a later defender phase raises `atkHitChance()` live.
- [ ] `test_kakita_3rd_dan_bonus_uses_clicked_die_value` — opening attack via a specific action die's menu computes the bonus against that die's value.
- [ ] `test_kakita_3rd_dan_phase_11_default_represents_no_remaining_actions` — the dropdown's labeled "no remaining actions" option yields the expected bonus for attacker_phase=die.value.
- [ ] `test_kakita_below_3rd_dan_no_bonus_control` — Kakita 2nd Dan doesn't render the control.

---

## Phase 4 — Phase 0 interrupt-attack button

The Special Ability grants Kakita the right to interrupt in phase 0 at the cost of their 2 highest action dice. This is a voluntary action the player can take *instead of* keeping a natural phase-0 die. Implement as a dedicated tracking-section button that spends the 2 highest unspent dice and opens the attack modal for an iaijutsu attack with `attacker_phase = 0`.

### What to do

1. **Client — tracking section (`sheet.html`)**
   - Add a button labeled "Phase 0 Interrupt (-2 highest dice)" inside the Actions block when `schoolAbilities.kakita_phase_zero` is set.
   - Enabled only when `>= 2` unspent non-athletics-only dice remain (athletics-only dice cannot pay for iaijutsu attacks; Kakita's school doesn't grant any, so this is purely defensive).
   - Click handler:
     - Find the two highest-valued unspent non-athletics-only dice.
     - Mark both spent with `spent_by = "Kakita Phase 0 interrupt"`.
     - Persist via `window._trackingBridge.save()`.
     - Open the attack modal with `openAttackModal('knack:iaijutsu:attack', null)` — `_preSpentDieIndex` stays null because no single die paid for the attack.
     - Stamp a new `atkForceAttackerPhase = 0` on the dice roller so the 3rd Dan bonus computation uses 0 as the attacker phase instead of the spent-die value.

2. **Attack modal**
   - When opened via the interrupt button, show a banner: "Phase 0 Kakita interrupt attack (2 highest dice spent)."
   - 3rd Dan defender-phase dropdown still applies, attacker_phase = 0.
   - Damage inherits Kakita 4th Dan +5 flat from existing iaijutsu-damage metadata.

3. **Reset**
   - If the player closes the modal without rolling, the 2 dice STAY spent (per rules — they paid the cost by declaring). Alternative: give them a "Cancel interrupt, refund dice" button — but the rules don't grant a refund. Ship without a refund; flag the decision in the feature doc.

### COVERAGE.md additions

Clicktests (`test_school_abilities.py`):
- [ ] `test_kakita_interrupt_button_hidden_for_non_kakita` — other schools never see the button.
- [ ] `test_kakita_interrupt_button_hidden_below_1st_dan` — not applicable (Special Ability is 1st Dan); instead: `test_kakita_interrupt_button_visible_on_kakita_sheet`.
- [ ] `test_kakita_interrupt_button_disabled_with_fewer_than_two_dice` — only 1 unspent die ⇒ disabled.
- [ ] `test_kakita_interrupt_button_spends_two_highest_dice` — click marks the 2 highest unspent dice spent with the Kakita label.
- [ ] `test_kakita_interrupt_button_opens_iaijutsu_attack_modal` — click opens the attack modal with `attack_variant === 'iaijutsu'` and an interrupt banner.
- [ ] `test_kakita_interrupt_attack_uses_phase_zero_as_attacker_phase` — 3rd Dan bonus with defender phase=10 yields +10 × attack (because attacker_phase=0).
- [ ] `test_kakita_interrupt_attack_inherits_4th_dan_damage_bonus` — Kakita 4th Dan interrupt damage roll includes the iaijutsu +5 flat.
- [ ] `test_kakita_interrupt_persists_after_modal_close` — closing the modal without rolling leaves the 2 dice spent (no refund).

---

## Phase 5 — 5th Dan contested iaijutsu at phase 0 (new modal)

The 5th Dan technique is its own mini-duel. It deserves a dedicated modal — the existing iaijutsu duel modal expects a full duel sequence (contested, then optional focus / strike) which isn't the right shape for a one-shot contested iaijutsu at the start of a round.

### What to do

1. **Server**
   - Add `school_abilities.kakita_5th_dan_phase_zero_contest = True` (only for Kakita Duelist + dan >= 5).

2. **Client — new modal (`sheet.html`)**
   - Add a "Kakita 5th Dan: Phase 0 Contested Iaijutsu" button in the tracking section (gated on the flag). Show alongside the existing interrupt button; probably in the Kakita abilities subsection.
   - New Alpine state for the dedicated modal: `kakita5thOpen`, `kakita5thPhase ('pre' | 'rolling' | 'result' | 'damage-rolling' | 'damage-result')`, `kakita5thOpponentHasIaijutsu: true`, `kakita5thOpponentRollTotal: 0`, `kakita5thDefenderPhase: 11`.
   - Pre-roll UI:
     - Checkbox "Opponent has iaijutsu knack" (default checked). When unchecked, display "Opponent rolls attack instead; you gain +1 free raise (+5 flat) on your iaijutsu roll."
     - 3rd Dan defender-phase dropdown (reuse the Phase-3 control) when flag is set; attacker_phase = 0 (phase 0 by rule).
     - Button "Roll Iaijutsu (contested)".
   - Roll flow:
     - Uses the iaijutsu knack formula plus any 3rd-Dan bonus and the +5 "no-iaijutsu" bonus.
     - After rolling, show the character's total and an input for "Opponent's iaijutsu/attack roll total" (with a "Won contested roll?" auto-indicator derived from `baseTotal > kakita5thOpponentRollTotal`).
     - Button "Roll Damage".
   - Damage flow:
     - Start from the iaijutsu damage metadata (2k1 + 4th Dan +5 if applicable).
     - Compute extra/fewer damage dice: `diff = baseTotal - kakita5thOpponentRollTotal`. If won by ≥ 5 ⇒ `+floor(diff/5)` rolled dice. If lost by ≥ 5 ⇒ `-floor(|diff|/5)` rolled dice (clamp at 0k0).
     - Show the modified formula and a "Roll Damage" button that runs the animation + result.
   - Result panel shows the contested outcome, the damage total, and a Close button.

3. **Round reset hook**
   - 5th Dan is once per combat round. When initiative is rolled again (which calls `resetMantisRound` style), also reset a `kakita_5th_dan_used_this_round` flag so the button becomes enabled again. Store on the tracking bridge.
   - Disable the button when `kakita_5th_dan_used_this_round` is true; re-enable on the next initiative roll.

### COVERAGE.md additions

Unit tests (`test_dice.py`):
- [ ] `test_school_abilities_exposes_kakita_5th_dan_phase_zero_contest` — flag true for Kakita Dan 5, false below and for other schools.

Clicktests (`test_school_abilities.py`):
- [ ] `test_kakita_5th_dan_button_visible_on_kakita_dan_5_sheet` — button is rendered.
- [ ] `test_kakita_below_5th_dan_hides_button` — Kakita Dan 4 doesn't see it.
- [ ] `test_kakita_5th_dan_button_opens_phase_zero_contest_modal` — click opens the new modal in 'pre' phase.
- [ ] `test_kakita_5th_dan_modal_defaults_opponent_has_iaijutsu_true` — checkbox defaults on.
- [ ] `test_kakita_5th_dan_opponent_without_iaijutsu_grants_plus_5_flat` — unchecking the checkbox adds a labeled +5 flat to the pre-roll summary.
- [ ] `test_kakita_5th_dan_3rd_dan_bonus_applies_with_attacker_phase_0` — Dan 5 character also at Dan 3+ (which they are by construction) sees the defender-phase dropdown; picking phase 10 ⇒ +10 × attack skill bonus from attacker_phase=0.
- [ ] `test_kakita_5th_dan_rolls_iaijutsu_contested` — clicking Roll produces a baseTotal consistent with the iaijutsu formula + bonuses.
- [ ] `test_kakita_5th_dan_damage_scales_up_on_win_by_5` — entering an opponent roll 5 below yours adds 1 rolled damage die.
- [ ] `test_kakita_5th_dan_damage_scales_down_on_loss_by_5` — entering an opponent roll 5 above yours removes 1 rolled damage die (floor 0 enforced).
- [ ] `test_kakita_5th_dan_damage_unchanged_when_diff_under_5` — a 4-point difference leaves the damage formula alone.
- [ ] `test_kakita_5th_dan_button_disabled_after_use_until_next_initiative` — rolling disables the button; rolling initiative re-enables it.
- [ ] `test_kakita_5th_dan_modal_inherits_4th_dan_damage_bonus` — Kakita Dan 5 (so ≥ 4) damage gets +5 flat.
- [ ] `test_kakita_5th_dan_modal_cancel_before_roll_does_not_consume` — closing the modal via × on the pre-phase does not flip `kakita_5th_dan_used_this_round`.

---

## Cross-phase concerns

1. **Shared helpers** — the Phase-3 / Phase-5 3rd-Dan control should share one Alpine method. Factor `_dieToSpend()` (currently `_shinjoDieToSpend`) into a neutral helper.
2. **Regression risk** — Phase 2 introduces `knack:iaijutsu:attack` which shares the attack-modal code path. Existing iaijutsu-strike and iaijutsu-duel tests must still pass; add a smoke clicktest `test_existing_iaijutsu_duel_still_opens` to flag any accidental regression.
3. **Documentation** — after each phase, update `school-features/KakitaDuelist.md` to mark the affected Dans "Fully implemented", list the new tests, and describe the implementation paths.
4. **Tracking the phase-0 attack attacker_phase** — the 3rd Dan math needs a way to say "this attack happens at phase 0" even when no 0-valued die was spent (Phase 4 interrupt). Introduce `atkForceAttackerPhase` on the dice roller: null by default, overridden by the interrupt / 5th Dan entrypoints. `_dieToSpend()` / bonus helpers read this override first.

---

## Suggested ordering and why

1. **Phase 1 first** because every later phase assumes phase-0 dice exist reliably.
2. **Phase 2 next** — small scope, validates the iaijutsu-as-attack plumbing that Phases 4 and 5 reuse.
3. **Phase 3 next** — same die-selection helper will be reused in Phases 4 and 5, so establish the pattern once.
4. **Phase 4** — builds directly on the Phase-2 attack variant and the Phase-3 3rd-Dan control.
5. **Phase 5** — biggest scope, new modal, reuses everything above.
