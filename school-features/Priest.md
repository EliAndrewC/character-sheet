# Priest

**School ID:** `priest`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, pontificate - Conviction is rollable (Water). Otherworldliness is non-rollable (passive knack, ring=None). Pontificate is rollable with whichever of Water or Air is higher at roll time.

---

## Special Ability

> You have all 10 rituals listed under the Priest profession.

**Status:** Mostly narrative; three of the rituals are exposed mechanically.
The remaining 7 stay narrative.

Mechanical rituals:

1. **Bless conversation topic** (2k1) — button on the Priest's own sheet
   (Tracking panel). Opens the dice modal with a 2k1 formula and a
   ritual-specific title. Conviction may be spent; void may not (roll menu is
   bypassed). Gated by `priest_bless_rituals` in `school_abilities`.
2. **Bless research** (2k1) — same shape as above, different title + tooltip.
3. **Sick-or-impaired ritual** (reroll) — shown on the **target's** sheet, not
   the priest's. When the target's Impaired 10-not-rerolled note appears and
   there is at least one priest in the target's gaming group (any Dan), a
   button "<priest name> priest blessed for 10 rerolls" appears beside the
   note. Clicking it rerolls the Impaired 10s (new dice explode normally) and
   updates finalDice / keptSum / baseTotal. Discretionary spends already made
   on the roll (raises, Conviction, Mirumoto round points, Shosuro 5th Dan
   lowest-3) carry through; Shosuro lowest-3 is recomputed against the new
   pool. The list of priests is exposed via the `party_priests` context var
   (populated from `party_chars` with `p.school == "priest"`), excluding the
   character themselves.

**Implementation:**
- `app/game_data.py` — school definition.
- `app/routes/pages.py` — `priest_bless_rituals` flag; `party_priests` list.
- `app/templates/character/sheet.html` — Bless buttons in the Tracking panel;
  `rollBless(title)` and `rerollImpairedTens(priest)` methods on the
  `diceRoller` Alpine component; reroll button wrapper gated on
  `formula.no_reroll_reason === 'impaired' && finalDice.some(d => d.value === 10) && partyPriests.length > 0`.

---

## 1st Dan

> Roll one extra die on precepts, any one skill, and any one type of combat roll.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

---

## 2nd Dan

> You and your allies get a free raise on rolls for which you receive an Honor bonus (bragging, precepts, and open sincerity).

**Status:** Partially implemented. The Priest's own free raise on Honor bonus rolls (bragging, precepts, open sincerity) is implemented in `dice.py:build_skill_formula()`. The "allies" part is out of scope (cross-sheet buff).
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- "Honor bonus rolls" are: bragging (gets +2*Honor), precepts (gets +2*Honor), and open sincerity (non-contested sincerity, gets +2*Honor). Contested sincerity (lying, rolled vs interrogation) does NOT qualify.

**Implementation:** `app/game_data.py` (`second_dan_free_raise: None`), `app/services/dice.py:build_skill_formula()`.

---

## 3rd Dan

> Roll X dice at the beginning of combat, where X is your precepts skill.  You may swap any of these dice for any rolled die on any attack, parry, wound check, or damage roll.  You may swap any of these dice for any lower die on any of those types of rolls made by any ally.

**Status:** Fully implemented.

Mechanics:
- **Pool storage** lives on the Character model as a JSON column
  `precepts_pool` (`[{"value": int}, ...]`). Migration in `database.py::_migrate_add_columns`.
- **Pool creation** is manual: a "Roll Pool" button in the Tracking panel
  rolls X dice (X = precepts skill rank), all kept, 10s reroll on. The
  resulting values are stored as the pool.
- **Pool persistence:** pool survives combat ends and page reloads. NOT
  wiped by the action-dice "Clear" button or by rolling initiative. IS
  wiped by the per-adventure Reset modal (listed as "Clear precepts pool
  (N dice)"). IS wiped server-side in `publish_character` /
  `revert_character` if a knack change drops the priest below 3rd Dan;
  `/track` defensively coerces to `[]` if a stale tab tries to persist a
  non-priest / sub-3rd-Dan pool.
- **Party broadcast:** `priest_precepts_allies` context mirrors the 5th
  Dan `priest_conviction_allies`. Filters: priest school, dan >= 3,
  non-empty pool, shared gaming group, excludes self.
- **Display:** pool renders as dice icons inside the discretionary-bonus
  area of four roll modals (generic dice-roller for parry/athletics:parry,
  attack, damage, wound-check). The `_isPreceptsPoolQualifyingRoll(modal)`
  helper uses `formula.is_attack_type` to distinguish Kakita's combat
  iaijutsu (qualifying) from iaijutsu-duel knack rolls (not qualifying).
- **Swap UI:** clicking a pool die opens a dropdown of eligible rolled
  values ("Swap with a rolled N"). Eligibility is strict `pool_die >
  rolled_die` for both self and ally (equal is a no-op, excluded).
  Dedup across same-value rolled dice. Empty eligible set shows a
  disabled "No lower rolled dice to swap with" entry.
- **Swap effect:** replaces the chosen rolled-die value in `finalDice`
  with the pool die value, puts the replaced rolled value back into
  the pool, re-keeps top-N, propagates the keptSum delta to `baseTotal`
  and whichever modal-specific total is active (`atkRollTotal`,
  `atkDamageTotal`, `wcRollTotal`), appends a structured
  `preceptsPoolSwapBonuses` entry (rendered as `+N (swapped rolled X -> Y)`
  under the pool block), and persists: self via `/track`, ally via
  `POST /characters/{priest_id}/precepts-pool`.

**Implementation:**
- `app/models.py` — `precepts_pool` column on `Character`.
- `app/database.py::_migrate_add_columns` — migration entry.
- `app/routes/characters.py::_sanitize_precepts_pool`,
  `/track` handler (accepts + sanitizes + defensive dan-check),
  `POST /characters/{char_id}/precepts-pool` (swap endpoint).
- `app/routes/pages.py` — `priest_precepts_pool` /
  `priest_precepts_pool_size` flags in `school_abilities`;
  `priest_precepts_allies` context list.
- `app/services/versions.py::_wipe_precepts_pool_if_dan_drop` — called
  from `publish_character` and `revert_character`.
- `app/templates/character/sheet.html` — Alpine state
  (`preceptsPool`, `priestPreceptsAllies`, `preceptsPoolMenuOpen`,
  `preceptsPoolSwapBonuses`); methods
  `rollPreceptsPool`, `clearPreceptsPool`,
  `_isPreceptsPoolQualifyingRoll`, `preceptsPoolAlliesForThisRoll`,
  `preceptsSwapOptions`, `swapPreceptsDie`,
  `_postPreceptsPoolReplace`, `_preceptsActiveModal`,
  `_preceptsModalKeptCount`; `precepts_pool_block` Jinja macro;
  `precepts-pool-section` UI in the Tracking panel;
  pool block wired into all four roll-result modals.

---

## 4th Dan

> Raise your current and maximum School Ring by 1.  Raising your School Ring now costs 5 fewer XP.  You and your allies get a free raise on contested rolls for which your opponent has an equal or higher skill rank.

**Status:** Partially implemented. Ring raise is fully implemented; "free raise for self and allies on contested rolls" is out of scope (cross-sheet ally buff).
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.

---

## 5th Dan

> You may spend the points from your conviction knack on your allies' rolls, and your conviction points refresh after each conversation and combat round.

**Status:** Partially implemented.
- **Cross-sheet spending on allies' rolls:** implemented. A 5th Dan priest in the same gaming group appears in `priest_conviction_allies` on party members' sheets, and allies can spend from the priest's pool via `POST /characters/{priest_id}/ally-conviction`. See `app/routes/pages.py` (priest discovery) and `app/routes/characters.py::ally_conviction`.
- **Per-round refresh:** implemented. The `priest_round_conviction_refresh` flag in `school_abilities` (set when dan >= 5) triggers a client-side reset of `adventure_state.conviction_used` whenever the priest rolls initiative. The refreshed pool message "Conviction pool refreshed for the new combat round" shows in the initiative result modal when the pool was not already full. See `app/templates/character/sheet.html` (`_resetPerRoundAbilities`).
- **Per-conversation refresh:** not implemented (no "conversation start" trigger exists in the UI).
- **Lower action dice to counterattack/parry:** not implemented.

