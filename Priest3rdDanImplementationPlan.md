# Priest 3rd Dan: Precepts Dice Pool - Implementation Plan

## Rules text

From `app/game_data.py` Priest school, 3rd Dan technique:

> Roll X dice at the beginning of combat, where X is equal to your precepts skill. You may swap any of these dice for any rolled die on any attack, parry, wound check, or damage roll. You may swap any of these dice for any lower die on any of those types of rolls made by any ally.

## Design decisions (resolved)

1. **Pool creation formula:** X dice rolled, all kept, 10s reroll on. X = `skills.precepts` rank.
2. **Qualifying rolls:** attack (all attack variants including feint, lunge, counterattack, double_attack, athletics:attack, and iaijutsu used as a normal attack roll) + parry (regular and athletics:parry) + damage + wound_check. **Iaijutsu DUEL rolls are excluded** - only iaijutsu used as an ordinary attack roll (e.g. Kakita's combat iaijutsu) qualifies.
3. **Swap eligibility:** `pool_die.value > rolled_die.value` strictly. Equal-value swaps are disallowed for both self and allies (disallowed because the swap would be a no-op).
4. **Dan drop:** when the priest's lowest school-knack rank drops below 3, `precepts_pool` is wiped server-side.
5. **Priest's own view:** priest sees their pool exactly once, via their own Alpine `preceptsPool` state. `priest_precepts_allies` excludes self to avoid duplicate rendering and racing mutation paths.
6. **Rolled dice, not kept dice.** The swap targets any rolled die (kept OR unkept). After substitution, the kept set is recomputed by taking the top-N values (N = `formula.kept`). Dropdown labels say "Swap with a rolled 6", not "kept 6". Dedup across rolled-dice values still applies.
7. **Pool persistence:** stored on `Character.precepts_pool`. NOT cleared at combat end. IS cleared by the per-adventure reset modal.

## Architecture summary

The feature is structurally "conviction 2.0": same party-broadcast pattern as the Priest 5th Dan ally-conviction feature, but the shared resource is a list of dice values instead of a scalar counter, and the UX is per-die swap dropdowns instead of +1 buttons.

**Reuse, do not reinvent:**
- Party-priest data propagation (context lists `priest_conviction_allies` / `party_priests`, JSON script tags, Alpine state `priestAllies`).
- Cross-character POST pattern (see `POST /characters/{priest_id}/ally-conviction` in `app/routes/characters.py`; gated by gaming-group membership).
- Per-adventure reset modal wipe pattern.
- Action-dice SVG rendering and per-die dropdown menu pattern.
- Roll-modal bonus-source breakdown display.

## Phase sequencing and dependencies

```
Phase 0 (schema + priest-only pool)    standalone, committable first
  |
  +-- Phase 1 (per-adventure reset)    depends on Phase 0
  |
  +-- Phase 2 (party broadcast)        depends on Phase 0
  |     |
  |     +-- Phase 3 (swap endpoint)    depends on Phase 0 and Phase 2
  |     |
  |     +-- Phase 4 (display on rolls) depends on Phase 0 and Phase 2
  |           |
  |           +-- Phase 5 (swap UI)    depends on Phase 3 and Phase 4
  |
  +-- Phase 6 (hygiene)                depends on everything
```

Each phase is independently committable, testable, and deployable.

---

## Phase 0 - Pool storage + priest-only create/clear UI

**Goal:** A 3rd-Dan+ priest can roll and clear their pool on their own sheet. The pool persists across reloads and across combat resets. No swap UI, no party broadcast.

### Step 0.1 - Add `precepts_pool` column

**Files:**
- `app/models.py` - add `precepts_pool: Mapped[Optional[list]] = mapped_column(JSON, default=list)` to `Character`. Shape: `[{"value": int 1..10}, ...]`. Include in `to_dict()` defaults.
- `app/database.py` - add `("precepts_pool", "TEXT", "'[]'")` to the `needed` list in `_migrate_add_columns`. The ADD COLUMN branch gets `# pragma: no cover` per existing policy.

### Step 0.2 - `/track` accepts and sanitizes pool

**Files:**
- `app/routes/characters.py` - extend `track_state`:
  ```
  if "precepts_pool" in body: character.precepts_pool = _sanitize_precepts_pool(body["precepts_pool"])
  ```
- Add `_sanitize_precepts_pool(raw)`: mirror `_sanitize_action_dice`; each entry must be `{"value": int clamped 1..10}`; drop malformed entries; cap list length at 10 (max reasonable precepts rank).

### Step 0.3 - Server context flags + Alpine state

**Files:**
- `app/routes/pages.py` - add to `school_abilities` dict:
  ```
  "priest_precepts_pool": character.school == "priest" and dan >= 3,
  "priest_precepts_pool_size": (char_dict.get("skills") or {}).get("precepts", 0)
                               if (character.school == "priest" and dan >= 3) else 0,
  ```
  And pass `precepts_pool=(character.precepts_pool or [])` into the TemplateResponse context.
- `app/templates/character/sheet.html` - in the Alpine `x-data` object that carries `actionDice`, add:
  ```
  preceptsPool: {{ (precepts_pool or []) | tojson }},
  ```
  And extend the body of the `save()` method to include `precepts_pool: this.preceptsPool`.

### Step 0.4 - Pool creation button + Clear

**Files:** `app/templates/character/sheet.html`

- Placement: new section adjacent to the action-dice section, `data-testid="precepts-pool-section"`, visible only when `x-show="schoolAbilities.priest_precepts_pool"`.
- Contents:
  - Heading: "Precepts Pool" with a subtitle showing `schoolAbilities.priest_precepts_pool_size` (the target count).
  - When `preceptsPool.length === 0`: "Roll Pool" button (`data-action="roll-precepts-pool"`), disabled if not `viewer_can_edit` or if precepts rank is 0.
  - When `preceptsPool.length > 0`: render each die as an SVG dice icon (reuse the action-die kite path + `.die` class), NOT in `spent` state. Each die gets `data-testid="precepts-pool-die"`.
  - Clear button (`data-action="clear-precepts-pool"`), visible only when `preceptsPool.length > 0`.
  - Animation tray `id="dice-animation-precepts"` for the roll animation.
- New Alpine methods on the same component that owns `setActionDice` / `clearActionDice`:
  - `async rollPreceptsPool()`: reads `n = this.schoolAbilities.priest_precepts_pool_size`; calls `window.L7RDice.rollAndAnimate(n, true, ...)` (`true` = reroll-10s on); maps resulting dice to `[{value}, ...]`; assigns to `this.preceptsPool`; calls `this.save()`.
  - `clearPreceptsPool()`: `this.preceptsPool = []; this.save();`.
- **Critical invariant:** `clearActionDice()` and the initiative roll flow must NOT touch `preceptsPool`. Review those paths during implementation.

### Phase 0 tests

**Unit (`tests/test_routes.py`):**
- `TestPrecepstsPoolTrack` class:
  - Owner can save pool via `/track`.
  - Non-editor gets 403 (or whatever `/track` uses for unauthorized).
  - Malformed entries are dropped.
  - Values are clamped to 1..10.
  - List is truncated at 10.
- `TestPriestPreceptsPoolContext` class:
  - Priest at dan=3 with precepts rank 4: `school_abilities["priest_precepts_pool"]` is True, `...pool_size` is 4.
  - Priest at dan=2: flag False, size 0.
  - Non-priest: flag False, size 0.
  - Sheet page HTML contains the `precepts_pool` JSON serialization on the Alpine data object.

**Unit (`tests/test_models.py` or wherever `to_dict` is covered):**
- A fresh character's `to_dict()["precepts_pool"]` is `[]`.

**Clicktest (`tests/e2e/test_school_abilities.py`, mark `schools`):**
- `test_priest_3rd_dan_pool_button_visible_only_for_priest_3rd_dan`
- `test_priest_3rd_dan_roll_creates_pool_of_size_equal_to_precepts`
- `test_priest_3rd_dan_clear_button_empties_pool`
- `test_priest_3rd_dan_pool_persists_across_reload`
- `test_priest_3rd_dan_pool_not_cleared_by_action_dice_clear`
- `test_priest_3rd_dan_pool_not_cleared_by_initiative_roll`

### Phase 0 COVERAGE.md additions

New subsection in `tests/e2e/COVERAGE.md` under the Priest block (create if missing):

```
### Priest 3rd Dan - Precepts Dice Pool

- [x] "Roll Pool" button visible only for priests at 3rd Dan or higher ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_button_visible_only_for_priest_3rd_dan`
- [x] Rolling creates a pool of size equal to precepts skill rank ->
      `test_school_abilities.py::test_priest_3rd_dan_roll_creates_pool_of_size_equal_to_precepts`
- [x] Clear button empties the pool ->
      `test_school_abilities.py::test_priest_3rd_dan_clear_button_empties_pool`
- [x] Pool persists across page reload ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_persists_across_reload`
- [x] Action-dice Clear does NOT wipe the precepts pool ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_not_cleared_by_action_dice_clear`
- [x] Initiative roll does NOT wipe the precepts pool ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_not_cleared_by_initiative_roll`
```

---

## Phase 1 - Per-adventure reset wipes the pool

### Step 1.1 - Reset wipe + confirm-modal listing

**Files:** `app/templates/character/sheet.html`

- Extend `resetAdventure()`: after `this.actionDice = [];`, add `this.preceptsPool = [];`.
- Extend `resetSummaryItems()`: when `this.preceptsPool.length > 0`, push a summary entry like `'Clear precepts pool (' + this.preceptsPool.length + ' dice)'`.

### Phase 1 tests

**Clicktest (`tests/e2e/test_school_abilities.py`, mark `schools` or `tracking`):**
- `test_priest_3rd_dan_adventure_reset_clears_pool`
- `test_priest_3rd_dan_reset_modal_lists_pool_clear`

### Phase 1 COVERAGE.md additions

```
- [x] Per-adventure reset wipes the precepts pool ->
      `test_school_abilities.py::test_priest_3rd_dan_adventure_reset_clears_pool`
- [x] Reset confirm modal lists the precepts pool among cleared items ->
      `test_school_abilities.py::test_priest_3rd_dan_reset_modal_lists_pool_clear`
```

---

## Phase 2 - Party broadcast context

**Goal:** allies in the priest's gaming group receive `priest_precepts_allies` on their own sheets, so the pool can be rendered in their roll modals.

### Step 2.1 - `priest_precepts_allies` context

**Files:** `app/routes/pages.py`

- Next to the existing `priest_conviction_allies` loop, build:
  ```
  priest_precepts_allies = []
  for p in party_chars:
      if p.id == character.id:
          continue                 # self handled via preceptsPool directly
      if p.school != "priest":
          continue
      p_dan = compute_dan(p.knacks or {})
      if p_dan < 3:
          continue
      pool = list(p.precepts_pool or [])
      if not pool:
          continue
      priest_precepts_allies.append({
          "priest_id": p.id, "name": p.name, "pool": pool,
      })
  ```
- Include in TemplateResponse context.
- Reuse whatever filtering `party_chars` already applies (hidden-draft visibility is already handled there by the 5th Dan loop).

**Files:** `app/templates/character/sheet.html`
- Add `<script type="application/json" id="priest-precepts-allies">{{ priest_precepts_allies | tojson }}</script>` near the existing priest JSON blocks.
- Alpine state: `priestPreceptsAllies: []`; parse in `init()` the same way `priestAllies` is parsed.

### Step 2.2 - Wipe pool on dan drop (server-side)

**Files:** `app/services/versions.py` (or wherever the apply-changes publish path lives)

- In `publish_character` (or equivalent): after applying changes, compute the new lowest school-knack rank. If `character.school == "priest"` and new dan < 3, set `character.precepts_pool = []`.
- Alternative location: `/track` handler - reject non-empty pool writes when dan < 3 by forcing to `[]`. The `publish_character` path is authoritative for knack changes so that's the right spot, but defensive normalization in `/track` also belongs.
- Decision tree for where the wipe lives: pick one primary (publish_character) and add a defensive guard in `/track` so an ally who's held a stale pool reference can't revive it.

### Phase 2 tests

**Unit (`tests/test_routes.py`):**
- `TestPriestPreceptsAlliesContext`:
  - Priest with non-empty pool in same group -> ally's context includes `{priest_id, name, pool}`.
  - Priest at dan=2 -> not included.
  - Priest at dan=3 with empty pool -> not included.
  - Priest in different gaming group -> not included.
  - Self (priest viewing own sheet) -> not included in ally list.

**Unit (`tests/test_versions.py` or publish tests):**
- Priest at dan=3 with a pool, then applying a change that drops school knack below 3: the pool is wiped as part of publish.

**Clicktest:** deferred to Phase 4 (display) - isolated context test here would be pure DOM inspection and is covered adequately by unit tests.

### Phase 2 COVERAGE.md additions

No new clicktest entries in Phase 2 (all covered by unit tests + Phase 4 display tests).

---

## Phase 3 - Swap endpoint

**Goal:** a cross-character endpoint lets an ally's browser commit a post-swap pool back to the priest's `Character.precepts_pool`.

### Step 3.1 - `POST /characters/{priest_id}/precepts-pool`

**Files:** `app/routes/characters.py`

- Sibling to `ally_conviction`. Signature:
  ```
  POST /characters/{priest_id}/precepts-pool
  Body: {"pool": [{"value": int}, ...]}
  Response: {"pool": [...normalized pool...]}
  ```
- **Validation:**
  - 401 if no authenticated user.
  - 404 if priest not found.
  - 400 if `priest.school != "priest"`.
  - 400 if priest dan < 3.
  - 403 if caller is not in the priest's gaming group (mirror `ally_conviction` permission).
  - 400 if body shape is wrong (missing `pool` key).
- Pool is sanitized via `_sanitize_precepts_pool` (same helper from Phase 0) then written to `priest.precepts_pool`, commit.
- **Model:** replace-whole-pool (not per-index mutation). Cleaner than a swap-index endpoint because concurrent allies racing would still produce a valid pool state; last-write-wins is acceptable at single-session scale.
- Caller may be the priest themselves editing their own pool via this endpoint (Phase 5's swap handler doesn't distinguish; the priest's own swaps route through `/track` via `save()` for simplicity). The endpoint should accept owner-as-caller too and behave identically.

### Phase 3 tests

**Unit (`tests/test_routes.py`) - `TestPriestPreceptsPoolEndpoint`:**
- Unauthenticated -> 401.
- Priest not found -> 404.
- Target not a priest -> 400.
- Target priest at dan=2 -> 400.
- Caller not in gaming group -> 403.
- Malformed body (missing `pool`) -> 400.
- Happy path: new pool replaces old, response includes sanitized pool.
- Malformed entries in body are dropped (no error, just sanitized).
- List over length 10 is truncated.

### Phase 3 COVERAGE.md additions

No clicktest-level COVERAGE entries needed (endpoint behavior is pure server-side; clicktests in Phase 5 exercise the full flow including this endpoint).

---

## Phase 4 - Display pool on qualifying roll modals

**Goal:** when the priest OR an ally makes a qualifying roll, the priest's pool renders in the discretionary-bonus area of the roll modal, labeled with the priest's name. No swap interaction yet.

### Step 4.1 - Identify qualifying roll predicate

**Investigation (first):** read `app/services/dice.py` to identify exactly how iaijutsu duel vs combat iaijutsu is distinguished. Candidates:
- `formula.iaijutsu_duel` flag, or
- `attack_variant == "iaijutsu_duel"`, or
- A separate key like `iaijutsu_duel` built by `build_iaijutsu_formula` vs a normal `attack` key that tags iaijutsu.

Confirm this before writing the predicate.

**Client-side helper (Alpine):** add `_isPreceptsPoolRoll()` returning true when ANY of:
- `formula?.is_attack_type === true` (covers attack, double_attack, counterattack, lunge, athletics:attack, feint, iaijutsu-as-attack)
- `atkFormula?.is_attack_type === true` (same check, attack modal context)
- roll key is `parry` or `athletics:parry` (including predeclared-parry variant, which shares the `parry` key)
- roll key is `wound_check`
- the damage-result panel is open (`atkPhase === 'damage-result'`)

AND NOT (iaijutsu duel flag).

### Step 4.2 - Render pool block in each qualifying modal

**Files:** `app/templates/character/sheet.html`

Four result panels must add a new bonus-area block:
- Generic roll modal (parry, athletics:parry, wound_check)
- Attack modal (attack, variants)
- Damage section of attack modal
- Wound check modal (already generic, but has its own discretionary-bonus list that needs updating)

Block template:
```
<template x-for="priest in preceptsPoolAlliesForThisRoll()" :key="'pp-' + priest.priest_id">
    <div class="bg-parchment rounded p-3 text-sm" x-show="priest.pool.length > 0"
         :data-testid="'precepts-pool-in-roll-' + priest.priest_id">
        <div class="text-xs font-medium mb-1">
            <span x-text="priest.isSelf ? 'Your Precepts Pool' : priest.name + \"'s Precepts Pool\""></span>
        </div>
        <div class="flex flex-wrap gap-1">
            <template x-for="(die, j) in priest.pool" :key="j">
                <!-- SVG dice icon reusing .die class; click wired in Phase 5 -->
                <button data-priest-pool-die ...>
                    ... die.value ...
                </button>
            </template>
        </div>
    </div>
</template>
```

Helper `preceptsPoolAlliesForThisRoll()`:
- If not `_isPreceptsPoolRoll()`, return `[]`.
- Start with `this.priestPreceptsAllies.filter(a => a.pool.length > 0)`.
- If this is the priest's own sheet (detected via `schoolAbilities.priest_precepts_pool` plus the pool being non-empty), prepend `{priest_id: 'self', name: 'Your', pool: this.preceptsPool, isSelf: true}`.
- Return the combined list.

**Edge case:** the wound-check modal's `wcHasDiscretionary` flag (controls the "Accept Result" button visibility) must include "has a priest precepts ally with non-empty pool OR is self with non-empty pool". Mirror the `hasPriestAlly` check already there.

### Phase 4 tests

**Unit tests (`tests/test_routes.py`):**
- Existing Phase 2 context tests already cover server-side data shape.

**Clicktest (`tests/e2e/test_school_abilities.py`, mark `schools`):**
- `test_priest_3rd_dan_pool_appears_on_priests_own_attack`
- `test_priest_3rd_dan_pool_appears_on_priests_own_wound_check`
- `test_priest_3rd_dan_pool_appears_on_priests_own_damage`
- `test_priest_3rd_dan_pool_appears_on_priests_own_parry`
- `test_priest_3rd_dan_pool_does_not_appear_on_iaijutsu_duel`
- `test_priest_3rd_dan_pool_does_not_appear_on_non_qualifying_roll` (e.g. skill roll, initiative)

**Clicktest (`tests/e2e/test_groups.py`, mark `groups`):**
- `test_ally_sees_3rd_dan_priest_pool_on_attack_roll`
- `test_ally_sees_3rd_dan_priest_pool_on_parry_roll`
- `test_ally_sees_3rd_dan_priest_pool_on_wound_check`
- `test_ally_sees_3rd_dan_priest_pool_on_damage`
- `test_priest_not_in_same_group_does_not_surface_pool_to_others`
- `test_priest_with_empty_pool_does_not_render_block`

### Phase 4 COVERAGE.md additions

```
- [x] Priest sees own precepts pool on attack roll ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_appears_on_priests_own_attack`
- [x] Priest sees own precepts pool on wound check ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_appears_on_priests_own_wound_check`
- [x] Priest sees own precepts pool on damage roll ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_appears_on_priests_own_damage`
- [x] Priest sees own precepts pool on parry roll ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_appears_on_priests_own_parry`
- [x] Pool does NOT appear on iaijutsu duel rolls ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_does_not_appear_on_iaijutsu_duel`
- [x] Pool does NOT appear on non-qualifying rolls (skill, initiative) ->
      `test_school_abilities.py::test_priest_3rd_dan_pool_does_not_appear_on_non_qualifying_roll`
- [x] Ally in same gaming group sees priest's pool on attack roll ->
      `test_groups.py::test_ally_sees_3rd_dan_priest_pool_on_attack_roll`
- [x] Ally sees priest's pool on parry roll ->
      `test_groups.py::test_ally_sees_3rd_dan_priest_pool_on_parry_roll`
- [x] Ally sees priest's pool on wound check ->
      `test_groups.py::test_ally_sees_3rd_dan_priest_pool_on_wound_check`
- [x] Ally sees priest's pool on damage roll ->
      `test_groups.py::test_ally_sees_3rd_dan_priest_pool_on_damage`
- [x] Priest NOT in the viewer's gaming group does not surface pool ->
      `test_groups.py::test_priest_not_in_same_group_does_not_surface_pool_to_others`
- [x] Priest with empty pool renders nothing in the roll modal ->
      `test_groups.py::test_priest_with_empty_pool_does_not_render_block`
```

---

## Phase 5 - Swap UI (any rolled die) + swap effect

**Goal:** clicking a pool die opens a dropdown of swappable ROLLED dice (not just kept). Executing the swap substitutes the pool die into `finalDice`, recomputes the kept set, updates totals, and persists the new pool.

### Step 5.1 - Expose rolled dice (kept AND unkept) as swap targets

**Investigation:** confirm where `finalDice` lives in Alpine state per modal. The existing roll-result panel renders kept dice prominently and unkept dice as struck-through / greyed. Phase 5 may need to add an interaction layer on unkept dice so users can see that they are also swap targets (no actual click on unkept dice except via the pool-die dropdown; the dropdown lists them by value).

### Step 5.2 - Per-pool-die dropdown menu

**Files:** `app/templates/character/sheet.html`

- State: `preceptsPoolMenuOpen` keyed by `"<priest_id>:<poolDieIndex>"`.
- `preceptsSwapOptions(priest, poolDieValue)`:
  - Reads `this._currentRolledDice()` - a new helper returning the active modal's `finalDice` array (`finalDice` for generic, attack result, wound check; damage has its own `finalDice`-like array - verify during implementation).
  - Filter: `finalDice.filter(d => d.value < poolDieValue)` (strict less-than, per decision 3; applies to both self and allies since equal swaps are a no-op).
  - Map to unique values: `Array.from(new Set(filtered.map(d => d.value))).sort((a,b) => a - b)`.
  - If empty, return a single disabled option `{disabled: true, label: 'No lower rolled dice to swap with'}`.
  - Else map to `{value, label: 'Swap with a rolled ' + v}`.

### Step 5.3 - Swap effect algorithm

Pseudo-code for `swapPreceptsDie(priest, poolIndex, rolledValue)`:

```
1. Find one rolled-die entry in finalDice with value === rolledValue
   (the first match is fine; all dice of that value are interchangeable
   in the kept-set calculation).
2. Capture its previous value and kept state.
3. Replace that entry's value with priest.pool[poolIndex].value.
   Preserve whatever "parts" structure the kept-dice renderer expects
   (if the entry had parts: [10, 4], replace with parts: [newValue]).
4. Replace priest.pool[poolIndex] with { value: <previousRolledValue> }.
5. Recompute kept set: sort finalDice descending by value, mark the top
   formula.kept as kept:true, rest as kept:false. (This handles
   promotion/demotion from the swap.)
6. Recompute keptSum = sum of values where kept.
7. Recompute active total:
   - generic roll: this.baseTotal = this.keptSum + formula.flat + ...
     (use the existing recompute path if one exists; else compute inline).
   - wound check: this.wcRollTotal = ... (use _wcUpdateMargin helper)
   - attack: this.atkRollTotal = ... then call _atkUpdateHitState()
   - damage: this.atkDamageTotal = this.keptSum + flat + bonuses;
     call _refreshAttackDieTooltip()
8. Append a structured entry to preceptsPoolSwapBonuses:
   { priestName, isSelf, rolledValueBefore, poolValueAfter }
9. Persist the new pool:
   - if priest.isSelf: this.preceptsPool = priest.pool; this.save();
   - else: this._postPreceptsPoolReplace(priest.priest_id, priest.pool)
     (fire-and-forget POST to /characters/{id}/precepts-pool; mirrors
     _postPriestAllyDelta).
10. Close the dropdown: this.preceptsPoolMenuOpen = null.
```

**Helpers needed:**
- `_currentRolledDice()`: returns the active modal's `finalDice` array. Mapping:
  - generic roll modal (`resultOpen`) -> `this.finalDice`
  - attack result (`atkPhase === 'result' | 'damage-result'`) -> verify exact array name during implementation (may be `this.atkFinalDice` or reused `this.finalDice`)
  - wound check -> `this.wcFinalDice` (or whatever wc phase uses)
- `_postPreceptsPoolReplace(priestId, pool)`: fire-and-forget POST mirroring `_postPriestAllyDelta`.

**Reset `preceptsPoolSwapBonuses = []`** at the start of every new roll. Mirror the `priestAllySpentThisRoll = {}` resets scattered through the codebase (4+ locations).

### Step 5.4 - Bonus-source breakdown rendering

**Files:** `app/templates/character/sheet.html`

Under each result-panel's bonuses list, add:

```
<template x-for="b in preceptsPoolSwapBonuses">
    <li>
        <span x-text="(b.poolValueAfter - b.rolledValueBefore >= 0 ? '+' : '') +
                     (b.poolValueAfter - b.rolledValueBefore)"></span>
        from
        <span x-text="b.isSelf ? 'your precepts pool' : b.priestName + \"'s precepts pool\""></span>
        <span class="text-ink/50 text-xs">(swapped rolled
            <span x-text="b.rolledValueBefore"></span>
            -> <span x-text="b.poolValueAfter"></span>)</span>
    </li>
</template>
```

### Step 5.5 - Reroll interaction

When any reroll path fires (Lucky, Togashi 4th Dan reroll, impaired-10s reroll), a fresh `finalDice` replaces the swapped-in state. The pool state stays committed server-side, so the swap's effect on the pool is preserved even though the reroll wipes the kept-dice modification. Document this on the reroll paths as a comment pointing to the pool-swap behavior.

### Phase 5 tests

**Clicktest (`tests/e2e/test_school_abilities.py`, mark `schools`):**

Priest self-swap flow:
- `test_priest_3rd_dan_self_swap_any_rolled_die_strictly_lower`
- `test_priest_3rd_dan_self_swap_updates_total_and_breakdown`
- `test_priest_3rd_dan_self_swap_puts_replaced_die_back_in_pool`
- `test_priest_3rd_dan_self_swap_promotes_unkept_die_into_kept_set`
- `test_priest_3rd_dan_self_swap_demotes_replaced_kept_die`
- `test_priest_3rd_dan_menu_dedupes_same_value_rolled_dice`
- `test_priest_3rd_dan_menu_shows_disabled_when_no_lower_rolled`
- `test_priest_3rd_dan_equal_value_swap_excluded_from_menu`

**Clicktest (`tests/e2e/test_groups.py`, mark `groups`):**

Ally-swap flow:
- `test_ally_swap_limited_to_strictly_lower_rolled_dice`
- `test_ally_swap_updates_ally_total_and_persists_priest_pool`
- `test_ally_swap_persisted_across_page_reload_on_both_sheets`
- `test_ally_swap_broadcasts_to_priest_endpoint`
- `test_ally_cannot_swap_equal_value_rolled_die`

### Phase 5 COVERAGE.md additions

```
- [x] Priest can self-swap any rolled die (strictly lower than pool die) ->
      `test_school_abilities.py::test_priest_3rd_dan_self_swap_any_rolled_die_strictly_lower`
- [x] Self-swap updates keptSum, total, and bonus-source breakdown ->
      `test_school_abilities.py::test_priest_3rd_dan_self_swap_updates_total_and_breakdown`
- [x] Self-swap puts the replaced die back into the pool ->
      `test_school_abilities.py::test_priest_3rd_dan_self_swap_puts_replaced_die_back_in_pool`
- [x] Self-swap can promote a previously-unkept die into the kept set ->
      `test_school_abilities.py::test_priest_3rd_dan_self_swap_promotes_unkept_die_into_kept_set`
- [x] Self-swap can demote a previously-kept die out of the kept set ->
      `test_school_abilities.py::test_priest_3rd_dan_self_swap_demotes_replaced_kept_die`
- [x] Swap menu dedupes rolled dice of the same value ->
      `test_school_abilities.py::test_priest_3rd_dan_menu_dedupes_same_value_rolled_dice`
- [x] Swap menu shows disabled "No lower rolled dice" when nothing eligible ->
      `test_school_abilities.py::test_priest_3rd_dan_menu_shows_disabled_when_no_lower_rolled`
- [x] Equal-value rolled dice are excluded from the swap menu ->
      `test_school_abilities.py::test_priest_3rd_dan_equal_value_swap_excluded_from_menu`
- [x] Ally swap is limited to rolled dice strictly lower than the pool die ->
      `test_groups.py::test_ally_swap_limited_to_strictly_lower_rolled_dice`
- [x] Ally swap updates ally's total and persists the priest's pool ->
      `test_groups.py::test_ally_swap_updates_ally_total_and_persists_priest_pool`
- [x] Ally swap persists across page reload on both sheets ->
      `test_groups.py::test_ally_swap_persisted_across_page_reload_on_both_sheets`
- [x] Ally swap fires the POST to the priest's precepts-pool endpoint ->
      `test_groups.py::test_ally_swap_broadcasts_to_priest_endpoint`
- [x] Ally cannot swap an equal-value rolled die (menu option excluded) ->
      `test_groups.py::test_ally_cannot_swap_equal_value_rolled_die`
```

---

## Phase 6 - Cross-cutting hygiene

### Step 6.1 - JS error coverage

**Files:** `tests/e2e/test_sheet_js_errors.py`

- The parametrized sheet-JS-errors test iterates a list of schools. Add a priest character with a non-empty pool at 3rd Dan so the render path is checked for console errors (null-safe Alpine expressions).

### Step 6.2 - Responsive check

**Files:** `tests/e2e/test_responsive.py`

- Add assertion: a pool of 10 dice does not cause horizontal overflow at 375px viewport width. The pool dice should wrap or scroll horizontally within their container.

### Step 6.3 - Docs

**Files:** `school-features/Priest.md`

- Move 3rd Dan from "Out of scope" to "Implemented".
- List the files touched.
- List the tests and clicktests that cover it.

### Phase 6 COVERAGE.md additions

```
- [x] Precepts pool renders without JS errors on a 3rd Dan priest sheet ->
      `test_sheet_js_errors.py::test_no_js_errors_on_sheet[priest_3rd_dan_with_pool]`
- [x] Pool of 10 dice does not overflow horizontally at phone width ->
      `test_responsive.py::test_precepts_pool_no_overflow_at_phone_width`
```

---

## Anticipated challenges and mitigations

1. **Four modals, one feature.** Generic-roll, attack, damage, and wound-check each own their own `finalDice`-style state and total fields (`baseTotal`, `wcRollTotal`, `atkRollTotal`, `atkDamageTotal`). A central `_currentRolledDice()` helper + explicit per-modal total update in `swapPreceptsDie` is mandatory to avoid per-modal branching everywhere.
2. **Rolled-dice representation asymmetry.** `finalDice` entries carry `{value, kept, parts}` where `parts` may include exploded-10s sub-values. Pool dice are flat `{value}`. When a pool die enters `finalDice`, wrap as `{value, kept: <recomputed>, parts: [value]}`. When a rolled die enters the pool, strip `parts` down to just the value (the pool is always flat).
3. **Keep-set recomputation.** After every swap, sort `finalDice` descending by value and mark top-N as kept. This must be idempotent. All qualifying rolls use "keep highest" (not initiative's "keep lowest") - verify no modal involves keep-lowest.
4. **Race conditions on cross-sheet endpoint.** Replace-whole-pool is race-safe (last write wins, no partial state). Document this on the endpoint.
5. **Rollback on failure.** `_postPreceptsPoolReplace` is best-effort. The local roll view is authoritative for the current roll; pool lag is acceptable. Mirrors the existing `_postPriestAllyDelta` pattern.
6. **Precepts rank 0.** Hide the Roll Pool button; show a helper line "You need a precepts skill rank of at least 1 to create a pool" if 3rd Dan + rank 0.
7. **Bonus-source integration.** The existing `formula.bonuses` array is computed server-side pre-roll. Pool swaps happen post-roll, so swap-derived entries live in a separate `preceptsPoolSwapBonuses` client-side list with its own `<template x-for>` block in each result panel.
8. **Iaijutsu-duel detection.** Phase 4 implementation must first identify the exact flag distinguishing iaijutsu duel rolls from combat iaijutsu. Grep candidates: `iaijutsu_duel`, `duel_strike`, `duelContestedRoll`, `attack_variant === 'iaijutsu_duel'`. Confirm before coding the predicate.
9. **Dan-drop wipe placement.** Primary wipe on `publish_character`; defensive guard in `/track` rejects pool writes from non-3rd-Dan priests (rather than accepting and leaving the column populated). Both paths tested.

---

## Minimum viable checkpoints

- **After Phase 0:** a priest can roll and clear their pool; pool survives reload and is unaffected by combat resets. Ship to prod? Yes - feature is invisible to non-priests and to allies; priests get a new UI section that does nothing but persist state.
- **After Phase 2+3:** all server-side plumbing is in place; no new UI yet. Ship? Yes - still invisible to users.
- **After Phase 4:** pool renders on qualifying rolls for self and allies but not interactive. Ship? Optional - users might wonder why it's decorative. Prefer to combine with Phase 5.
- **After Phase 5:** full feature live for self and allies. Ship.
- **After Phase 6:** hygiene polish, inline docs, full COVERAGE updates.
