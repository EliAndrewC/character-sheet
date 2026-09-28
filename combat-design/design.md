# GM Combat Tracker and Generated NPCs - Design

Status: **requirements gathering, round 2.** Nothing is implemented. Section 7 lists the questions still open;
Phase 1 does not start until the GM signs off on this document.

## 1. Goal

The GM wants one screen, per gaming group, for running a fight:

- every PC in the group, with their **action dice**, **light wounds** and **serious wounds**, kept current as the players act on their own sheets;
- the **NPCs they are fighting** on the same screen. The GM acts for them with **quick-roll buttons on the tracker itself**: click an NPC's action die and choose what it is spent on (attack, parry, ...). The GM never rolls for PCs.

The NPCs are **generated**, not hand-built: "the party is fighting six Wave Men with about 50 earned XP" produces six usable combatants.
- **Their builds follow the combat simulator's current XP progression** (`l7r/simulator`, <https://l7r-combat-sim.fly.dev/>). That repo is where questions like "when does a parry school take Air from 5 to 6" get answered, and this app picks up its answers without code changes here.
- **They are real `Character` rows**, so they go through the same rules code as PCs.
- **Players never see them**, and they never appear on the home page.

## 2. Decisions so far (GM, round 1)

| # | decision |
|---|---|
| D1 | The simulator's profession-ability count (`(xp - 100) // 15 + 1`) is a **simulator bug**. This app's rule (1 ability at 150 total XP, +1 per 15) is correct. Fix it in the simulator. |
| D2 | **Earned XP** is always on top of the starting 150: "50 earned" = 200 total. The GM always gives figures in earned XP. |
| D3 | **Freshness:** "as of this app's last deploy" is fine. What matters is a smooth dev loop while we change the simulator as part of this work. |
| D4 | **Each NPC draws its own XP.** The build is otherwise the simulator's. |
| D5 | **XP entry:** the GM either types an **exact** earned XP, or (usually) a **base** in steps of 50, to which is added **5 x an exploding d10**. A 10 rerolls and adds, so 10, 10, 2 gives +110 (22 x 5). |
| D6 | **Combat share is not fixed at 75%.** The GM sets a target, for the whole encounter or per NPC. Each NPC varies around it with the spread we measured from real characters (`analysis/CombatVsNonCombatXP.md`), and the GM can override it for one NPC (e.g. a bruiser boss). |
| D7 | **Quick-roll buttons on the tracker.** Damage and wound-check math move to the server. This matches the long-term direction: the browser should kick off server actions through an API that other clients can call too. |
| D8 | **NPCs can be archived** after a fight and brought back later, optionally having **gained XP** in between. |
| D9 | **At 2 x Earth serious wounds the GM chooses "unconscious" or "dead".** It depends on the weapon (fists vs swords), which the app does not know. |
| D10 | **Names are suggested the way gm-assistant does it:** from its name pool, excluding names already used in the campaign and names too similar to them. |
| D11 | **No round or phase pointer.** The tracker lists every combatant's action dice and wounds; the GM calls phases aloud. Explicit phase ticking may come later, for per-phase abilities. |

## 3. What exists today

### Simulator (`/host-l7r-repo/simulator`, repo `claude-guided-l7r-combat-simulator`, public on GitHub)

- **The generator:** `simulation/templates/generator.py::generate_template(school_key, total_xp, priorities=None) -> (CharacterConfig, breakdown)`.
  - Deterministic, works at any XP.
  - Spends `COMBAT_XP_FRACTION = 0.75` of total XP greedily down a per-school priority list (`simulation/templates/strategies.py::SCHOOL_PRIORITIES`).
  - Leaves the rest unspent and unassigned, which is what we want.
  - Higher XP never gives lower stats, which makes "the returning NPC gained XP" simply a re-generation at the new total.
- **Not installable:** `pyproject.toml` has no `[project]` table.
  - The generator imports `web.models.CharacterConfig`. A top-level `web` package would be an unwelcome thing to install into this app's environment, so `CharacterConfig` (or the generator's output type) should move under `simulation`.
- **No JSON API:** the deployed site is Streamlit.
- **Coverage gaps:** there are no builds for Mantis Wave-Treader, Kitsune Warden, Suzume Overseer, Shugenja or Worker.
- **Its ids differ from `app/game_data.py`:**
  - Schools: `kakita` vs `kakita_duelist`, `monk` vs `brotherhood_of_shinsei_monk`.
  - Knacks: `"double attack"` vs `double_attack`.
  - All ten Wave Man ability names, e.g. `"missed attack bonus"` vs `wave_man_miss_raise`.
- **Its own CLAUDE.md** sets these rules: TDD, ruff, strict mypy, 100% coverage, and **"never run `git push` yourself"**.

### gm-assistant (`/host-l7r-repo/gm-assistant`, public on GitHub, deployed as `l7r-gm-assistant.fly.dev`, sleeps when idle)

- **Name picking:**
  - `webapp/chargen/namepool.py::pick_name(gender, pool, used, avoid, peasant)` picks over gendered given-name pools (`pool-male.jsonl`, `pool-female.jsonl`).
  - `webapp/chargen/similarity.py` has the rules: edit distance <= 1 or a prefix match against used names. Within one batch, it also rejects the same first letter and rhymes.
- **The used-name set is only available inside gm-assistant.** It combines:
  - Obsidian Portal (an OAuth API behind gm-assistant's secrets),
  - lineage tags,
  - a manual list,
  - a scrape of **this app's public index**.
- **No endpoint returns suggested names.** `/chargen/generate` needs a Discord session. The deployed copy's used-name cache is a snapshot taken at deploy time.

### This app

- **No NPC concept.** About 8 sites list characters: `index`, `group_summary`, the dark-secret map, `group_money` / award, `party.visible_party_members`, `/api/characters`, `/api/rolls`, and `discord_commands.resolve_character`.
- **Split between server and browser:**
  - The server builds every roll's **formula** (`build_all_roll_formulas`), which is where the rules live.
  - It can **roll** any single formula (`roll_engine.execute_roll`) and initiative. These two were added for the Discord bot, the first client other than the sheet.
  - **Damage assembly and the wound-check outcome (pass/fail, serious wounds) are computed only in the browser**, in `_dice_js.html` and `roll_math.js`, because the sheet began as a single interactive page.
- **Nothing updates live.** `/api/characters` has a pollable `current` block, but it is bearer-token-authed.
- **Unspent XP is legal.** The editor already computes a GM-only **XP profile** (`xp_profile()` in `services/xp.py`, bands in `game_data.XP_PROFILE_BANDS`) using the same combat categorization as the analysis.

## 4. Architecture

### 4.1 The simulator as a library (D3)

- **In the simulator repo:**
  - Add `[project]` packaging that exports `simulation` only (move `CharacterConfig` under it).
  - Make `generate_template` take a `combat_xp_fraction` argument, defaulting to today's constant.
  - Fix the profession-ability count (D1).
- **Local development:** `pip install -e /host-l7r-repo/simulator`, so a change in the simulator is live here immediately. No bump, no copy.
- **Deploys:** `requirements.txt` installs `git+https://github.com/EliAndrewC/claude-guided-l7r-combat-simulator@main`, so each deploy of this app takes the simulator's latest pushed `main`. The resolved commit is recorded on every generated NPC ("built with simulator `abc1234`") so an odd build can be traced.
- **The adapter:** `app/services/npc_generator.py` translates the simulator's output to `Character` fields through **one id-mapping table**. A guard test walks every simulator school, knack and ability, and fails if one maps to nothing and is not explicitly listed as unsupported. Drift becomes a red test, never a silently wrong NPC.

### 4.2 Generating an NPC

**Inputs per NPC:** school, earned XP (exact, or base + roll), combat-share target, optional per-NPC combat-share override, name.

1. **Earned XP (D5).**
   - An exact value is used as-is.
   - Otherwise it is `base + 5 x exploding_d10()`. The mean bonus is about 30.5 XP, and one NPC in a hundred gets +100 or more.
   - `total_xp = 150 + earned` (D2).
2. **Combat share (D6).**
   - `share = target + (a deviation drawn from the measured characters)`, clamped to a sane band.
   - The measured deviations are the 19 characters in the analysis, each minus their median (74.1%), which gives offsets from -20.9 to +16.9 points.
   - Resampling the real data keeps its actual shape: a tight cluster near the middle with a few far-out "faces" and "pure fighters". It assumes no bell curve.
   - The default target is the median. An override replaces the draw entirely.
   - The table lives in `game_data.py` beside `XP_PROFILE_BANDS`, and the analysis script regenerates it.
3. **Build:** `generate_template(sim_school, total_xp, combat_xp_fraction=share)`, then translation (4.1).
   - Stored on the NPC: school, earned XP, the XP roll, the share, and the simulator commit. These are its **generation parameters**, so it can be regenerated at a higher XP later (D8).
4. **Name (D10):** see 4.5.

### 4.3 NPCs, encounters, archive

**NPC characters.**
- An NPC is a `Character` with `is_npc = True` (new column plus a migration entry), owned by the GM, `is_hidden = True`.
- **One helper excludes NPCs from every listing site**, and a guard test makes new listing sites use it.
- **Only the GM can open an NPC sheet.** For anyone else, the NPC is never a party member and can never be resolved from Discord.

**Encounters.** An `Encounter` model has `id`, `gaming_group_id`, `name`, `status` (active / ended) and `created_at`. NPCs join an encounter through a link table, because an archived NPC can fight again in a later encounter.

**NPC state.** An NPC's per-fight status is `fighting`, `unconscious` or `dead`. Reaching 2 x Earth serious wounds prompts the GM to pick one (D9); the others stay GM-settable.

**Ending an encounter** archives its NPCs to a GM-only **NPC roster** (per group). From the roster the GM can add an archived NPC to a new encounter, optionally with **gained earned XP**. That re-runs the generator with the NPC's stored school and share, and because progression is monotonic the new build only adds to the old one. Dead NPCs stay in the roster, marked dead. Deleting from the roster is explicit.

### 4.4 Server-side combat actions (D7)

**New server endpoints, session-authed and GM-only for NPCs:**
- attack (by type) against a chosen PC's TN,
- parry against a given attack total,
- damage,
- apply light wounds + wound check,
- keep light wounds / take a serious wound,
- initiative for one or all NPCs.

**The rules are still not re-implemented.**
- Formulas come from `build_all_roll_formulas`, and dice from `roll_engine`.
- The damage and wound-check arithmetic now in `roll_math.js` gets a Python twin: excess-to-extra-dice, failed-parry reduction, the 10k10 cap and Wave Man rounding for damage; pass/fail and serious-wound count for the wound check.
- The twin is pinned to a shared case table in `tests/shared/`, per the "rules in both JS and Python" rule.

**Scope.** This project builds the server API and the tracker uses it. **Moving the sheet itself onto these endpoints is a separate, later project** (see Q4). The sheet's modals carry many mid-roll choices, and migrating them is its own large piece of work.

**Mid-roll choices for NPCs.**
- Automatic bonuses are applied, as they already are for the bot.
- Pre-roll void is a picker on the button.
- Discretionary post-roll choices (spend void on a wound check, free raises) are a small prompt in the result.
- Anything more exotic falls back to opening the NPC's full sheet, which already handles everything.

### 4.5 Names (D10)

The used-name data (Obsidian Portal) is only reachable from gm-assistant, so **the name picking stays there**. This app asks for names; it does not copy gm-assistant's rules.

- **gm-assistant grows a small token-authed JSON endpoint:** `GET /api/names?gender=&count=&peasant=&avoid=`. It refreshes its used-name cache when stale, then returns `count` names that pass both the used-name check and the within-batch check.
- **This app calls it** when the GM generates an encounter, and pre-fills each NPC's name. The GM can edit it or ask for another. If gm-assistant is asleep or down, names fall back to "Wave Man 1..N".
- **Generated NPC names must count as "used" too.** gm-assistant learns this app's names by scraping the public index, which NPCs are deliberately absent from. So NPC names reach it through `/api/characters`, flagged `is_npc` (see Q10).

### 4.6 The tracker page

- **`GET /groups/{id}/combat`, GM-only.**
- **Cards:**
  - PC cards: name, action dice (spent / unspent), LW, SW / max SW, TN to be hit.
  - NPC cards: the same, plus void, status, and clickable action dice (D11).
- **Live updates by polling** a GM-only `GET /groups/{id}/combat/state` every few seconds, which compares `tracking_rev` to skip redraws.
- **Clicking an NPC action die** opens a menu: attack (type, target PC), parry, other. The result shows in place, the die is marked spent, and wounds update.
- **Encounter builder on the same page:** rows of "N x school, XP, combat target", then generate, and names are fetched.

## 5. Out of scope

- The GM rolling for PCs.
- Player-visible NPC data of any kind (pending Q9).
- A new rules engine: every rule comes from `build_all_roll_formulas` and every build from the simulator.
- Moving the sheet's own modals onto the new server endpoints (a later project).

## 6. Phases

Each phase ends with tests green at 100% coverage in every repo it touches, targeted clicktests passing, commits and a deploy.

### Phase 0 - Requirements (current)
- [x] Survey the simulator, gm-assistant and this app
- [x] Draft this document; fold in GM round 1 answers
- [ ] GM answers section 7
- [ ] GM signs off on this document

### Phase 1 - Simulator as a library (simulator repo + this repo)
- [ ] Simulator: fix the profession-ability count (D1), with a test
- [ ] Simulator: `[project]` packaging exporting `simulation` only; move `CharacterConfig` under it
- [ ] Simulator: `combat_xp_fraction` argument on `generate_template`
- [ ] Here: git dependency in `requirements.txt`; editable install for local dev; Docker build check on 512 MB
- [ ] Here: `npc_generator.py` + id-mapping table + guard test
- [ ] Here: XP roll (D5) and combat-share draw (D6), with its table generated by the analysis script
- [ ] Unit tests: several schools across XP produce characters whose validation is clean apart from unspent XP

### Phase 2 - NPC characters, encounters, roster
- [ ] `is_npc` + generation-parameter columns + migrations; `Encounter` and link models
- [ ] Listing helper at every listing site + guard test
- [ ] NPC sheet GM-only; no party effects; no Discord resolution; `/api` per Q10
- [ ] Suppress PC-only validation noise on NPC sheets
- [ ] Encounter create / end; roster; return-with-gained-XP; unconscious / dead status

### Phase 3 - Names (gm-assistant repo + this repo)
- [ ] gm-assistant: token-authed `/api/names`, with a cache refresh
- [ ] Here: client with a fallback; NPCs on `/api/characters` flagged `is_npc`

### Phase 4 - Server combat actions
- [ ] Python damage + wound-check math, with a shared case table against `roll_math.js`
- [ ] Endpoints listed in 4.4, GM-only for NPCs, recording per Q10

### Phase 5 - The tracker page
- [ ] Page + state polling endpoint; PC and NPC cards
- [ ] Action-die menu driving the Phase 4 endpoints; result display; spent dice
- [ ] Encounter builder; 2 x Earth prompt; archive
- [ ] Clicktests + `COVERAGE.md`; responsive checks; deploy

### Later
- [ ] Explicit phase ticking, for per-phase abilities (D11)
- [ ] The sheet's own modals calling the server combat API

## 7. Open questions (round 2)

**Process**

1. **Pushing to the other repos.** The simulator's CLAUDE.md says never `git push`, and this container has no SSH key for its remote anyway. Proposal: I commit in the simulator (and gm-assistant) and you push. Does gm-assistant have the same rule?

**Generation**

2. **Exact vs base XP.** Proposal: the XP field has a "roll extra" checkbox, on by default. Typing 50 with it checked means "50 + roll"; unchecked means exactly 50. (The alternative is to infer it from "is it a multiple of 50", which is implicit.)
3. **Combat-share clamp.** Resampling the measured deviations around a target can go past 91% (e.g. a target of 85 plus the Jimen offset). Clamp to 50%-95%?
4. **Sheet migration.** Confirm that moving the sheet's own roll modals onto the new server API is a separate later project, not part of this one.
5. **Name details.** Gender: the GM picks per row, or random? Peasant or samurai: from the school (Wave Man = peasant pool?), or the GM picks? Family names for samurai NPCs: skip for now (given name only), or draw from the school's clan families?
6. **Returning NPCs.** When an archived NPC comes back, are they healed and rested (full void, no wounds)? Proposal: yes, always.
7. **Schools the simulator lacks** (Mantis Wave-Treader, Kitsune Warden, Suzume Overseer, Shugenja, Worker): unavailable as NPCs until the simulator has builds for them?

**At the table**

8. **NPC attacks a PC.** Proposal:
   - The GM picks the target PC, and the server compares against that PC's TN to be hit.
   - The player parries on their own sheet and says whether it worked; the GM clicks "parried" or "not parried".
   - The tracker rolls damage (including the failed-parry reduction from the PC's parry skill, which it knows) and shows the number for the GM to tell the player.
   - The player enters it on their sheet, which starts their wound check.
   - The tracker does **not** write wounds onto a PC. OK?
9. **PC attacks an NPC.** The GM types the PC's attack total and, if the NPC parries, clicks parry on an NPC die. On a hit, the GM types the damage; the server adds light wounds, rolls the NPC's wound check, and the GM chooses keep-LW or take-SW. Should keep-LW / take-SW instead follow the simulator's wound-check strategy automatically, with an override?
10. **Records.** Should NPC rolls go into `roll_history`, and should NPCs appear in `/api/rolls` / `/api/characters` flagged `is_npc`? gm-assistant needs NPC names from somewhere (4.5).
11. **What players see.** Nothing at all? Or, e.g., an NPC dice card in Discord with no stats, or "Bandit 3: down" on the group page?
12. **Which PCs appear.** Every non-hidden PC in the group, or does the GM choose who is in this fight?
13. **More per-card detail.** Void, TN to be hit, Dan, per-round flags? More for NPCs than for PCs is fine?
