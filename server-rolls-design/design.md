# Server-side Rolls and State Changes - Design

Status: **Phases 1-9 done; Phase 10 next.** Decisions S1-S7 in section 8.

## 1. Goal

The GM, 2026-09-28: *"The actions that we take that affect the system's state should happen on the
server and be the result of API calls rather than happening on the client and then having us report
what the results were."* And on dice: *"from an architectural perspective, actually making the roll
should be something that happens on the server, not the client."*

So:

- **The server rolls every die.** The browser animates the dice the server rolled.
- **Every action that changes state is a server operation**, reached through an API call: a void
  spend, a Lucky reroll, a free raise, taking a serious wound, spending an action die, banking a
  bonus. The browser sends the choice; the server applies the rules, persists, and answers with the
  result.
- **The UI stays in the browser.** The modals, their phases, animation, sounds, probability charts
  and every display-only calculation remain client-side. This is not server-rendered UI.

The Discord commands and the GM's combat tracker already work this way. They follow one pattern:
check and plan, roll, apply, record, then commit once. This project brings the character sheet onto
the same footing.

## 2. How it works today

- **Dice are generated in the browser.** `app/static/js/dice.js` (`Math.random()`) is used at about
  17 roll entry points and 12 reroll mechanics in `partials/sheet/_dice_js.html` (6,889 lines) and
  the modal templates.
- **The browser computes every result.** That includes totals, hits, damage pools, wound-check
  outcomes and about 60 post-roll interactions (raises, Conviction, banks, rerolls, temp-void grants
  and so on). The arithmetic lives in `roll_math.js`; the rest is Alpine handlers, some of them
  inline `@click` strings.
- **State is saved as a whole snapshot.** Tracking goes to `POST /characters/{id}/track` (45 call
  sites). `adventure_state` has no schema; the server stores whatever it is sent. A revision
  (`tracking_rev`) stops two writers overwriting each other, but it cannot stop a wrong value.
- **Roll history stores what the browser reports.** The server keeps the browser's payload as-is
  (POST `/rolls`, then a debounced PATCH).
- **Already operations on the server:** PCP spend and undo, Night's Rest, ally Conviction, the
  precepts pool, the money ledger, and the whole Discord / combat-tracker path.
- **The rules are already server-side.** `build_all_roll_formulas` decides what a roll is.
  `roll_engine`, `void_spend`, `tracking.start_combat_round` and `combat_math` (attack, damage and
  wound-check arithmetic) already exist on the server.
- **`discord-design/audit.md` A4/A5/B9 sketched this migration** and names the structural blocker:
  `/track` is a blob setter. Its suggested order is folded into section 6.

## 3. Principles

1. **One source of truth per rule, on the server.** When a result moves to the server, its JS copy
   is deleted, not kept in sync. `roll_math.js` shrinks to display-only helpers (probability charts,
   formatting). The shared case tables in `tests/shared/` retire with the JS they pinned.
2. **Every state change is an operation**, never a blob. Each operation is validated (is this spend
   affordable? is this bank present?), applied, and answers with the new tracking snapshot and
   revision, which the tab adopts. Operations never answer 409 (audit B9); `prefetch_body` keeps
   them atomic.
3. **Check before anything happens.** Every refusal runs before a die is rolled or a row changes,
   and each request commits once. This is the Discord / tracker rule.
4. **Rolls are server-side records.** A roll is created on the server, and every later action on it
   (a reroll, a raise, an undo) is an operation on that record. The server computes the displayed
   total; the browser no longer sends one.
5. **Read-only Roll Mode survives unchanged for the player** (Q1). A non-editor still walks every
   roll and sees every bonus. The server runs the same code in *simulate* mode and persists nothing.
6. **Incremental.** Each phase moves a group of flows end to end and deploys. The old and new paths
   coexist until the last phase retires `/track`.

## 4. Architecture

### 4.1 Roll sessions

**A new `RollSession` row per roll**, created by the server. It holds:
- the character, the viewer, and whether it is **live** or **simulated**;
- the roll key, the formula as built, the pre-roll choices;
- the dice (with their explosion chains), the kept set;
- an ordered list of the post-roll actions applied, and the current total and payload;
- the reroll lock, the undo stack, and a link to its `RollHistory` row when the roll is recorded.

`RollHistory` keeps its role and shape (the dice card, `/api/rolls`, the history page). What changes
is that it is now **written by the server from the session**, never posted by the browser. Sessions
that are not recorded (admin-not-owner, non-editors, anonymous visitors) are reaped after a few hours.

**API** (on the `characters` / `rolls` routers, with `prefetch_body`):
- `POST /characters/{id}/roll` with `{roll_key, choices}` (void, Otherworldliness, variant, TN,
  action die, the attack modal's situational inputs, and so on). It returns
  `{session_id, dice, payload, tracking, rev}`.
- `POST /characters/{id}/roll/{session_id}/act` with `{action, args}`. `action` is a closed set:
  `raise`, `undo_raise`, `conviction`, `lucky_reroll`, `pcp_reroll`, `pcp_free_raise`,
  `pcp_reroll_tens`, `merchant_reroll`, `bank`, `spend_bank`, `keep_light_wounds`,
  `take_serious_wound`, `roll_damage`, and so on. Each action is a function in a registry, with
  its own unit tests. The request returns the same shape as a roll.
- **A chained roll is a new session linked to its parent:** damage after an attack, the wound check
  after damage, the duel's strike after its contest. The parent's context (excess, variant, parry
  outcome) is read on the server, not re-sent.

### 4.2 Tracking operations

**`POST /characters/{id}/track/op` with `{op, args}`** takes a closed set of operations:
- light and serious wounds: add, set, take-serious-and-reset;
- void and temp void: spend (in draw order, with the school consequences), gain, set;
- counters and toggles, keyed by the per-adventure ability ids the server already enumerates;
- action dice: set, spend, unspend, annotate, the Kakita and Mantis special spends;
- banks: grant, spend, unspend; Mantis posture; per-day and per-adventure resets.

**It replaces the `/track` blob in stages.** The serious-wound Night's Rest cadence flags move with
the wound operations.

**`adventure_state` gets a schema**: known keys, types and bounds, validated on every write. That
turns `/track` from a setter into the rule boundary audit A5 asked for.

**The tab stops computing state.** After each operation it adopts the returned snapshot
(`adoptServerState` already exists). Optimistic display is Q2.

### 4.3 The browser

- **`dice.js` splits in two:** `animateDice(dice, ...)` plays dice it is handed; generation is
  deleted at the end.
- **The Alpine flows keep their phases**, but each "compute and mutate" becomes "call and render".
  The per-flow reroll cores converge on the one `act` endpoint.
- **Inline `@click` rules are extracted** into named functions first (audit A4), so they can be
  replaced one by one.
- **Probability charts, averages and duel charts stay client-side.** They read server-built tables
  and change nothing. `atkComputeDamage` is split: its average stays for the chart, and the real
  damage pool comes from the server.

### 4.4 Simulate mode (Read-only Roll Mode)

- **What runs:** the same functions, with a flag. The session is created, dice are rolled, actions
  apply to the session, and totals render exactly as for an editor.
- **What does not:** no tracking operation persists, and no history row is written. The response's
  `tracking` is the character's real persisted state, so the displayed counters stay anchored, which
  the current rule requires.
- **Anonymous visitors** need an unauthenticated simulate path (Q1), rate-limited like the client
  report endpoints.

### 4.5 Latency

- **Every click becomes a request.** A roll is one request; each post-roll click is one more.
- **Rough cost:** on the one Fly machine that is about 50-150 ms, well under the dice animation
  (which runs while the request is in flight).
- **Post-roll buttons are the exposed case,** raises and Conviction clicked quickly. They queue
  per session in order (the way `save()` queues today) rather than racing. See Q2.

## 5. Behavior to settle while porting

The server can only implement one version of each of these. They are inconsistencies in today's
browser code, found during the survey. Q3 asks which are GM rulings and which are plain bugs.

1. **Togashi 4th Dan reroll** runs a whole new roll. It writes a **second** history row and drops
   raises, Mirumoto points, Courtier and Akodo void bonuses already applied to the first.
2. **Hida 3rd Dan reroll** rebuilds the total from the kept dice plus flat only. It drops Shosuro,
   Conviction and ally-Conviction bonuses, and zeroes spent raises without refunding them.
3. **Post-roll void spends skip the school consequences.** Akodo 4th Dan (three places), the
   wound-check void buttons and Akodo 5th Dan reflect all bypass `deductVoidPoints`, so Ide 5th /
   Yogo 3rd / Matsu 3rd do not fire. The Merchant's post-roll spends do fire them.
4. **Mirumoto 3rd Dan round points are tab-local**, never persisted. A reload or a second tab
   refills them.
5. **Unrecorded rolls:** the Bayushi feint sub-damage, the Shiba parry sub-damage and Kakita 5th Dan
   damage never reach roll history.
6. **Character-level editors get a read-only sheet.** The sheet decides `viewer_can_edit` with
   `can_view_drafts` (owner, admin, account grant), while `/track` accepts `can_edit_character`
   (which also admits character-level editors).
7. **Some local display changes are not gated for non-editors.** Bayushi and Akodo bank spends and
   the Shinjo / Ide banks move the display (nothing persists). Simulate mode fixes this by
   construction.
8. **There are four separate damage assemblers:** `atkComputeDamage`, the duel's, Kakita 5th's (with
   a hand-inlined 10k10 cap) and the sub-damage one (computed in `@click` strings). They converge on
   `combat_math.damage_pool`.

## 6. Phases

Each phase: tests first; unit suite 100% coverage; the relevant `tests/shared` tables updated or
retired with their JS; targeted clicktests (named `-k` selections under the 100-test guard, listed per
phase); commit, push, deploy. A phase may leave old and new paths side by side; the last phase
removes the old ones.

### Phase 0 - Requirements
- [x] Inventory the roll flows, reroll mechanics, post-roll actions and state writes
- [x] Draft this document
- [x] GM answers section 8 (2026-09-28)
- [x] GM signs off

### Phase 1 - Foundations and the generic roll
- [x] `RollSession` model (+ reaping), the `roll` endpoint (the `act` endpoint arrives with the first post-roll actions, Phase 3), live vs simulated, recording
      from the session (`should_record_roll`, `skill_rank`); retry-safe `request_id`
- [x] `dice.js`: `animateDice` for server dice
- [x] `runRoll` flows through the server: skills, knacks, rings, athletics, bless, freeform, the
      Xk1 void roll; pre-roll void, Otherworldliness, Kitsune swap, Commune activation (extra flat is the predeclared parry's, Phase 6). `server_rolled` is stamped on every formula so the sheet reads it rather than keeping a list; bless / Xk1 / freeform rules live in `special_rolls.py` for both the buttons and the server
- [x] Simulate mode for non-editors and anonymous visitors (S1; anonymous rate-limited 60/min per address). Fixed 5.6 on the way: the sheet's `viewer_can_edit` is now `can_edit_character`, so live-vs-simulate matches the sheet
- [x] Clicktests: new `test_server_rolls.py`; `test_rolls.py -k "skill or ring or athletics or otherworld or kitsune or commune or void"` + `test_void_spending.py` (64), `test_readonly_rolls.py` + `test_roll_history_clicktest.py` (73 + 1 skip), freeform / bless / Xk1 / Ide / Ishi / priest-bless (43). Dice-forcing helpers moved to `tests/e2e/dice_control.py` (browser stub + the server's `X-Test-Dice` seam, test server only)

### Phase 2 - Tracking operations
- [x] `/track/op` with the operation set in 4.2 (`tracking_ops.py`: light wounds add/set, take serious, serious +/-, void +/- capped at max, temp void, counters, toggles, reset ability / adventure, Absorb Void, Togashi heal, Hida trade, action dice spend/unspend/annotate/clear); `adventure_state` schema (`adventure_state.py`) now applied to `/track` too; the serious-wound Night's Rest cadence lives in `tracking.set_serious_wounds` for every writer
- [x] The tracking section's buttons (LW / SW / void / temp void / counters / toggles / resets /
      Togashi heal / Hida trade / Kuni reflect / Absorb Void, action dice) use operations; the bridge queues them in order and a blob save waits for them
- [x] Clicktests: `test_tracking.py`, `test_tracking_concurrency.py` (rewritten: an operation from a stale tab lands; the 409 path is provoked by a direct blob save), `test_light_wounds.py`,
      `test_void_spending.py`, `test_tracking_advanced.py`, `test_sheet_js_errors.py`, and the school techniques touched (86)

### Phase 3 - Post-roll number actions
- [x] Raises, Togashi raises, Conviction, Courtier 5th Dan on server-made rolls: `POST /roll/{session}/act` enforces the per-roll caps and pools (simulate mode counts its own spends), keeps the session total and the history row, and undoes server-side (S5); the buttons update at once and snap back on a refusal (S2). The session-less windows (attack, wound check, duel) spend the same pools through the `counter` operation until their phases. Ally Conviction, the arbitrary post-roll bonus and Mirumoto points belong to the attack / parry windows and move with Phases 6-7
- [x] Clicktests: `test_rolls.py -k "raise or conviction"`, `test_school_abilities.py -k
      "togashi or courtier or mirumoto or priest"`

### Phase 4 - Rerolls
- [x] One reroll primitive (whole roll, chosen dice, explode 10s, add a die) and the shared lock:
      `REROLLS` in `roll_sessions.py`, scored by `roll_engine.score_roll` exactly as a first roll is.
      Every reroll keeps the actions already taken (S3); Lucky / PCP / business share one lock and keep
      the higher total, recorded as `payload.lucky`
- [x] Lucky, PCP (reroll / free raise / reroll 10s; the PCP spend is `services/pcp.py`, shared with
      `/spend-pcp`), Merchant (business, 5th Dan, +1k1 - its cap now counts the roll's pre-roll void
      too), the Priest ritual (self or a visible party priest), Togashi 4th Dan (one roll, one history
      row, keeps its bonuses - settles 5.1), Wave Man W5 (applied by `roll_dice` on every whole
      reroll). **Hida 3rd Dan moves to Phase 7**: it rerolls attack dice only, and the attack is still
      rolled in the browser until then (5.2 is settled there). The combat windows' Lucky / PCP rerolls
      likewise move with their windows (Phases 6-9)
- [x] Clicktests: `test_pcp.py`, `test_rolls.py -k lucky`, `test_school_abilities.py -k
      "merchant or hida or togashi"`, `test_professions.py -k "merchant or wave"`

### Phase 5 - Initiative and rounds
- [x] Initiative (both Togashi variants), rerolls on initiative, Merchant 5th keep-lowest, round
      start, action-die operations: `initiative` / `initiative:athletics` are session rolls
      (`roll_sessions._start_initiative`); `roll_engine.roll_initiative_dice` + `score_initiative`
      are shared with the Discord command, which now also marks every die of the all-athletics
      variant. A live roll starts the round with `tracking.start_combat_round` (Priest 5th Dan
      conviction, per-round state) and records; Lucky / PCP rerolls take the new set and restart
      the round. Initiative refuses bonuses and the partial rerolls (Merchant 5th Dan is never
      offered on initiative, so its keep-lowest branch goes with the browser code in Phase 10).
      Action-die operations were Phase 2. Mirumoto round points are persisted with their spends
      in Phase 6
- [x] Clicktests: `-k "initiative or action_di or round"` across e2e (83), and
      `test_school_abilities.py -k "(kakita or shinjo or hiruma or mantis or togashi) and
      (initiative or phase_0 or round or posture or 4th_dan ...)"` (the whole-school selection is
      173 tests, over the guard)

### Phase 6 - Parry and feint
- [x] Parry (predeclared, interrupt, athletics), feint, and their hooks: Mirumoto temp void, Shinjo
      decrement and bank, Hiruma bank, feint temp void, Akodo feint, Bayushi and Ide banks, and the
      Shiba and Bayushi sub-damage rolls (recorded, per 5.5). Parry / athletics parry / feint are
      session rolls; `predeclared` is a roll choice (+5). The hooks a live roll triggers by itself
      are `parry_feint.apply_post_roll_hooks`; the result panel's choices are session actions
      (`akodo_feint`, `ide_bank`, `shinjo_bank`, `shinjo_phase`, `sub_damage`, and `akodo_vp` -
      Akodo 4th Dan, now through `apply_void_spend`, settling 5.3 for the dice roller, iaijutsu
      included). One flag definition, `parry_feint_flags`, feeds the sheet and the server. The
      roll waits for the queued action-die spend
- [x] Mirumoto 3rd Dan round points persisted in `adventure_state` (`mirumoto_round_points`),
      refilled by `start_combat_round`, spent on a parry session (`mirumoto_point`) or, for the
      browser-rolled attack until Phase 7, the `mirumoto_points` operation; the tracking section's
      buttons are operations too (S4, settles 5.4)
- [x] Clicktests: `-k "parry or feint"` across e2e (67), and `-k "(mirumoto or shinjo or hiruma or
      shiba or bayushi or ide_ or akodo) and not (parry or feint)"` (83); five tests that set
      tracking only on the tab were fixed

### Phase 7 - Attack and damage
- [x] The attack modal's situational inputs as the roll's choices; banked-bonus consumption;
      Isawa trade; Mantis postures; W1; Matsu near miss; Doji; Kakita phases. Every attack variant is
      a session roll. `attack_rolls.build_attack` turns the inputs (TN, extra bonus, specialization
      boxes, Doji / Shinjo / Kakita phases, the spent die) plus what the server knows (the Mantis
      postures and accumulators, the Hiruma / Ide banks it spends) into the rolled formula;
      `attack_outcome` is the hit, Matsu's near miss, W1 and the extra dice, re-judged after every
      action. The Isawa trade is an action (on by default). One flag definition, `attack_flags`.
      Mantis postures, the Mantis 3rd Dan spends and the Kakita interrupt are tracking operations
- [x] Damage through `combat_math.damage_pool` (one assembler, per 5.8), Otaku 5th Dan trade,
      Hiruma post-parry, Mantis accumulators: `damage_pool` grew the sheet's inputs (weapon dice,
      extra flats, W9 claim, trade) and the Hiruma bonus; W4's rounding is part of `score_roll`.
      Damage is a child session (`damage` action), recorded as `<attack key>:damage`, with its own
      Lucky / PCP rerolls and Conviction
- [x] The attack window's rerolls on the session: Lucky / PCP (reroll, free raise, reroll 10s),
      Hida 3rd Dan chosen-dice reroll keeping every bonus (S3, settles 5.2). Plus the panel's
      choices: raises, Togashi raises, Conviction, Mirumoto points, Akodo 4th Dan void raise, Akodo
      3rd Dan and Bayushi 4th Dan banks, the post-roll bonus, the Courtier void point
- [x] Clicktests: `-k "(attack or damage or mantis or kakita) and not test_school_abilities"`,
      `test_school_abilities.py -k "attack or damage"`, and `-k "(mantis or kakita) and (posture or
      interrupt or 3rd_dan or phase_0) and not (attack or damage)"`. Nine tests fixed: most set
      state only on the tab; the Lucky pair tests now force the server's dice; a TN corrected after
      the roll is sent with the damage roll and the server re-judges at it

### Phase 8 - Wound check
- [x] Wound check, post-roll void (with consequences, per 5.3), keep / take, auto-fail, banks
      (Isawa, Akodo, Matsu, Hida), Akodo 5th reflect, Yogo temp void. The check is a session roll
      against the character's persisted light wounds (a non-editor's test-drive names its own
      amount); `wound_checks.build_wound_check` adds the Mantis defensive bonuses, the Hida bank it
      spends, Doji 5th Dan and a Daidoji counterattack; `wc_resolve` applies the outcome (the Night's
      Rest cadence included, via `set_serious_wounds`). An iaijutsu strike's check takes only
      Conviction. The Akodo 5th Dan reflect is a tracking operation. `wound_check_flags` is the one
      flag definition (it also fixed the party Daidoji's raises, which read a skill that does not
      exist and was always 1)
- [x] Clicktests: `-k "wound or wc or light_wound or serious"` across e2e (79), and
      `test_school_abilities.py -k "(yogo or akodo or matsu or isawa or hida or daidoji) and not
      (wound or wc or light_wound or serious or attack or damage or parry or feint or
      initiative)"` (40); four tests that set banks or pools only on the tab fixed

### Phase 9 - Duel and Kakita 5th Dan
- [x] The duel's contested / strike / damage as chained sessions; Kakita 5th Dan contest and damage
      (recorded); the once-per-round latch enforced. `iaijutsu:contested` (void allowed, the
      restart bonus a choice) and `iaijutsu:strike` (no void, no rerolled 10s, judged against the
      opponent's TN) are session rolls under the keys the sheet recorded them as; `duel_damage`
      rolls the strike's damage as a child session (`iaijutsu:damage`). `kakita_5th_dan` builds the
      contest from its inputs (`duels.kakita_5th_formula`), refuses once the round's use is spent
      and latches it the moment it is rolled; `kakita_5th_damage` is recorded as
      `kakita_5th_dan:damage` (settles the rest of 5.5). The opponent's duel damage is a
      `light_wounds` operation
- [x] Clicktests: `-k "(duel or kakita or iaijutsu or k5) and not test_school_abilities"` (36) and
      `test_school_abilities.py -k "duel or kakita or iaijutsu or k5"` (80); the duel's dice mock and
      the Kakita 5th Dan tests now wait for / force the server's roll

### Phase 10 - Precepts pool and retirement
- [ ] Precepts pool roll and swaps (own and ally) as operations
- [ ] Retire `/track` (blob), browser dice generation, the result-computing JS in `roll_math.js` and
      its shared tables; update CLAUDE.md (Read-only Roll Mode, tracking revision, roll history)
- [ ] One full clicktest run with a stated reason (the only time this project runs the whole suite)

## 7. Out of scope

- **Server-rendered UI.** The modals stay in Alpine.
- **New rules.** Behavior changes only where section 5 settles an inconsistency.
- **New Discord commands.** They would become easy, but each one is a separate GM decision.

## 8. Decisions (GM, 2026-09-28)

| # | decision |
|---|---|
| S1 | **One path.** Everyone rolls on the server: editors live, and logged-in non-editors and anonymous visitors in simulate mode (the anonymous path rate-limited). No browser dice for anyone, "otherwise we're just duplicating effort." |
| S2 | **Latency plan accepted.** Rolls and rerolls always wait for the server, under the dice animation. The pure +/- raise and Conviction buttons show their effect at once and are corrected by the server's answer. |
| S3 | **Rerolls always keep bonuses.** A reroll replaces dice and nothing else; raises, void, Conviction and every other bonus already applied stay. This settles 5.1 (Togashi 4th Dan) and 5.2 (Hida 3rd Dan) and applies to every reroll mechanic. |
| S4 | **The other section 5 items are fixed as bugs**; Mirumoto's round points are persisted and cleared at round start (5.4). |
| S5 | **Undo stays** on every post-roll action, as a server-side undo on the roll session. |
| S6 | **No browser fallback.** If the server cannot be reached, the roll shows an error and a Retry button. |
| S7 | **A deploy per phase**, with old and new paths side by side until Phase 10. |
