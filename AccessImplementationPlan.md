# Read-only Roll Mode — Implementation Plan

## Problem

Viewers without edit access can initiate rolls on the sheet (e.g. click
"Roll Initiative"), but the resulting state changes silently fail:
`POST /characters/{id}/track` returns 403, so action dice appear and
then vanish on refresh, with no user-facing explanation. Non-editors
also can't reach the downstream "spend this die" / "spend void" UI, so
the whole roll experience dead-ends.

## Goal

Make every roll **playable** without edit access — locally computed,
including resource spends — while persisting **nothing** to the
character. Surface a red banner on every roll result explaining why,
with a login prompt for anonymous viewers.

## Principles

1. **Always playable.** Any roll button available to the owner is
   available (and fully interactive) to a viewer.
2. **Never persistent without permission.** Zero character state
   (VP, wounds, action dice, adventure state, conviction, precepts pool,
   banked bonuses) writes to the DB unless the viewer has edit access.
   This includes side effects of rolls — e.g. rolling initiative
   normally clears old action dice and resets per-round abilities; for
   non-editors those changes happen in Alpine state only and reset on
   refresh. The roll itself still computes and displays normally.
3. **Always obvious.** Every roll result panel rendered for a viewer
   carries the red "read-only" banner with the appropriate message.
4. **Server is authoritative.** Every mutation endpoint must reject
   non-editors on its own, independent of client-side gating.
5. **Ally conviction + precepts-pool-as-ally follow the rolling
   character's edit gate.** These are party-wide features, so they are
   NOT gated on edit access to the priest. Instead they are gated on
   edit access to the character the viewer is rolling from: if the
   viewer can edit that character and it shares a gaming group with the
   priest, the spend persists to the priest. If the viewer cannot edit
   the rolling character, the spend is local-only with the banner —
   same treatment as VP and wounds. See Phase 7.
6. **Hide controls that would no-op for non-editors.** Anything that
   isn't a roll and would only short-circuit through the save shim
   (e.g. "Reset Per-Adventure", admin/GM controls, the Edit button
   itself) should be hidden for viewers, not shimmed. Don't render
   what doesn't do anything.

## Current-state audit (summary)

- `GET /characters/{id}` renders the sheet for anyone unless the char is
  a hidden draft → `viewer_can_edit` is already in the template context
  (`False` for anon + non-editors).
- The sheet's `save()` method POSTs the full mutable state blob to
  `POST /characters/{id}/track` (combat wounds, VP, action_dice,
  adventure_state, precepts_pool). `/track` already 403s non-editors.
- `POST /characters/{id}/ally-conviction` and
  `POST /characters/{id}/precepts-pool` are **gaming-group-gated**
  today. Phase 7 tightens them: the caller must also have edit access
  to a character in the priest's gaming group (i.e. the rolling
  character). Bare group membership is no longer sufficient; without
  edit access the spend is local-only via the Phase 1 shim.
- Many roll sub-UIs in `sheet.html` appear to be gated on
  `viewer_can_edit` today → those buttons don't render for viewers.
  Phase work will flip those to "render, call save() through the
  read-only shim".
- `GET /auth/login` does not support `return_to`; it always redirects
  home. Phase 1 adds that.

## Phase plan

Each phase is independently deployable and testable. Phases 2-7 each
introduce tests in their feature area; Phase 8 runs the full suite.

### Phase 1 — Infrastructure (no behavior change yet)

- **Backend**
  - [x] Add `?return_to=` support to `/auth/login` and `/auth/callback`
    (session cookie or query-passthrough; reject non-same-origin).
  - [x] Pass `viewer_is_logged_in`, `owner_display_name`, and
    `login_url_for_return_to_sheet` into the sheet template context.
    (`viewer_can_edit` already exists.)
- **Frontend**
  - [x] Add Alpine state on the sheet's top-level component: `canEdit`,
    `isLoggedIn`, `ownerName`, `loginUrl`.
  - [x] Build a reusable banner partial
    (`app/templates/character/partials/read_only_roll_banner.html`)
    that takes the three state flags and emits one of:
    - "You are not logged in, so void points and other effects of this
      roll do not affect character stats. If you are **{{ owner_name
      }}**, [please log in]({{ login_url }})."
    - "You don't have edit access to this character, so void points and
      other effects of this roll do not affect character stats."
  - [x] Include the partial on every roll-result panel on the sheet (attack,
    damage, parry, wound check, skill roll, iaijutsu strike/focus,
    precepts draw, conviction consume, lucky reroll). Hidden when
    `canEdit` is true.
- **Shim**
  - [x] Introduce a `save()` wrapper that short-circuits to
    `Promise.resolve()` when `!canEdit`. No behavior change for editors.
- **Tests**
  - [x] Unit: `/auth/login?return_to=/characters/42` round-trips correctly.
  - [x] Unit: sheet template renders `viewer_is_logged_in` + banner markup
    when appropriate.
  - [x] Clicktest: anon visitor loads a published sheet, the banner partial
    is present in the DOM (hidden until a roll triggers it — can assert
    element exists with `x-show` attribute).

### Phase 2 — Action dice (initiative + spend + clear)

- **Frontend**
  - [x] Un-gate Roll Initiative, Spend Die, Clear Action Dice, and any
    per-die spend controls (double-attack, feint) so they render for
    viewers.
  - [x] All dice-state mutations (roll, spend, clear) update local Alpine
    state and skip `save()` via the Phase 1 shim.
  - [x] Attack modal and initiative result panel render the read-only
    banner when `!canEdit`.
- **Server**
  - [x] `/track` already 403s. Add a test that confirms it does for the
    action_dice field specifically (currently tested indirectly).
- **Tests**
  - [x] Clicktest (new): anon rolls initiative → dice show → banner shows
    → refresh → dice are gone, original state unchanged.
  - [x] Clicktest (new): anon spends a die (double attack) → die marked
    spent locally → refresh → not spent.
  - [-] Clicktest (update): existing `rolls`-mark tests that assume
    `canEdit=True` may need parametrization or a separate file.
    (No update needed - existing `rolls` tests all run under the `page`
    admin fixture so `canEdit=True` holds; non-editor coverage lives in
    `test_readonly_rolls.py` per option (1) above.)

### Phase 3 — Void points (regular + temp)

- [x] Un-gate VP +/- and "spend N void on this roll" controls. (The
  in-modal "spend N void" selectors and the rollMenu void options were
  already not Jinja-gated; this reduced to removing the 4 tracking-panel
  `{% if viewer_can_edit %}` blocks around the VP and Temp VP +/-.)
- [x] Locally apply the VP delta during roll computation; do not persist.
  (Inherited from the Phase 1 save shim: `deductVoidPoints` mutates
  `_trackingBridge.voidPoints` and calls `t.save()`, which no-ops for
  non-editors.)
- [x] Includes temp VP (Mantis Wave-Treader Worldliness). (The temp-void
  row is gated on `has_temp_void`, a template flag based on
  `SCHOOLS_WITH_TEMP_VOID` - includes any school whose techniques mention
  "temporary void" or whose knacks include feint. `akodo_bushi` -> has
  feint -> has_temp_void=True, so the default test character already
  exercises this path.)
- **Tests:**
  - [x] Non-editor viewer spends 2 VP on a skill roll, banner shows,
    VP unchanged after refresh.
  - [x] Repeat for temp VP.

### Phase 4 — Wound checks + wounds

- [x] Un-gate wound check buttons, "Take 1 Serious" / "Keep Light",
  post-roll VP spend on WC, "Accept Result" applies wound check
  failure. (The modal-internal buttons - Take 1 Serious, Keep Light
  Wounds, Spend VP (+5), Accept Result - were already not Jinja-gated;
  this reduced to removing the tracking-panel WC button gate, LW +/-
  gates, LW minus-dropdown + set-modal + plus-modal block gate, and
  SW +/- gates.)
- [x] Local-only: LW/SW counters mutate in Alpine, never POSTed, banner
  shown on each WC result. (Inherited from the Phase 1 save shim; the
  banner is already placed inside the WC modal via Phase 2.)
- **Tests:**
  - [x] Non-editor rolls WC, takes serious, wounds mutate locally;
    refresh resets. Banner present.

### Phase 5 — Per-adventure consumables

Covers every `adventure_state` key exercisable from a roll. Treatment
for each: un-gate the buttons, local-only state, banner. **No** reset
per-adventure button for non-editors — it's not a roll.

- [x] Lucky / Unlucky (reroll) - un-gated via the per-adventure toggle
  row (setToggle -> save shim).
- [x] Akodo banked bonus (consume / undo) - the banked-bonus UI in the
  tracking panel was never Jinja-gated; its Mark spent button routes
  through saveBankedBonuses -> save shim. Direct clicktest deferred
  because the UI only renders at 3rd Dan+; transitively covered by the
  Lucky setToggle test (same save shim).
- [x] Mantis 2nd Dan free-raise usage - turns out this is a passive
  damage bonus baked into the roll formula, not a per-adventure
  consumable with its own UI. No un-gating needed.
- [x] Priest's own conviction spend (not ally) - the in-modal Spend
  Conviction (+1) buttons were already not Jinja-gated; they call
  spendConviction -> setCount('conviction', ...) -> save shim.
- [x] Adventure raises used - the per-adventure counter row's +/- were
  un-gated along with Lucky; they route through setCount -> save shim.
- [x] Reset Per-Adventure Abilities button stays editor-only per
  Principle 6; the per-ability (per_day) Reset buttons are un-gated
  since they're useful for local bookkeeping.
- **Tests:**
  - [x] Non-editor flips the Lucky toggle, refresh restores unused
    state. Representative for all per-adventure setToggle/setCount
    consumables (Lucky, Unlucky, adventure_raises, conviction, etc.)
    since they share the Phase 1 save shim path.
  - [x] The bulk Reset Per-Adventure Abilities button is absent from
    the non-editor DOM (Principle 6 regression).
  - [-] Per-consumable clicktests (Akodo banked, Mantis 2nd Dan,
    Priest conviction, adventure raises) - transitively covered by the
    Lucky test + the Phase 1 save shim contract; adding five
    mechanically-identical tests is redundant.

### Phase 6 — Priest precepts pool (own priest)

For the priest's OWN viewer (non-editor, logged in or not):

- [x] Un-gate "add pool die to this roll" UI. (The precepts_pool_block
  macro that renders inside roll modals was never Jinja-gated; un-gated
  the tracking-panel Clear + Generate dice pool buttons.)
- [x] Draw locally — pool count unchanged in DB. (Inherited from Phase
  1 save shim: rollPreceptsPool / clearPreceptsPool call this.save()
  which no-ops for non-editors. In-modal self-swap uses t.save() via
  the same shim.)
- [x] Banner shown on the affected roll result. (Phase 2 per-modal
  banner placement covers attack / wound check / freeform / duel
  modals where pool swaps happen.)
- **Tests:**
  - [x] Non-editor generates the priest's own dice pool: pool populates
    locally, refresh restores the empty server-side pool.
    Representative for the Phase 6 un-gating. The pool-die swap flow in
    roll modals shares the same save shim (self-swap: t.save()), so
    the dedicated "uses 2 pool dice on an attack" test is transitively
    covered without needing a full seeded-pool + attack-modal
    staging harness.

### Phase 7 — Gaming-group interactions (cross-character)

The gate for spending a priest's resources (ally conviction, priest's
pool consumed by an ally) is the edit gate on the **rolling**
character, not the priest. If the viewer has edit access to the
character they're rolling from, and that character shares a gaming
group with the priest, the server-side mutation persists and depletes
the priest's resource. If they don't have edit access to the rolling
character, the spend is local-only + banner, exactly like VP and
wound state — they can burn the priest's notional 17 pool across 100
test rolls with no real effect.

- **Backend**
  - [x] Tighten `POST /characters/{id}/ally-conviction` and
    `POST /characters/{id}/precepts-pool` to require that the caller
    has edit access to a character in the target priest's gaming group.
    Return 403 otherwise. Bare group membership is no longer enough.
  - [x] Accept the rolling character's ID on the request so the server
    can verify both "this rolling char shares a group with the priest"
    and "caller has edit access on the rolling char". Implemented as
    `_check_rolling_char_can_edit_for_priest_spend` helper in
    `app/routes/characters.py`; 400 if missing, 403 if not in group or
    caller cannot edit. The `/precepts-pool` endpoint keeps its
    owner-as-caller fast path (priest self-save via this endpoint
    instead of /track).
- **Frontend**
  - [x] When `!canEdit` on the rolling character, route "spend ally
    conviction" and "spend priest pool" through the Phase 1 save shim
    so the priest's resource never depletes. Apply the banner to the
    affected roll result. Implemented as an early-return in
    `_postPriestAllyDelta` and `_postPreceptsPoolReplace` keyed on
    `window._trackingBridge.canEdit`.
  - [x] When `canEdit` on the rolling character, behavior is unchanged
    (real depletion via the tightened endpoints above) — including the
    case where the viewer has edit on their own character but NOT on
    the priest. Confirmed via the
    `test_allows_non_owner_editor_of_rolling_char` unit regressions on
    both endpoints.
- **Tests**
  - [x] Unit: `/ally-conviction` 403s for a caller who is in the
    priest's gaming group but has no edit access to any character in
    that group (regression of tightened auth) ->
    `TestPriestAllyConviction::test_rejects_rolling_char_caller_cannot_edit`.
  - [x] Unit: `/precepts-pool` same regression ->
    `TestPriestPreceptsPoolEndpoint::test_rejects_non_editor_viewer_of_rolling_char`.
  - [x] Unit: both endpoints still succeed when the caller has edit
    access to a party-mate character but NOT to the priest ->
    `test_allows_non_owner_editor_of_rolling_char` on both endpoints.
  - [x] Clicktest: non-editor viewer of their own character spends ally
    conviction on an attack → banner shown, priest's
    `conviction_used` unchanged on refresh ->
    `test_readonly_rolls.py::test_non_editor_ally_conviction_no_persist`.
  - [-] Clicktest: non-editor burns 5 priest-pool dice on an attack,
    banner shown, priest pool count unchanged on refresh. Transitively
    covered - the self-swap path (`t.save()`) is the Phase 1 shim
    already tested in Phase 6; the ally-swap path
    (`_postPreceptsPoolReplace`) is covered by the backend unit tests
    plus its early-return on !canEdit (same pattern as
    `_postPriestAllyDelta` which has full clicktest coverage above).
  - [-] Clicktest (regression): editor of a party-mate character (not
    the priest) spends ally conviction → priest's `conviction_used`
    actually increments on refresh. Covered at the unit layer by
    `test_ally_can_spend_priest_conviction` (admin owns the ally,
    passes rolling_character_id=ally_id, and priest
    conviction_used increments to 1).

### Phase 8 — Full regression

- [x] Run full `pytest tests/e2e/ --browser chromium` once. Result:
  942 passed, 3 skipped, 2 xpassed, 3 failed in 48:51. Of the three
  failures:
  1. `test_permissions.py::test_tracking_buttons_hidden_for_nonadmin`
     asserted the pre-Phase-2 invariant (tracking +/- buttons hidden
     for non-editors). Rewritten in place as
     `test_tracking_buttons_local_only_for_nonadmin` - asserts the new
     contract (buttons render, banner partial in DOM, `canEdit=false`
     on trackingData, /track backend 403 still enforced by the sibling
     test).
  2. `test_readonly_rolls.py::test_non_editor_ally_conviction_no_persist`
     flaked under full-suite load because it picked
     `priest-conviction-allies[0]` and the session-scoped live-server
     DB carried stale Dan-5 priests in Tuesday Group from earlier
     tests. Hardened to find our priest by name.
  3. `test_responsive.py::test_sheet_no_horizontal_overflow_across_widths`
     fails on the Stipend tooltip at tablet width (768px) - the
     `w-64` absolute tooltip overflows by ~25px. Bisected to commit
     `fbf000c` ("tweaks based on Craig's feedback") which predates the
     Phase 1 work; pre-existing regression, out of scope for this
     plan.
- [x] Update `COVERAGE.md` (new section + mark updates). Done
  incrementally per phase; the final file has a Read-only Roll Mode
  section with subsections for Phases 1-7 plus the new `readonly_rolls`
  pytest mark (added in Phase 1).

Deploy to Fly only when Eli explicitly asks. Same rule for any
intermediate phase — do not deploy at phase boundaries.

## COVERAGE.md plan

### New section to add

```
## Read-only Roll Mode (sheet.html for viewers)

- [x] Banner: anon visitor sees "you are not logged in, ... <name>, log in" → test_readonly_rolls.py::test_anon_sees_login_banner
- [x] Banner: logged-in non-editor sees "you don't have edit access" → test_readonly_rolls.py::test_non_editor_sees_no_edit_banner
- [x] Banner "log in" link carries return_to pointing at the current sheet → test_readonly_rolls.py::test_login_link_returns_to_sheet
- [x] Anon roll initiative: dice render, banner shown, refresh clears → test_readonly_rolls.py::test_anon_initiative_no_persist
- [x] Anon spend action die: marked spent locally, refresh unspent → test_readonly_rolls.py::test_anon_spend_action_die_no_persist
- [x] Non-editor spend VP on skill roll: banner shown, VP unchanged on refresh → test_readonly_rolls.py::test_non_editor_vp_spend_no_persist
- [x] Non-editor wound check take serious: LW/SW mutate locally, reset on refresh → test_readonly_rolls.py::test_non_editor_wc_take_serious_no_persist
- [x] Non-editor lucky reroll: reroll works, lucky_used unchanged on refresh → test_readonly_rolls.py::test_non_editor_lucky_no_persist
- [x] Non-editor own-conviction spend: applied locally, conviction_used unchanged → test_readonly_rolls.py::test_non_editor_conviction_no_persist
- [x] Non-editor priest pool draw: dice in roll, pool unchanged on refresh → test_readonly_rolls.py::test_non_editor_pool_no_persist
- [x] Reset Per-Adventure button hidden for non-editors → test_readonly_rolls.py::test_reset_adventure_hidden_for_non_editor
- [x] /track POST returns 403 for non-editor (regression) → tests/test_routes.py::test_track_rejects_non_editor
- [x] /track POST returns 401 for anon (regression) → tests/test_routes.py::test_track_rejects_anon
```

### New pytest mark

- `readonly_rolls` in `pytest.ini`, covers `test_readonly_rolls.py`.

### Existing mark rows to revisit

Several `rolls`-marked clicktests today assume the viewer has edit
access. We have two options, neither of which changes those tests'
coverage of the editor path:

1. Leave the existing tests unchanged (editor-only) and add the new
   non-editor tests in `test_readonly_rolls.py`. Favor this.
2. Parametrize some existing tests across editor + non-editor. Riskier
   for flakiness, not necessary for coverage.

## Test strategy details

### Fixtures

- Re-use `page` (admin editor), `page_nonadmin` (non-editor logged in),
  `page_anon` (anonymous) already in `tests/e2e/conftest.py`.
- Seed a published, non-hidden character owned by the admin so both
  `page_nonadmin` and `page_anon` can view the sheet.

### Shared helpers

- `tests/e2e/helpers.py`: add `load_sheet_as(page, char_id)` that
  navigates and waits for the Alpine root.
- A polling helper `assert_readonly_banner_visible(page)` that waits
  for `[data-testid="readonly-roll-banner"]` after a roll result.

### Regression coverage

After each phase's clicktests, run the owning feature area's existing
mark (`-m tracking`, `-m rolls`, etc.) to confirm the editor path
still works.

