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
3. **Always obvious.** Every roll result panel rendered for a viewer
   carries the red "read-only" banner with the appropriate message.
4. **Server is authoritative.** Every mutation endpoint must reject
   non-editors on its own, independent of client-side gating.
5. **Ally conviction + precepts-pool-as-ally stay gaming-group gated.**
   These are party-wide features, not owner-only. A non-editor who IS
   in the priest's gaming group is still the intended operator. See
   open question Q1.

## Current-state audit (summary)

- `GET /characters/{id}` renders the sheet for anyone unless the char is
  a hidden draft → `viewer_can_edit` is already in the template context
  (`False` for anon + non-editors).
- The sheet's `save()` method POSTs the full mutable state blob to
  `POST /characters/{id}/track` (combat wounds, VP, action_dice,
  adventure_state, precepts_pool). `/track` already 403s non-editors.
- `POST /characters/{id}/ally-conviction` and
  `POST /characters/{id}/precepts-pool` are **gaming-group-gated, not
  edit-gated** on purpose (party members consume the priest's
  resources). Leave untouched pending Q1.
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
  - Add `?return_to=` support to `/auth/login` and `/auth/callback`
    (session cookie or query-passthrough; reject non-same-origin).
  - Pass `viewer_is_logged_in`, `owner_display_name`, and
    `login_url_for_return_to_sheet` into the sheet template context.
    (`viewer_can_edit` already exists.)
- **Frontend**
  - Add Alpine state on the sheet's top-level component: `canEdit`,
    `isLoggedIn`, `ownerName`, `loginUrl`.
  - Build a reusable banner partial
    (`app/templates/character/partials/read_only_roll_banner.html`)
    that takes the three state flags and emits one of:
    - "You are not logged in, so void points and other effects of this
      roll do not affect character stats. If you are **{{ owner_name
      }}**, [please log in]({{ login_url }})."
    - "You don't have edit access to this character, so void points and
      other effects of this roll do not affect character stats."
  - Include the partial on every roll-result panel on the sheet (attack,
    damage, parry, wound check, skill roll, iaijutsu strike/focus,
    precepts draw, conviction consume, lucky reroll). Hidden when
    `canEdit` is true.
- **Shim**
  - Introduce a `save()` wrapper that short-circuits to
    `Promise.resolve()` when `!canEdit`. No behavior change for editors.
- **Tests**
  - Unit: `/auth/login?return_to=/characters/42` round-trips correctly.
  - Unit: sheet template renders `viewer_is_logged_in` + banner markup
    when appropriate.
  - Clicktest: anon visitor loads a published sheet, the banner partial
    is present in the DOM (hidden until a roll triggers it — can assert
    element exists with `x-show` attribute).

### Phase 2 — Action dice (initiative + spend + clear)

- **Frontend**
  - Un-gate Roll Initiative, Spend Die, Clear Action Dice, and any
    per-die spend controls (double-attack, feint) so they render for
    viewers.
  - All dice-state mutations (roll, spend, clear) update local Alpine
    state and skip `save()` via the Phase 1 shim.
  - Attack modal and initiative result panel render the read-only
    banner when `!canEdit`.
- **Server**
  - `/track` already 403s. Add a test that confirms it does for the
    action_dice field specifically (currently tested indirectly).
- **Tests**
  - Clicktest (new): anon rolls initiative → dice show → banner shows
    → refresh → dice are gone, original state unchanged.
  - Clicktest (new): anon spends a die (double attack) → die marked
    spent locally → refresh → not spent.
  - Clicktest (update): existing `rolls`-mark tests that assume
    `canEdit=True` may need parametrization or a separate file.

### Phase 3 — Void points (regular + temp)

- Un-gate VP +/- and "spend N void on this roll" controls.
- Locally apply the VP delta during roll computation; do not persist.
- Includes temp VP (Mantis Wave-Treader Worldliness).
- **Tests:** non-editor viewer spends 2 VP on a skill roll, banner
  shows, VP unchanged after refresh. Repeat for temp VP.

### Phase 4 — Wound checks + wounds

- Un-gate wound check buttons, "Take 1 Serious" / "Keep Light",
  post-roll VP spend on WC, "Accept Result" applies wound check
  failure.
- Local-only: LW/SW counters mutate in Alpine, never POSTed, banner
  shown on each WC result.
- **Tests:** non-editor rolls WC, takes serious, wounds mutate locally;
  refresh resets. Banner present.

### Phase 5 — Per-adventure consumables

Covers every `adventure_state` key exercisable from a roll:

- Lucky / Unlucky (reroll) — already consumable via `adventure_state`.
- Akodo banked bonus (consume / undo).
- Mantis 2nd Dan free-raise usage.
- Priest's own conviction spend (not ally).
- Adventure raises used.

Treatment: un-gate the buttons, local-only state, banner. **No** reset
per-adventure button for non-editors — it's not a roll.

- **Tests:** one clicktest per consumable: non-editor exercises it,
  banner shown, refresh resets counter.

### Phase 6 — Priest precepts pool (own priest)

For the priest's OWN viewer (non-editor, logged in or not):

- Un-gate "add pool die to this roll" UI.
- Draw locally — pool count unchanged in DB.
- Banner shown on the affected roll result.

**Tests:** non-editor viewer uses 2 pool dice on an attack, attack
shows the dice in the breakdown, banner shown, pool unchanged on
refresh.

### Phase 7 — Gaming-group interactions (cross-character)

Pending Q1, this phase **either**:

- (a) Leaves `/ally-conviction` and cross-character precepts POSTs
  alone. Party members who aren't the priest's editor still deplete
  the priest's pool / conviction — because they're authorized by group
  membership. The banner **does not** apply to these actions.
- (b) Tightens: anyone without edit permission on the priest can use
  the priest's pool / conviction locally on their own roll but does
  not deplete the priest. Banner applies.

Assume (a) is the default. Only implement (b) if Q1 says so.

### Phase 8 — Full regression + deploy

- Run full `pytest tests/e2e/ --browser chromium` once.
- Update `COVERAGE.md` (new section + mark updates — see below).
- Deploy to Fly.

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

---

## Questions for you

**Q1 — Ally conviction / cross-character precepts pool**

`POST /ally-conviction` and `POST /precepts-pool` today authorize on
**gaming-group membership**, not edit permission, because that's the
whole point: party members consume the priest's resources during
combat. Two options:

- **(a) Keep gaming-group model.** A party member who is in the
  priest's group but NOT an editor on the priest CAN actually deplete
  the priest's pool / conviction by clicking those buttons on their
  own character's sheet. The read-only banner does NOT apply to these
  actions. (Recommended — this matches the design intent.)
- **(b) Tighten.** Only the priest's editor can truly deplete; everyone
  else uses the priest's resources locally-only with the banner.

Which do you want?

**Q2 — Anon display name in the banner**

"If you are **&lt;player name&gt;**, please log in." — use the
owner's display name (same as shown in the "Player: X" line)? If the
owner has never logged in (seeded user only), fall back to the
character's `player_name` field.

**Q3 — Login return_to for anon**

After Discord OAuth from an anon sheet view, land the user back on the
sheet they were viewing? (Any roll the anon was mid-flow gets lost —
that's fine since nothing persisted.)

**Q4 — Reset Per-Adventure button**

Confirm: hide this button entirely for non-editors, rather than
shimming it. It's not a roll; shimming provides no value.

**Q5 — Phased deploys**

Deploy at the end of each phase, or just a single deploy after Phase
8? Single deploy is simpler; phased gives the campaign early value on
the initiative fix but risks intermediate UI inconsistencies.

**Q6 — Scope check: is there any roll that should stay editor-only?**

E.g. the "Ready for next adventure" reset? Admin overrides on GM-award
modals? I'd say anything that isn't a dice roll is out of scope for
this work (those already have their own permission gates).
