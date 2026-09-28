# GM Combat Tracker and Generated NPCs - Design

Status: **built and deployed** (2026-09-28). All phases done, including the GM's review of the three new simulator progression lists.

## 1. Goal

**The GM's screen.** One screen per gaming group for running a fight:

- every PC in the group, with their **action dice**, **wounds**, **void points** and **discretionary bonuses** (3rd Dan free raises and the like), kept current as the players act on their own sheets;
- the **NPCs they are fighting** on the same screen. The GM acts for them with **quick-roll buttons**: click an NPC's action die and choose what it is spent on (attack, parry, ...). The GM never rolls for PCs.

**The players' view.** A public combat page, linked from the group page, shows each NPC's wounds, whether it is down, the actions it has taken this round with each roll's **total only**, and how many actions it took last round. It never shows what the NPC still has available or how a total was reached.

**Generated NPCs.** They are generated, not hand-built: "the party is fighting six Wave Men with about 50 earned XP" produces six usable combatants.
- **Their builds follow the combat simulator's current XP progression** (`l7r/simulator`). That repo is where questions like "when does a parry school take Air from 5 to 6" get answered.
- **They are real `Character` rows**, so they go through the same rules code as PCs.
- **Players never see their stats**, and they never appear on the home page.

## 2. Decisions

### Round 1

| # | decision |
|---|---|
| D1 | The simulator's profession-ability count (`(xp - 100) // 15 + 1`) is a **simulator bug**. This app's rule (1 ability at 150 total XP, +1 per 15) is correct. Fix it in the simulator. |
| D2 | **Earned XP** is on top of the starting 150: "50 earned" = 200 total. The GM always gives earned XP. |
| D3 | **Freshness:** "as of this app's last deploy" is fine. What matters is a smooth dev loop while we change the simulator as part of this work. |
| D4 | **Each NPC draws its own XP.** The build is otherwise the simulator's. |
| D5 | **XP entry:** an **exact** earned XP, or a **base** (usually a multiple of 50) plus **5 x an exploding d10**. A 10 rerolls and adds, so 10, 10, 2 gives +110. |
| D6 | **Combat share:** the GM sets a target for the encounter or per NPC. Each NPC varies around it with the spread measured from real characters (`analysis/CombatVsNonCombatXP.md`). A per-NPC override replaces the draw. |
| D7 | **Quick-roll buttons on the tracker**, with damage and wound-check math on the server. Long-term direction: the browser kicks off server actions that other clients can also call. |
| D8 | **NPCs can be archived** after a fight and brought back later, optionally with **gained XP**. |
| D9 | **At 2 x Earth serious wounds the GM chooses "unconscious" or "dead".** It depends on the weapon, which the app does not know. |
| D10 | **Names are suggested the way gm-assistant does it:** its pool, excluding names already used in the campaign and names too similar to them. |
| D11 | **No round or phase pointer.** Each combatant's action dice and wounds are enough; the GM calls phases aloud. Explicit phase ticking may come later, for per-phase abilities. |

### Round 2

| # | decision |
|---|---|
| D12 | **I may push to the simulator and gm-assistant repos**, adding commits only: no force pushes and no history rewrites (the GM configured the repos that way). **Blocked:** this container has no SSH key for them (see Q1). |
| D13 | **XP entry has a "roll extra" checkbox, on by default.** Checked: base + roll. Unchecked: exactly the number typed. |
| D14 | **The combat share is clamped to the range real PCs have had**: the lowest and highest measured (today 53.2% and 91.0%). The clamp comes from the same table as the spread, so it moves if the analysis is re-run. |
| D15 | **Moving the sheet's own roll windows onto the server is a separate, later project**, except where this feature needs it. |
| D16 | **NPC names are always male.** |
| D17 | **A returning NPC comes back healed and rested.** The GM marks any lingering wounds by hand. |
| D18 | **Builds are needed for Mantis Wave-Treader, Kitsune Warden and Suzume Overseer, following the simulator's existing precedent** (its `school-progression-designer` agent: identity-driven, and schools sharing a school ring advance similarly). **Not** for Shugenja or Worker. |
| D19 | **NPC attacks a PC:** "attack" opens a sub-menu of targets. Picking one opens the attack roll with **that PC's TN to be hit pre-filled and editable**, for situational modifiers. The GM tells the player the result; **the player decides about parrying** (including pre-declaring). The tracker rolls damage, and the GM tells the player the number. **The tracker never writes to a PC.** Players who roll physical dice enter wounds on their sheet by hand, and the tracker simply reflects it. |
| D20 | **The GM chooses keep-light-wounds vs take-a-serious-wound** for an NPC's passed wound check. |
| D21 | **NPC rolls are recorded, and there is a combat rolls view:** every roll made during the encounter, PC and NPC, in order, with a filter to NPC-only. It is for eyeballing whether the NPCs rolled above or below average. |
| D22 | **Players see, per NPC:** the actions it has taken this round, its wounds, whether it is down, and **after the first full round, how many actions it took last round**. That count is how players infer "one more action left" without learning its phase or whether it is available. **Players never see** remaining action dice, void or any stat. |
| D23 | **Nothing goes to Discord for now.** Combat is too interactive for slash commands: probability charts and chained decisions. Attacks and wound checks will likely never be Discord commands. |

### Round 3

| # | decision |
|---|---|
| D24 | **Git for the other repos.** gm-assistant: work in its session clone (`.clones/combat`, after this session's name) and land through its `scripts/sync-with-main.sh`, which also pushes to GitHub with gm-assistant's own token. Simulator: commit on its `master` following its conventions; **the GM pushes** until credentials exist here. |
| D25 | **Stub schools are fine** for Mantis Wave-Treader, Kitsune Warden and Suzume Overseer: enough for the progression code to build them, marked as not usable in simulator fights. Full mechanics go on the simulator's backlog. |
| D26 | **Names:** Wave Men always from the **peasant** pool. Samurai-school NPCs get a **samurai-eligible personal name only**; the GM types a full name if one is ever needed. |
| D27 | **The players' view is its own page**, linked from the group page like Money, and it is **public**. Logged in as the GM you get the tracker controls; everyone else, logged in or not, gets the same public view. |
| D28 | **Players see the NPC's real name.** For a mystery, the GM types a name like "Bandit 2" instead of using a generated one. |
| D29 | **Players see each NPC roll's total** ("attack: 52"), never how it was reached: no dice, no 10s, no void spent, no breakdown of bonuses. They cannot see NPC roll history; the GM screen-shares if they want to. |
| D30 | **Every visible PC in the group** is on the tracker. |
| D31 | **"New round" rolls initiative for the NPCs only.** Players roll their own. |

### Round 4

| # | decision |
|---|---|
| D32 | **The public view lists the PCs too**: their wounds and remaining action dice, alongside the NPCs. |
| D33 | **One fight at a time per group.** Starting a new encounter ends the current one, after a confirmation. When none is active, the public page says "No fight in progress". |

## 3. What exists today

### Simulator (`/host-l7r-repo/simulator`, GitHub `claude-guided-l7r-combat-simulator`, public)

- **The generator:** `simulation/templates/generator.py::generate_template(school_key, total_xp, priorities=None)`.
  - Deterministic, works at any XP.
  - Spends `COMBAT_XP_FRACTION = 0.75` greedily down `strategies.SCHOOL_PRIORITIES`.
  - Leaves the rest unspent.
  - Monotonic in XP, so re-generation at a higher XP only adds to a build.
- **It builds through each school's class** in `simulation/schools/`. Mantis, Kitsune Warden and Suzume have **no class there**, not just no priority list (see Q2).
- **The priority-design precedent:** the `school-progression-designer` agent (`.claude/agents/`) proposes a school's list from its rules identity, with a rationale for each entry. Its hard rule is "not template-copied". New schools go through the simulator's speckit workflow.
- **Not installable.** The generator imports `web.models.CharacterConfig`, which must move under `simulation`.
- **Ids differ from `app/game_data.py`** for schools, knacks (spaces vs underscores) and all Wave Man abilities.
- **House rules:** TDD, ruff, strict mypy, 100% coverage.

### gm-assistant (`/host-l7r-repo/gm-assistant`, GitHub public, deployed `l7r-gm-assistant.fly.dev`, sleeps when idle)

- **Name picking:** `webapp/chargen/namepool.py::pick_name` over given-name pools, with `similarity.py` for the rules (edit distance <= 1 or a prefix match against used names; in-batch, also same first letter and rhymes).
- **The used-name set exists only there:** Obsidian Portal, lineage tags, a manual list, and a scrape of this app's public index.
- **No names endpoint.** `/chargen/generate` needs a Discord session.

### This app

- **No NPC concept.** About 8 sites list characters.
- **The server builds every formula** (`build_all_roll_formulas`) **and rolls single formulas and initiative** (`roll_engine`). **Damage assembly and the wound-check outcome are browser-only** (`_dice_js.html`, `roll_math.js`).
- **No live updates.** `/api/characters` has a pollable `current` block behind a bearer token.
- **The group summary page is public**, anonymous visitors included.
- **Roll history** is per character. The GM owns NPCs, so `should_record_roll` would record their rolls.

## 4. Architecture

### 4.1 The simulator as a library

- **In the simulator:**
  - `[project]` packaging exporting `simulation` only.
  - A `combat_xp_fraction` argument on `generate_template`.
  - The D1 fix.
  - The D18 schools.
- **Local development:** `pip install -e /host-l7r-repo/simulator`, so simulator edits are live here at once.
- **Deploys:** bundle the simulator checkout's committed `HEAD` into the build context (`scripts/deploy.sh`), the same way every other file in every Fly image here comes from this machine rather than from GitHub. Each NPC records the simulator commit that built it. (First built as a GitHub install of `master`; changed on 2026-09-28 to match how the other deploys work and so a deploy never waits on a push.)
- **The adapter:** `app/services/npc_generator.py` translates through **one id-mapping table**. A guard test walks every simulator school, knack and ability and fails on any it cannot map, unless that item is explicitly listed as unsupported.

### 4.2 Generating an NPC

1. **Earned XP (D5, D13).** Exact, or `base + 5 x exploding_d10()` (mean bonus about 30.5; 1 in 100 get +100 or more). Then `total = 150 + earned`.
2. **Combat share (D6, D14).**
   - `share = clamp(target + one deviation drawn from the measured characters, measured min, measured max)`.
   - The deviations are the 19 real characters minus their median (74.1%), so -20.9 to +16.9 points. Resampling real data keeps its actual shape: a tight middle with a few generalists and pure fighters.
   - The default target is the median. A per-NPC override replaces the draw and is still clamped.
   - The table lives in `game_data.py` beside `XP_PROFILE_BANDS`, and the analysis script regenerates it.
3. **Build:** `generate_template(sim_school, total, combat_xp_fraction=share)`, then translation.
   - Stored on the NPC as **generation parameters**: school, earned XP, the roll, the share, and the simulator commit. They make re-generation at a higher XP possible (D8).
4. **Name:** see 4.6.

### 4.3 NPCs, encounters, rounds, archive

**NPC characters.**
- An NPC is a `Character` with `is_npc = True`, owned by the GM, `is_hidden = True`.
- **One listing helper excludes NPCs everywhere**, and a guard test makes new listing sites use it.
- **Only the GM can open an NPC sheet.** An NPC is never a party member and can never be resolved from Discord.

**Encounters.**
- An `Encounter` has `id`, `gaming_group_id`, `name`, `status`, `started_at`, `ended_at` and `current_round`.
- A link table joins NPCs to encounters, so an archived NPC can fight again.

**Rounds and actions (D22).**
- The GM clicks **"New round"**, which rolls initiative for every NPC in the encounter and increments `current_round`. The PCs roll their own initiative, as today.
- Every action the GM takes for an NPC is logged as an `EncounterAction`: encounter, NPC, round, kind (attack / parry / other), target, and the roll it produced.
  - An interrupt parry spends 2 dice but is **one action**, which is what the players saw.
  - The player view counts actions, not dice.

**Status (D9).**
- Each NPC is `fighting`, `unconscious` or `dead` in the encounter.
- Reaching 2 x Earth serious wounds prompts the GM for unconscious or dead. Status stays GM-settable.

**End and return (D8, D17).**
- Ending an encounter archives its NPCs into a GM-only per-group **NPC roster**.
- Bringing an NPC back into a new encounter heals and rests them, and optionally applies **gained earned XP**. That re-generates from the stored school and share.
- Dead NPCs stay in the roster, marked dead. Deleting from the roster is explicit.

### 4.4 Server-side combat actions (D7, D15, D19, D20)

**Endpoints, GM-only, NPCs only:**
- **attack** (by type, target PC, TN defaulting to that PC's TN to be hit and overridable);
- **"the PC's parry result"**: not parried / failed parry / parried. A failed parry reduces damage dice by the PC's parry skill, which the tracker knows;
- **damage**;
- **NPC parry** against a GM-typed attack total;
- **NPC takes damage:** light wounds are added and the wound check rolled, then the GM picks keep-LW or take-SW;
- **new round**, which rolls NPC initiative.

**Where the rules come from.** Formulas come from `build_all_roll_formulas`, dice from `roll_engine`. The damage and wound-check arithmetic now in `roll_math.js` gets a Python twin, pinned to a shared case table in `tests/shared/`.

**Choices during a roll.** Pre-roll void is a picker on the button. Post-roll discretionary choices (void on a wound check, 3rd Dan free raises) are a small prompt in the result. Anything more exotic falls back to opening the NPC's full sheet.

### 4.5 Views

**The GM's tracker (the GM's view of `GET /groups/{id}/combat`).**
- **Cards:** every visible PC in the group (D30), and PC and NPC cards with action dice (spent / unspent), LW, SW / max, void, discretionary bonuses remaining, and TN to be hit. NPC cards add status and clickable action dice.
- **Encounter builder:** rows of "N x school, XP (+ roll extra), combat target", with per-NPC overrides after generation. Names are fetched for the rows.
- **Live updates:** polls a GM-only state endpoint every few seconds, comparing `tracking_rev` and encounter state to skip redraws.

**One URL, two views: `GET /groups/{id}/combat` (D27).** It is public. The GM, when logged in, gets the tracker described above; everyone else gets the public view. The group page links to it, the way it links to Money.
- **Public view, per NPC:** name (D28), LW / SW, down or not, this round's actions (kind, target and roll **total** - D29), and last round's action count (D22).
- **Never in the public view:** dice, void, phases, remaining actions, stats, how a total was reached, or roll history.
- **Live updates:** the public view polls its own endpoint. Its payload is built from an **allow-list**, so a field added later cannot leak by accident, and a test asserts the exact key set.
- **PCs in the public view (D32):** every visible PC, with wounds and remaining action dice.

**The combat rolls view (D21), per encounter.**
- **Contents:** every `roll_history` row between `started_at` and `ended_at` from the group's PCs and the encounter's NPCs, in order.
- **Filters:** all / NPC-only / PC-only. Each row shows its dice so "above or below average" can be eyeballed.

### 4.6 Names (D10, D16)

- **The used-name data is only reachable from gm-assistant**, so picking stays there. It gets a token-authed `GET /api/names?count=&peasant=`, male pool only. `peasant=true` for Wave Men; `peasant=false` (samurai-eligible) for school NPCs, given name only (D26). The endpoint refreshes the used-name cache when stale and applies both the used-name and within-batch rules.
- **In this app:** the builder pre-fills names, and the GM can edit one or ask for another. If gm-assistant is asleep or down, names fall back to "Wave Man 1..N".
- **NPC names reach gm-assistant's used-name set through `/api/characters`**, flagged `is_npc`. The public-index scrape cannot see them.

## 5. Out of scope

- The GM rolling for PCs, or writing to a PC's tracking state.
- Discord (D23).
- A new rules engine.
- Moving the sheet's own roll windows to the server (D15).
- Shugenja and Worker NPC builds (D18).

## 6. Phases

Each phase ends with tests green at 100% coverage in every repo it touches, targeted clicktests, commits, pushes, and a deploy where there is UI.

### Phase 0 - Requirements
- [x] Survey the simulator, gm-assistant and this app
- [x] Fold in GM answers, rounds 1 and 2
- [x] GM answers rounds 3 and 4

### Phase 1 - Simulator as a library
- [x] Simulator: D1 fix, with a test (simulator `d75e505`)
- [x] Simulator: `[project]` packaging exporting `simulation` only; move `CharacterConfig` under it
- [x] Simulator: `combat_xp_fraction` argument
- [x] Here: editable install for dev; deploys bundle the simulator's committed HEAD (`scripts/deploy.sh`)
- [x] Here: `npc_generator.py` + id-mapping table + guard tests (every simulator school offered or explicitly unsupported; every offered school's knacks and ring agree with this app)
- [x] Here: XP roll (D5) and combat-share draw with clamp (D6, D14); `NPC_COMBAT_SHARE_SAMPLES` generated by `analysis/xp_profile_ranges.py --npc-combat-shares`

### Phase 2 - New simulator schools (D18)
- [x] Mantis Wave-Treader: stub school class (D25) + priorities via `school-progression-designer` (simulator `e7961e6`)
- [x] Kitsune Warden: same (default ring Fire, per the designer)
- [x] Suzume Overseer: same
- [x] GM reviewed and approved each progression's rationale (2026-09-28). The approved choices:
  - **Mantis Wave-Treader** - default school ring **Fire** (both offensive-posture clauses boost attack and damage). Attack leads every tier (it is X in both 3rd Dan clauses), parry kept level (defensive posture adds to TN to be hit), **Water 3** is the first bought ring (four clauses touch wound checks), Dan-5 skills before the rank-3 rings, then Void / Earth / Air. No non-combat skill bought.
  - **Kitsune Warden** - default school ring **Fire** over Water (the ring swap cannot reach damage or iaijutsu, so a native Fire ring covers what the swap cannot). Iaijutsu first among knacks, **precepts to 5** out of the combat budget (3rd Dan's X), Earth 3 at Dan 3, then Void / Water / Air, Earth 4 in the 20-XP ring tier.
  - **Suzume Overseer** - Water (fixed). **Precepts to 5** first (3rd Dan's X, 1st Dan die), worldliness leads the knacks (void points are lowest ring + worldliness, and the special ability spends void after the roll), attack before parry, the four non-Water rings raised together so the lowest ring rises.

**Found while building Phases 1-2:**
- **Hiruma Scout is stale in the simulator.** The rules swapped counterattack for lunge (l7r `48410d9`), including the 3rd Dan interrupt, and the simulator still uses counterattack. It is left out of the NPC list (`UNSUPPORTED_SIM_KEYS`) and recorded in the simulator's BACKLOG. It is a combat-mechanics change, so it goes through the simulator's per-school workflow.
- **Several existing simulator lists are not monotonic between tiers** (a stat can drop a rank at, say, 160 XP vs 150). The three new lists are monotonic, and a test checks it in 10-XP steps. A returning NPC is re-generated through `never_below()`, so it never comes back weaker.
- **Deploys need the simulator commits pushed.** They are committed in `/host-l7r-repo/simulator` (`d75e505`, `e7961e6`, `3e9fec9`), and this container cannot push there.

### Phase 3 - NPC characters, encounters, roster
- [x] `is_npc` + generation-parameter columns + migrations; `Encounter`, link and `EncounterAction` models
- [x] Listing sites: NPCs keep `gaming_group_id` NULL (group / party / Discord queries exclude them by construction), the home page filters `is_npc`; a census test fails on any new unclassified listing query
- [x] NPC sheet GM-only (`npc_guard` on every `{char_id}` router, test-enforced); no party effects; no Discord resolution; `/api/characters` and `/api/rolls` flag `is_npc`
- [x] Suppress PC-only validation noise on NPC sheets
- [x] Encounter create / end; roster; return healed with gained XP; unconscious / dead

### Phase 4 - Names
- [x] gm-assistant, in its session clone (D24): token-authed `/api/names` (male, peasant or samurai, cache refresh, batch rules) - gm-assistant spec 213, commits `aa4a384d` / `109e3750`, pushed. It also now reads this app's `/api/characters` so NPC names count as used. **Off until the GM sets `names_token` and deploys gm-assistant** (see 4.6).
- [x] Here: client with a fallback (`services/npc_names.py`; names fetched before the handler's read-modify-write)

### Phase 5 - Server combat actions
- [x] Python damage + wound-check math (`combat_math.py`), with a shared case table against `roll_math.js` (`tests/shared/combat_math_cases.json`); the damage school flags moved to one `damage_flags()` the sheet also reads
- [x] Endpoints in 4.4 (`combat_actions.py`, `routes/combat.py`), action log, rounds, recording

### Phase 6 - Views
- [x] GM tracker: cards (with remaining per-adventure bonuses, shared with the sheet via `per_adventure.py`), action-die menu, encounter builder, 2 x Earth prompt, archive
- [x] Public view of the combat page, linked from the group page (allow-listed payload, totals only)
- [x] Combat rolls view
- [x] Clicktests + `COVERAGE.md`; responsive checks; deployed 2026-09-28 (`scripts/deploy.sh`, simulator `86d21d43a80a`), verified live: public combat page 200, NPC generation on the production machine, gm-assistant names

### To finish (needs the GM)
- [x] Push the simulator commits (`d75e505`..`86d21d4`, pushed with the simulator's own `GITHUB_TOKEN`) and deploy this app with `scripts/deploy.sh`.
- [x] Turn on name suggestions: `names_token` added to gm-assistant's secrets, gm-assistant deployed through `make deploy` (1863 tests, 100% coverage), and `GET /api/names` answers live (401 without the token). This app's `GM_ASSISTANT_URL` / `GM_ASSISTANT_NAMES_TOKEN` are staged Fly secrets that take effect with the next deploy.
- [ ] Review the three new progression lists (Phase 2).

### Later
- [ ] Explicit phase ticking, for per-phase abilities (D11)
- [ ] The sheet's own roll windows calling the server API (D15)
- [ ] Any Discord integration (D23)

## 7. Answered and folded in

- Round 1: Q1-Q3, Q10, Q11.
- Round 2: exact vs base XP (D13), clamp (D14), sheet migration (D15), returning NPCs (D17), missing schools (D18), NPC attacks (D19), keep-LW vs take-SW (D20), records (D21), player visibility (D22, D23), card detail (D23 / 4.5).
- Round 3: git (D24), stub schools (D25), names (D26), public combat page (D27), real names (D28), roll totals only (D29), every visible PC (D30), new round (D31).
- Round 4: PCs on the public page (D32), one fight at a time (D33).
