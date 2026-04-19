# Mantis Wave-Treader Implementation Plan

This is the phased implementation plan for the new Mantis Wave-Treader bushi school. The school's rules and current status live in [./school-features/MantisWaveTreader.md](./school-features/MantisWaveTreader.md). Read that first - this document assumes familiarity with the ability text.

The school is unusually UI-heavy because it centres on per-phase posture selection. To keep reviewable diffs small, the work is broken into the phases below. The phases exist to make the work easier to review and validate incrementally - they are not a commit plan. The user handles all git operations (commits, pushes, deploys) and decides when those happen. Claude should not commit or push between phases unless explicitly asked. A likely flow is that the user commits and pushes between phases, but that's the user's call. Each phase should still land with unit tests, a `COVERAGE.md` entry, and clicktests for any frontend changes, per the workflow in `CLAUDE.md`.

**Clicktest scope during this effort:** run only the targeted clicktests for the phase being worked on - the specific new tests added in that phase plus any directly related existing tests (e.g. the school-selection suite for Phase 1, the `school_abilities` mark for later phases). Do NOT run the full e2e suite between phases. The full suite is deferred until Phase 11 (post-deploy), per `CLAUDE.md` step 8.

---

## Phase 1 - School definition, "Any" ring, and listing

Scope: get the school selectable in the editor and treated as a bushi school everywhere, without any abilities wired up yet.

- Add a `School(id="mantis_wave_treader", ...)` entry to `SCHOOLS` in `app/game_data.py` next to the other bushi schools. Set `category="bushi"` (this automatically adds it to `SCHOOLS_BUSHI_NONBUSHI` via `_BUSHI_CATEGORIES`).
- Add a new `school_ring="Any"` value. Extend the `SCHOOL_RING_OPTIONS` loop to expand "Any" to `["Air", "Fire", "Earth", "Water", "Void"]`. Update the `# pragma: no cover` guard comment to reflect the new recognised value.
- **Default ring is Void, and only for Mantis.** The existing variable-ring default in `app/templates/character/edit.html:1357` hardcodes Water for any non-fixed ring. Replace that with a branch that picks Void when the newly-selected school is `mantis_wave_treader` and keeps Water for every other variable-ring school. The analogous block in `app/templates/character/create.html` (around line 668) currently sets `schoolRingChoice = ''` and does not auto-raise a ring; mirror the new branch there too so Mantis defaults to Void on both Create and Edit. No other school should change default behaviour.
- Clicktest (add to `test_editor_controls.py`): selecting Mantis Wave-Treader in the school dropdown sets the school-ring picker to Void and bumps the Void ring to at least 3; selecting Priest (or any other variable-ring school) still defaults to Water.
- Record the three school knacks (`athletics`, `iaijutsu`, `worldliness`).
- Encode the raw technique text in `techniques={1: ..., 2: ..., 3: ..., 4: ..., 5: ...}` so the editor tooltips render correctly even before the mechanics are wired up.
- Unit tests in `test_game_data.py`:
  - School is registered.
  - `SCHOOL_RING_OPTIONS["mantis_wave_treader"]` contains all five rings.
  - School shows up in the bushi half of `SCHOOLS_BUSHI_NONBUSHI`.
  - Each school knack resolves to a valid `SchoolKnack`.
- No UI work in this phase beyond the school appearing in the editor's school dropdown. Add a quick clicktest in `test_editor_controls.py` that the school is selectable and saves.

**Done when:** a character can be created with school Mantis Wave-Treader, any ring can be picked as the school ring, and the View Sheet page renders without JS errors (even though no abilities fire).

---

## Phase 2 - 1st Dan extra dice (data-only)

Scope: the simplest technique first to validate that generic plumbing covers it.

- Add `"mantis_wave_treader": {"first_dan_extra_die": ["initiative", "athletics", "wound_check"], "second_dan_free_raise": None}` to `SCHOOL_TECHNIQUE_BONUSES`. Leave 2nd Dan null for now (implemented in Phase 3).
- Unit tests in `test_dice.py`:
  - Initiative formula includes the extra die at Dan 1+.
  - Athletics formula includes the extra die at Dan 1+ (across all four ring variants).
  - Wound check formula includes the extra die at Dan 1+.
  - No bonus at Dan 0.
- Clicktest in `test_school_abilities.py::test_mantis_1st_dan_formula_extra_die` mark `@pytest.mark.school_abilities` showing the three formula strings on the View Sheet.
- Add entries to `tests/e2e/COVERAGE.md`.

**Done when:** a Dan 1 Mantis rolls +1 rolled die on initiative, athletics, and wound checks.

---

## Phase 3 - 2nd Dan flexible free raise

Scope: player-chosen free raise on "a type of roll of your choice". Mirrors the Priest 1st Dan flexible extra die.

- Keep `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- Extend the existing `technique_choices` JSON column usage. Define a `"mantis_2nd_dan_free_raise"` key whose value is the chosen roll type.
- Editor UI: a dropdown that appears next to the 2nd Dan technique description when the school is Mantis Wave-Treader and Dan >= 2.
- Choice set: any rollable thing for which a free raise is mechanically meaningful. Concretely:
  - All rollable skills.
  - The rollable school knacks for this character (for Mantis: `athletics` and `iaijutsu` - `worldliness` is excluded because it's passive).
  - Combat rolls: `attack`, `damage`, `parry`, `wound_check`.
  - **Excluded:** `initiative` (free raise has no meaning on an initiative roll) and any non-rollable knack.
- The picker enforces this set - `initiative` must not appear as an option, and the only knacks that appear are the rollable ones. Validate server-side on save, too, so a crafted POST can't persist `initiative` or `worldliness` as the chosen roll.
- `_apply_school_technique_bonus()` honours the choice as a +5 flat bonus on the matching roll. For wound check specifically, add a branch to `build_wound_check_formula` that mirrors the existing `second_dan_free_raise == "wound_check"` path but for the flexible choice (so the `+5 from 2nd Dan` label still lands in `bonus_sources`).
- **Damage choice needs its own plumbing.** Damage rolls are not a `RollFormula`; the damage-side bonuses live in `damage_flat_bonus`, `damage_extra_rolled`, `damage_extra_kept`, and `damage_bonus_sources`, hand-assembled in `_annotate_attack_type` in `app/services/dice.py` (see the Yogo/Kuni and Brotherhood blocks for precedent). When the Mantis 2nd Dan choice is `damage`:
  - Add `+5` to `damage_flat_bonus` in `_annotate_attack_type`.
  - Append `"+5 from 2nd Dan (damage)"` to `damage_bonus_sources`.
  - Extend `atkComputeDamage()` in `app/templates/character/sheet.html` so the `+5` shows up as a labeled line in the damage result breakdown (currently `atkDamageParts` aggregates rolled/kept dice under a single "from school" line and drops flat bonuses entirely). The fix is to push an explicit `"+5 flat from 2nd Dan"` entry into `parts` when `damage_flat_bonus > 0` has a matching label in `damage_bonus_sources`. The modal breakdown at `sheet.html:2915-2934` already iterates `atkDamageParts`, so no template change is needed once `parts` is populated.
- Unit tests covering: the chosen roll gets +5; unchosen rolls do not; no bonus below Dan 2. Specifically exercise damage as a choice to cover the new `_annotate_attack_type` branch.
- Clicktests - one per choice in the eligible set (skills, knacks, attack, parry, wound_check, damage):
  - Select the choice in the editor, save, then verify the formula on the sheet picks up +5.
  - Verify the bonus is **visually labeled** in the relevant modal, not just applied. For attack: both the pre-roll "Bonuses:" line (via `bonus_sources`) and the post-roll result breakdown (via `formula.bonuses`). For parry / skills / knacks: the post-roll result breakdown. For wound check: the WC modal's `bonus_sources` row. **For damage: both the attack modal's pre-roll damage preview AND the post-roll damage result breakdown must show the labeled +5.**
  - Switch the choice to something else and verify the bonus moves.

**Done when:** a Dan 2 Mantis can pick any one roll type and see a +5 free raise applied to it, and only to it.

---

## Phase 4 - Posture tracker UI (state only, no bonuses yet)

Scope: build the per-phase posture clicker without wiring any mechanical effects. Makes the interaction testable in isolation.

- Server: pass `school_abilities.mantis_posture_tracking = True` from `routes/pages.py` when school is Mantis Wave-Treader.
- Client: add Alpine state to `trackingData()`:
  - `posturePhase` (1-10)
  - `postureHistory` (array of `"offensive" | "defensive"`, length == `posturePhase - 1`)
  - `currentPosture` (last entry in `postureHistory`, or `null`)
- Render a new block inside the Tracking section (directly under the existing discretionary bonuses area) with:
  - Two buttons side by side: "Offensive Posture for Phase X" and "Defensive Posture for Phase X". X is `posturePhase`.
  - Both disabled when `posturePhase > 10`.
  - Clicking appends to `postureHistory` and increments `posturePhase`.
  - Below the buttons, a "Current: Phase X - <Posture>" line when a posture has been selected.
- **Two reset triggers, both full per-round resets:**
  - Rolling initiative (wire into `rollInitiative()` and `rollInitiativeAthleticsVariant()`).
  - Clicking the action-dice "Clear" button (and the future "Clear bonuses" button in Phase 8 - they are equivalent end-of-round actions).
  - Both zero `posturePhase` back to 1 and empty `postureHistory`. Phases 6, 7, and 8 hang additional state off these same triggers (5th Dan counters, 3rd Dan accumulators, etc.), so centralise the reset in a single helper (e.g. `resetMantisRound()`) that all triggers call.
- Persist `posturePhase` and `postureHistory` through the tracking bridge so they survive page reloads (same pattern as `actionDice`).
- Clicktests in `test_school_abilities.py` mark `@pytest.mark.school_abilities`:
  - Buttons appear on Mantis sheets and are absent on non-Mantis.
  - Clicking advances X and records the chosen posture.
  - Both buttons disable at X=11.
  - Rolling initiative resets state back to Phase 1.
  - Clicking the action-dice "Clear" button also resets state back to Phase 1.
- Update `COVERAGE.md`.

**Done when:** a Mantis sheet shows the posture tracker, clicks advance it through Phase 10, and both initiative and the action-dice "Clear" button reset it.

---

## Phase 5 - Special ability bonuses from the current posture

Scope: make the current posture actually apply its +5 free raises and TN bump.

- **Attack rolls during offensive posture** - apply +5 via the generic `bonus_sources` pathway in `_annotate_attack_type` (push a `"+5 from offensive posture"` entry into `bonus_sources` and add `+5` to `flat` / `bonuses[]`). Already labeled in both the pre-roll probability display and post-roll result breakdown once it's in `bonus_sources` / `formula.bonuses`.
- **Damage rolls during offensive posture** - same damage-side plumbing as Phase 3's damage choice. In `_annotate_attack_type`, add `+5` to `damage_flat_bonus` and `"+5 from offensive posture"` to `damage_bonus_sources` when `currentPosture === 'offensive'` at roll time (this will need to be a client-side overlay rather than a server-side formula field, since posture state lives in the tracking bridge - see next bullet). The same extension to `atkComputeDamage` from Phase 3 handles the display side.
- **Posture is a runtime client-side condition**, not a static formula field. The server-side formulas don't know which posture is active; that's derived from `postureHistory`. Approach: in `atkComputeDamage()` and in the attack modal's pre-roll probability computation, when `window._trackingBridge?.currentPosture === 'offensive'`, add `+5` to the damage flat and to the attack flat, and push a labeled entry into whichever display list the existing code reads from (`atkDamageParts` for damage, `atkFormula.bonus_sources` for attack). Do the same overlay for the wound check modal when posture is defensive.
- **Wound checks during defensive posture** - overlay `+5` into the wound check modal's `bonus_sources` display AND into `wcRollTotal` / `wcMargin` / `wcSeriousWounds` / `wcPassed`. The WC modal is the canonical place for this; no server-side change needed since WC opens on the defender's own sheet.
- **TN to be hit** - while `currentPosture === 'defensive'`, the sheet's TN display shows +5 (render as `base + 5` with a tooltip "Mantis Wave-Treader defensive posture"). Purely visual on the Mantis's sheet.
- **Posture-tracker block summary** - display a short line beneath the current-posture line enumerating the active bonuses ("+5 to attack rolls", "+5 to damage rolls", etc.) so the player can see what's live.
- Unit tests: formula totals and overlay math at Dan 1 when current posture is offensive vs defensive (including damage-side).
- Clicktests:
  - Offensive posture: roll an attack and verify both the pre-roll "Bonuses:" row and the post-roll result breakdown show `"+5 from offensive posture"`.
  - Offensive posture: roll damage after the attack and verify both the pre-roll damage preview and the post-roll damage result breakdown show the labeled +5 (this covers the `atkComputeDamage` / `atkDamageParts` path).
  - Defensive posture: open the WC modal and verify the `bonus_sources` row includes `"+5 from defensive posture"`, the total reflects the bonus, and the TN display shows `base + 5` with the tooltip.
  - Toggling postures mid-round updates the active bonus summary on the tracker and is picked up by the next roll.

**Done when:** choosing a posture immediately changes the bonuses displayed on the sheet and carried into the attack / wound check modals.

---

## Phase 6 - 5th Dan accumulated posture counters

Scope: per-round running totals from each posture declaration.

- Derive `offensivePhaseCount` and `defensivePhaseCount` from `postureHistory` (counts of each value).
- Only active when Dan >= 5. Pass `school_abilities.mantis_posture_accumulation = True` from server.
- Display a new "Accumulated 5th Dan bonuses" sub-block under the posture tracker when Dan 5 and either count > 0:
  - "+N to attack and damage rolls" when offensive count > 0.
  - "+M to wound checks and TN" when defensive count > 0.
- Bonuses apply to attack / damage / wound check / TN alongside the Phase 5 special-ability bonus and any Phase 7/8 3rd Dan accumulators. Reuse the same overlay code paths:
  - Attack: overlay `"+N from Mantis 5th Dan (offensive posture count)"` into the attack modal's `bonus_sources` and result breakdown when `offensivePhaseCount > 0`.
  - Damage: overlay the labeled line into `atkDamageParts` via the same `atkComputeDamage` extension from Phases 3/5/7.
  - Wound check: overlay into the WC modal's `bonus_sources` via the same extension from Phase 5.
  - TN display: add `defensivePhaseCount` to the Mantis's displayed TN with an enumerated tooltip.
- Reset on both triggers from Phase 4 (initiative roll and the action-dice "Clear" button) - derived from `postureHistory` so they follow automatically once `postureHistory` resets.
- Unit tests and clicktests covering accumulation across multiple phases and reset on both triggers. Each clicktest must assert the labeled line is present in the relevant modal, not just that the total shifted.

**Done when:** a Dan 5 Mantis clicking offensive posture on phases 1, 3, 5 sees a persistent +3 on attack rolls that resets next round.

---

## Phase 7 - 3rd Dan offensive branch (attack modal button)

Scope: spend-an-action-die-for-X-attack/damage button on the attack roll result modal.

- Pass `school_abilities.mantis_3rd_dan_offensive = True` + `mantis_3rd_dan_x = attack_skill_rank` from server when Dan >= 3.
- In the attack result modal, render a button "Spend another action to increase attack and damage by X for the round" when:
  - `schoolAbilities.mantis_3rd_dan_offensive` is true
  - `currentPosture === 'offensive'`
  - At least one unspent action die remains
- Tooltip: the exact rules text for the offensive branch.
- Clicking:
  - Marks the lowest unspent action die as spent (label `spent_by: 'Mantis 3rd Dan (offensive)'`).
  - Adds X to the `offensive3rdDanAccum` tracking-bridge counter.
- `offensive3rdDanAccum` applies to all subsequent attack and damage rolls this round:
  - **Attack display** - overlay into the attack modal's pre-roll `bonus_sources` ("+X from Mantis 3rd Dan (offensive)") and post-roll result breakdown when the accumulator is non-zero.
  - **Damage display** - the same `atkComputeDamage` / `atkDamageParts` extension added in Phase 3 and Phase 5 is reused here. Push a labeled `"+X from Mantis 3rd Dan (offensive)"` entry into `parts` when `offensive3rdDanAccum > 0`, and add `offensive3rdDanAccum` into the damage flat total.
- Reset on initiative roll; cleared by "Clear bonuses" and by action-dice "Clear" (see Phase 8).
- Unit tests: pass the right X, reject when no action dice, reject when posture is defensive.
- Clicktests: spend the action die, then roll an attack and a damage roll; assert that both modals show the labeled `"+X from Mantis 3rd Dan (offensive)"` line and that the totals include the bonus. Repeat with the accumulator at 2X after two spends.

---

## Phase 8 - 3rd Dan defensive branch + Clear bonuses wiring

Scope: spend-action-die-for-X-wound-check/TN button and the full "Clear" plumbing.

- Render under the posture tracker block (not in a modal, per the user's spec): "Spend action to increase TN and wound checks by X" button.
- Visible only when `currentPosture === 'defensive'`, Dan >= 3, and at least one unspent action die remains.
- Tooltip: rules text for the defensive branch.
- Clicking spends the lowest unspent action die and adds X to `defensive3rdDanAccum`, which applies to:
  - **Wound checks** - overlay a labeled `"+X from Mantis 3rd Dan (defensive)"` entry into the WC modal's `bonus_sources` display and into `wcRollTotal` / `wcMargin` / `wcSeriousWounds` / `wcPassed`. This reuses the same WC-modal overlay path that Phase 5 sets up for the defensive posture +5.
  - **Displayed TN** - add `defensive3rdDanAccum` to the sheet's TN display, with a tooltip that enumerates the contributing bonuses (defensive posture +5, 3rd Dan accumulator, 5th Dan accumulator if Dan 5).
- **Clear bonuses button:** next to the defensive 3rd Dan button. Always visible when any of the accumulators are non-zero or any action die is present.
  - Semantically marks the **end of the combat round** - it is fully equivalent to the action-dice "Clear" button from Phase 4.
  - Both buttons call the same `resetMantisRound()` helper, which zeros `offensive3rdDanAccum`, `defensive3rdDanAccum`, empties `postureHistory`, resets `posturePhase` to 1, and calls `clearActionDice()` (clears ALL action dice). The 5th Dan counters fall out automatically since they are derived from `postureHistory`.
- Clicktests covering: defensive button appears and fires; the accumulator applies to the next wound check with a labeled line; clicking "Clear bonuses" zeros all accumulators, 5th Dan counters, posture history (back to Phase 1), and action dice; clicking the action-dice "Clear" button has the exact same effect; the TN display reflects the accumulators and clears with them.

---

## Phase 9 - Wound check probability table integration

Scope: make the probability / expected-serious-wounds display in the wound check modal reflect the posture bonuses so the player sees accurate odds before committing.

- Phases 5, 6, and 8 all overlay labeled bonus-source lines into the WC modal and update `wcRollTotal` / `wcMargin` / `wcSeriousWounds` / `wcPassed`. This phase is the pass that wires those bonuses into the **probability table** (the pre-roll "% chance" and "average serious wounds" computation), not just the post-roll total:
  - Defensive posture special-ability +5 (when current posture is defensive).
  - `defensive3rdDanAccum`.
  - 5th Dan `defensivePhaseCount` bonus (Dan 5+).
- The probability-table code already reads a flat-bonus argument; extend the caller to pass the sum of the three overlays when computing odds.
- Also audit that each overlay already pushes its label into the modal's `bonus_sources` display (done in earlier phases) - if any are missing, add them here.
- Unit tests in `test_dice.py` + front-end clicktests verifying that toggling posture, spending the 3rd Dan defensive button, and accumulating 5th Dan defensive counts each shift the displayed % chance and average SW, and that each bonus shows as a labeled row in the modal.

---

## Phase 10 - 4th Dan ring raise + bonus athletics action die

Scope: the Dan 4 mechanics. Left late because the ring-raise code needs the "Any" handling added in Phase 1, and the extra-die UI should reuse the infrastructure built in earlier phases.

- **Ring raise:** the 4th Dan raises the **school ring** only (not any arbitrary ring of the player's choice). This is the standard behaviour already enforced by `enforceFourthDanRing()` (editor) and `calculate_ring_xp()` (server), and for Mantis the school ring is whatever the player picked at character creation from the "Any" option (per Phase 1). Confirm both functions read `school_ring_choice` rather than the static `school_ring` value, so a Mantis who chose Void as their school ring gets +1 Void at Dan 4. Add unit tests covering: all five rings as the school ring choice, 4th Dan raises that ring's current and max by 1, costs the discounted 5-XP-fewer rate, and Dan 4 cannot be spent on a non-school ring.
- **Bonus athletics die:** after initiative is rolled, append a blue "1" die to `actionDice` with `value=1, spent=false, locked_value=true, restricted_to='movement/athletics/mantis_3rd_dan'`. Render with a distinct colour (reuse gold/blue variant) and a tooltip explaining the restriction. It's not actually rolled - it's added deterministically in `build_initiative_formula()` for Mantis Dan 4+ (mirroring the Togashi athletics-only pattern but always adding `[1]` regardless of variant).
- Enforcement of the spending restriction is display-only (same approach as Togashi today).
- Reset on initiative roll (recreated each round).
- "Clear" action-dice / "Clear bonuses" removes this die along with everything else; it reappears on the next initiative roll.
- Unit tests for the `build_initiative_formula` output and clicktests for the blue die appearing, being spendable, and being regenerated on the next initiative roll.

---

## Phase 11 - Docs, COVERAGE, and deploy

- Update `school-features/MantisWaveTreader.md` - replace the "TBD" sections with concrete file/function references and test names as each phase lands.
- Ensure every new clicktest appears in `tests/e2e/COVERAGE.md`.
- Run the full `@pytest.mark.school_abilities` clicktest suite locally.
- Deploy to Fly.io, then kick off the full e2e suite in the background per `CLAUDE.md` step 8.
