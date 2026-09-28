# GM Combat Tracker and Generated NPCs - Design

Status: **requirements gathering.** Nothing is implemented. The open questions in section 6 must be answered
before Phase 1 starts. Once they are, their answers get folded into sections 3-5 and the question list shrinks.

## 1. Goal

The GM wants one screen, per gaming group, for running a fight:

- every PC in the group, with their **current initiative (action dice)**, **light wounds** and **serious wounds**, kept current as the players act on their own sheets;
- the **NPCs they are fighting** on the same screen, whose rolls the GM makes from it. The GM never rolls for PCs.

The NPCs have to be **generated**, not hand-built: "the party is fighting six Wave Men with 40-80 earned XP" should produce six usable combatants. Their builds must follow **the combat simulator's current XP progression** (`l7r/simulator`, deployed at <https://l7r-combat-sim.fly.dev/>). That repo is where questions like "when does a parry school take Air from 5 to 6" get answered, and this app must pick up its answers **without code changes here**.

The NPCs are real `Character` rows, so they go through the same rules code as PCs and no parallel rules system is needed. They are never visible to players, and they never clutter the home page.

## 2. What exists today

### In the simulator (`/host-l7r-repo/simulator`)

- **The generator:** `simulation/templates/generator.py::generate_template(school_key, total_xp, priorities=None) -> (CharacterConfig, breakdown)`.
  - It is **deterministic** and has no seed or variance knob.
  - It works at any XP, not only the pre-generated `XP_TIERS`.
- **How it spends XP:**
  - It spends `COMBAT_XP_FRACTION = 0.75` of total XP on combat, walking a per-school priority list (`simulation/templates/strategies.py::SCHOOL_PRIORITIES`) greedily.
  - It leaves the other 25% **unspent and unassigned**, which is what we want here.
  - The progression is **Python tables, not data files**.
- **Coverage:** 27 schools/professions. There are no Mantis Wave-Treader, Kitsune Warden, Suzume Overseer, Shugenja or Worker builds. Advantages and disadvantages are always empty.
- **Reuse cost:**
  - It imports cheaply (about 0.09 s; pure Python plus `pyyaml`; no Streamlit).
  - It is **not an installable package**: `pyproject.toml` has no `[project]` table.
  - The Fly site is Streamlit and has **no JSON endpoint**.
- **Its ids differ from `app/game_data.py` almost everywhere:**
  - Schools, e.g. `kakita` vs `kakita_duelist` and `monk` vs `brotherhood_of_shinsei_monk`.
  - Knacks use spaces, e.g. `"double attack"` vs `double_attack`.
  - All ten Wave Man ability names differ, e.g. `"missed attack bonus"` vs `wave_man_miss_raise`.
- **Rules conflict:** the simulator allows `(xp - 100) // 15 + 1` profession abilities, which is **4 at 150 XP**. This app allows 1 at 150 XP plus 1 every 15 XP. See Q1.

### In this app

- **No NPC concept.** The GM's NPCs are ordinary characters they own; hidden ones still appear on the GM's own index.
- **About 8 sites list characters** and each would need an NPC filter:
  - `index`, `group_summary`, `group_dark_secret_map`, `group_money` / `group_money_award`
  - `party.visible_party_members`, which feeds party effects on the sheet and in the bot
  - `/api/characters`, `/api/rolls`
  - `discord_commands.resolve_character`
- **Only initiative rolls on the server** (`roll_engine.execute_initiative` + `tracking.start_combat_round`).
  - Attack, parry and wound-check *dice* can be rolled server-side by `execute_roll`.
  - **Damage assembly and wound-check pass/fail/serious-wound math exist only in the browser**: `_dice_js.html` plus `roll_math.js`.
- **Nothing updates live.** A tab learns of another writer only through a 409 on its next save. `/api/characters` already exposes a `current` block (wounds, void, action dice, `tracking_rev`) for polling, but it is bearer-token-authed rather than session-authed.
- **Unspent XP is legal.** The sheet shows "Unspent: N" and only overspending warns.

## 3. Proposed architecture (draft - pending section 6)

### 3.1 Getting builds from the simulator: import it as a library

Options considered:

| option | picks up progression changes | cost / risk |
|---|---|---|
| **A. Install the simulator as a Python package** (git dependency, built into the Docker image) | on the next deploy of this app, **no code change here** | a small `[project]` table in the simulator's `pyproject.toml`; a deploy is still needed to pick up changes |
| B. Add a JSON endpoint to the simulator, call it over HTTP | immediately | the simulator's Fly machine must be awake mid-session (cold boot); a Streamlit app is an awkward host for an API; a second service to keep up |
| C. Re-implement the greedy loop here, read their tables | never automatically | exactly the duplication the GM wants to avoid |
| D. Read the pre-generated tier YAMLs | on deploy | only 7 XP tiers; cannot do "earned 55" |

**Recommendation: A.**
- `requirements.txt` pins the simulator to a git ref. `main` is an option, but see Q3.
- A thin adapter, `app/services/npc_generator.py`, calls `generate_template` and translates the resulting `CharacterConfig` into `Character` fields.
- **The only coupling is an id-mapping table** (schools, knacks, profession abilities, rings). A unit test walks every simulator school and fails loudly if the simulator grows a school, knack or ability this table cannot map. That makes drift a red test rather than a silently wrong NPC.
- Pull request for the simulator repo: add `[project]` metadata. Optionally, promote `COMBAT_XP_FRACTION` to a keyword argument on `generate_template` so the "how much goes on combat" knob can be tuned per encounter without forking anything. See Q5.

### 3.2 NPCs and encounters

- **NPCs are `Character` rows with `is_npc = True`**, owned by the GM, `is_hidden = True`, attached to an **encounter**. `is_npc` is a new column, so it also needs a migration entry.
- **One shared helper, e.g. `visible_to_listings()`, excludes NPCs from all ~8 listing sites.** A guard test in the spirit of `test_the_registered_set_is_exactly...` checks that every `Character` query in `routes/` goes through it.
- **A new `Encounter` model:** `id`, `gaming_group_id`, `name`, `created_at`, `status` (active / ended). NPCs point to it with `encounter_id`.
- **An encounter is created from one or more generation requests.** A request is school, count, XP range, optional name stem, and knobs (Q4/Q5). For example "6 x Wave Man, earned 40-80".
- **NPC sheets are GM-only:** `GET /characters/{id}` returns 404 for anyone else, admins included only as the GM. They are never recorded as party members, never reachable from Discord, and never included in `/api/*`. `/api/*` inclusion is Q9.
- **Ending an encounter** either deletes its NPCs or archives them. See Q7.

### 3.3 The tracker page

- **`GET /groups/{id}/combat`**, admin-only, modelled on `group_money` / the Dark Secret map.
  - PC cards: name, action dice (spent / unspent), LW, SW / max SW, current void, TN to be hit.
  - NPC cards: the same fields.
- **Live updates by polling** a new session-authed, admin-only `GET /groups/{id}/combat/state`. It returns each combatant's `tracking_rev` and current state and is polled every few seconds, with an integer compare to skip no-op redraws. It uses no SSE and no websockets (single uvicorn worker, Fly auto-stop).
- **NPC actions:** see Q10, the biggest open decision. The draft recommendation is to do it in phases:
  1. First, each NPC card opens that NPC's **real sheet** in a side panel or tab. The GM rolls with the full sheet modals and exact PC rules, with zero duplication.
  2. Later, add quick-roll buttons on the tracker itself (initiative, attack, parry, damage, wound check), backed by the server roller. This needs damage and wound-check math moved to Python with a shared case table in `tests/shared/`, per the "rules in both JS and Python" rule.
- **A "roll initiative for all NPCs" button** reuses `execute_initiative` + `start_combat_round`, the same code `/initiative` uses.

## 4. Things that deliberately stay out

- **The GM does not roll for PCs from this page.** PCs roll on their sheets or in Discord; the tracker only reads their state.
- **No player-visible NPC data.** Players do not see stats, sheets or rolls. What gets posted to Discord is Q8.
- **No new rules engine.** Every rule comes from `build_all_roll_formulas` and the existing sheet code; every build decision comes from the simulator.

## 5. Phases

Each phase ends with unit tests green at 100% coverage, targeted clicktests passing, a commit and a deploy, per `CLAUDE.md`.

### Phase 0 - Requirements (current)
- [x] Survey the simulator generator and this app's combat surfaces
- [x] Draft this document
- [ ] GM answers section 6; fold the answers into sections 3-5
- [ ] Final review of this document with the GM before any code

### Phase 1 - Simulator as a dependency
- [ ] Simulator repo: add `[project]` packaging; (maybe) `combat_xp_fraction` keyword on `generate_template`
- [ ] Add a pinned git dependency here; confirm the Docker build and the 512 MB machine are fine
- [ ] `npc_generator.py`: `CharacterConfig` -> `Character` fields, with id-mapping tables
- [ ] Guard test: every simulator school / knack / ability maps, or is explicitly listed as unsupported
- [ ] Unit tests: a few schools across the XP range produce valid characters (validation clean apart from "unspent")

### Phase 2 - NPC characters and encounters
- [ ] `is_npc`, `encounter_id` columns + migration entries; `Encounter` model
- [ ] Listing helper and filter at every listing site; guard test
- [ ] NPC sheet 404 for non-GM; no party effects; no Discord resolution; `/api` per Q9
- [ ] Suppress PC-only validation noise on NPC sheets (age, lineage, ...)
- [ ] Encounter create / end / delete routes (admin-only), generation from requests with variance per Q4

### Phase 3 - The tracker page (read-only)
- [ ] `/groups/{id}/combat` + `/combat/state` polling endpoint, admin-only
- [ ] PC and NPC cards (action dice, LW, SW / max, void, TN to hit)
- [ ] Encounter builder UI on the page
- [ ] Clicktests + `COVERAGE.md`; responsive checks

### Phase 4 - GM acting for NPCs
- [ ] Per Q10: side-panel NPC sheet (first) and / or tracker quick-rolls
- [ ] Roll-initiative-for-all-NPCs
- [ ] Applying damage to an NPC (LW entry -> wound check)

### Phase 5 - Later / maybe
- [ ] Server-side damage + wound-check math with `tests/shared/` case tables (only if Q10 needs it)
- [ ] Phase / turn order view (Q11)
- [ ] Variance knobs beyond XP range (Q5)

## 6. Open questions for the GM

**Rules and the simulator**

1. **Profession ability count conflict.** Simulator: `(xp - 100) // 15 + 1` gives 4 abilities at 150 XP and 14 at 300. This app: 1 at 150 XP, then 1 every 15 XP. Which is right? The wrong one should be fixed in its own repo, not papered over here.
2. **XP meaning.** "A Wave Man with 50 earned XP" means `generate_template(total_xp = 150 + 50)`, correct? And the range you give me is always *earned* XP?
3. **How current is "latest"?** Is "the progression in effect as of this app's last deploy" good enough, or must a push to the simulator reach live NPC generation with no redeploy here? The second pushes us to option B (an HTTP service) and its cold-boot problem.

**Generation and variance**

4. **Variance, v1.** Proposal: each NPC in a group draws its own XP uniformly from the range, and the build is otherwise the simulator's deterministic one. Is that enough to start with?
5. **Tuning knobs.** You mentioned "what percentage of XP goes to skills". Should the combat fraction (simulator default 75%) be a per-encounter knob? Any others, such as "sometimes swap two adjacent priorities" via the simulator's `variants.py` transforms?
6. **Schools the simulator lacks** (Mantis Wave-Treader, Kitsune Warden, Suzume Overseer, Shugenja, Worker): leave them unavailable as NPCs until the simulator has builds for them?
7. **NPC lifetime.** When an encounter ends, delete its NPCs, or archive them so a recurring villain can reappear? Should a generated NPC ever be "promoted" to a permanent, hand-editable GM character?
8. **Names.** Auto-name them ("Wave Man 1..6"), let you supply a stem ("Bandit"), or both?

**Visibility**

9. **The GM API and gm-assistant.** Should NPCs appear in `/api/characters` and `/api/rolls` (flagged `is_npc`), or be invisible there too? Should their rolls be recorded in `roll_history` at all?
10. **How you act for an NPC** (the biggest decision). (a) Open the NPC's full sheet in a panel, so every rule is already there. (b) Compact quick-roll buttons on the tracker, which is faster at the table but needs damage and wound-check math ported to Python. (c) (a) first, then (b). Recommendation: (c).
11. **Turn order.** Do you want the tracker to show the round as phases 1-10, with who acts in each phase and a "current phase" pointer? Or is a table of each combatant's action dice enough to start?
12. **What players see.** Anything? For example, nothing at all; or an NPC's roll posted to the Discord channel as a card with no stats; or "Bandit 3: Heavily Wounded" descriptors on the group page.
13. **Which PCs are on the tracker.** Every non-hidden PC in the group, or do you pick who is in this fight?
14. **Beyond LW / SW / initiative.** Void points, TN to be hit, Dan, per-round flags (e.g. a Mantis's state)? Is showing more for NPCs than for PCs fine?
