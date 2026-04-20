# Kakita Duelist Implementation Plan

**Status: all five phases shipped.** Per-phase test inventories have been consolidated into `tests/e2e/COVERAGE.md` (clicktests) and `tests/test_dice.py` / `tests/test_routes.py` (unit tests); this doc is kept as the historical design record. See `school-features/KakitaDuelist.md` for the current per-ability status.

This plan brought the Kakita Duelist school to full feature parity with the rest of the game. Each phase was independently shippable; later phases built on earlier ones.

**School abilities recap** (from `app/game_data.py` and `school-features/KakitaDuelist.md`):
- **Special Ability** — 10s on initiative rolls go into Phase 0. Phase 0 action dice are spent on iaijutsu attacks. Interrupt attacks (Phase 0) are iaijutsu.
- **1st Dan** — extra die on double_attack / iaijutsu / initiative (done, keep as-is).
- **2nd Dan** — free raise on iaijutsu rolls (done, keep as-is).
- **3rd Dan** — attack bonus = X × (defender's next phase - attacker's phase), where X = attack skill; defenders with no remaining action count as phase 11; applies to all attacks; know the next action of everyone in striking range.
- **4th Dan** — Fire ring raise + free raise on iaijutsu damage (done, keep as-is).
- **5th Dan** — at the start of phase 0, make a contested iaijutsu roll against an opponent; damage scales by ±1 die per 5-point contest difference.

---

## Phase 1 — Make Kakita initiative actually keep its 10s as Phase 0

Today's bug: the client's initiative sort (`runRoll()` around `const sortedAsc = [...indexed].sort((a, b) => a.value - b.value)`) keeps the lowest dice, so 10s are always *unkept*. The subsequent `v === 10 ? 0 : v` rewrite therefore never fires on a kept die — a Kakita's 10s get discarded instead of becoming Phase 0 action dice. The fix is to sort 10s as if they were 0s for Kakita, which makes them the first dice the keep-lowest logic picks up; the existing post-keep rewrite then turns them into value-0 action dice.

### What to do

1. **Server**
   - Confirm `build_initiative_formula()` in `app/services/dice.py` sets `kakita_phase_zero = True` for `kakita_duelist`.
   - Add a `school_abilities.kakita_phase_zero` flag in `app/routes/pages.py` (true for Kakita Duelist) so the client can gate UI without reading the initiative formula from the dice roller cross-scope.

2. **Client — sort + keep path (`runRoll()` in `sheet.html`)**
   - Introduce a helper `sortValue(v)` that returns `0` when `this.formula.kakita_phase_zero && v === 10`, otherwise `v`. Sort `indexed` by `sortValue(a.value) - sortValue(b.value)`. Tiebreak on original index so repeated rolls remain stable.
   - `keptIdx` (initiative branch) still slices the bottom `keptCount` of the sorted list — with the new sort, any rolled 10s now occupy the bottom positions and get kept.
   - After the kept slice is populated, the existing `actions.map(v => v === 10 ? 0 : v)` converts them to Phase-0 dice. Verify ordering: `actions.sort((a, b) => a - b)` should run AFTER the 10→0 rewrite (else 10s end up sorted to the back despite being Phase 0). The current code has the sort first and the rewrite after; move the rewrite above the final sort, or sort by `sortValue` in both places.
   - Persistence: the 0-valued entries flow into `window._trackingBridge.setActionDice(...)` ⇒ `save()` ⇒ `_sanitize_action_dice` (already preserves `value`), so reload is already covered.

3. **Actions-panel visual**
   - The existing SVG class binding already writes `phase-zero` when `die.value === 0` and `base.html` already paints that class dark red. Confirm this path fires for the per-die button in the Actions panel (it does — same binding as the initiative-result modal uses). Tooltip on a value-0 die should read "Phase 0 (Kakita interrupt): iaijutsu attacks only." (Phase 2 tightens the menu to actually restrict this.)

4. **Regression guard**
   - For a non-Kakita character, the sort helper is a passthrough — 10s still get un-kept and the action dice never contain 0s. Re-run the Togashi/Shinjo/Mantis initiative clicktests to be sure.

### reroll_tens is NOT a concern here

`build_initiative_formula` already sets `reroll_tens: False` for every school (`dice.py:889`, confirmed by the docstring "No reroll-10s"). So a rolled 10 on initiative stays exactly 10 for any character; no Kakita-specific reroll-disable is needed.

### Tests (all delivered)

Unit tests covering the flag on the initiative formula + `school_abilities` exposure live in `test_dice.py::TestSchoolAbilities::test_kakita_phase_zero_flag`, `test_non_kakita_initiative_no_phase_zero_flag`, and `test_routes.py::TestKakitaPhaseZeroFlag::{test_kakita_has_phase_zero_flag, test_non_kakita_does_not_have_phase_zero_flag}`. Clicktests covering the 10-sorts-as-0 keep, multiple 10s, non-Kakita regression, `.phase-zero` SVG marker, reload persistence, and the iaijutsu-only tooltip are all listed in `tests/e2e/COVERAGE.md` under the Kakita section.

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

### Tests (all delivered)

Unit tests for the Kakita-only `knack:iaijutsu:attack` formula live in `test_dice.py::TestSchoolAbilities::{test_kakita_iaijutsu_attack_formula_exposed, test_non_kakita_no_iaijutsu_attack_formula, test_kakita_iaijutsu_attack_formula_mirrors_iaijutsu_knack_rolled_kept, test_kakita_iaijutsu_attack_formula_respects_4th_dan_damage_bonus, test_kakita_below_4th_dan_iaijutsu_attack_no_damage_bonus}`. Clicktests covering the restricted per-die menu, the non-zero regression, attack-modal routing, interrupt note, clicked-die spend, and the non-Kakita regression are all listed in `tests/e2e/COVERAGE.md`.

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

### Tests (all delivered)

Unit tests for the `kakita_3rd_dan_defender_phase_bonus` flag across every attack-type formula (plus negatives for parry, sub-3rd-Dan, and non-Kakita) live in `test_dice.py::TestSchoolAbilities::{test_kakita_3rd_dan_attack_flag_set, test_kakita_3rd_dan_parry_no_flag, test_kakita_3rd_dan_attack_knack_flags, test_kakita_3rd_dan_athletics_attack_flag, test_kakita_3rd_dan_iaijutsu_attack_flag, test_kakita_below_3rd_dan_no_defender_phase_flag, test_kakita_3rd_dan_flag_only_for_kakita_school}`. Clicktests for the hidden/visible states, bonus application, clamping, live probability-chart updates, clicked-die value, phase-11 default, below-3rd-Dan hide, and the Phase-0-die case are all listed in `tests/e2e/COVERAGE.md`.

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

### Tests (all delivered)

Clicktests covering the hidden-for-non-Kakita state, visible-on-Kakita button, the disabled-with-fewer-than-two-dice gate, the 2-highest spend mechanics, opens-iaijutsu-modal-with-banner flow, phase-0 attacker_phase plumbing, 4th Dan damage inheritance through the interrupt path (`test_kakita_interrupt_attack_inherits_4th_dan_damage_bonus`), the no-additional-third-die-spent invariant, the no-init-warning suppression, and the no-refund-on-close behavior are all listed in `tests/e2e/COVERAGE.md`.

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

### Tests (all delivered)

Unit tests for the `school_abilities.kakita_5th_dan_phase_zero_contest` flag (Kakita Dan 5+ only) live in `test_routes.py::TestKakitaPhaseZeroFlag::{test_kakita_5th_dan_has_phase_zero_contest_flag, test_kakita_below_5th_dan_no_phase_zero_contest_flag, test_non_kakita_no_phase_zero_contest_flag}`. Clicktests covering the button visibility on Dan 5 and hide below, the modal entry, the opponent-iaijutsu checkbox default + the +5 no-iaijutsu bonus, the 3rd Dan bonus at attacker_phase=0, the roll applying both bonuses, damage scaling up/down/unchanged, the disabled-after-use / re-enabled-on-initiative cycle, the cancel-before-roll invariant, 4th Dan damage inheritance, and reload persistence are all listed in `tests/e2e/COVERAGE.md`.

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
