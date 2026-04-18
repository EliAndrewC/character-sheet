# Priest

**School ID:** `priest`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, pontificate - Conviction is rollable (Water). Otherworldliness is non-rollable (passive knack, ring=None). Pontificate is rollable (Water).

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
- `app/game_data.py:1564` — school definition.
- `app/routes/pages.py` — `priest_bless_rituals` flag; `party_priests` list.
- `app/templates/character/sheet.html` — Bless buttons in the Tracking panel;
  `rollBless(title)` and `rerollImpairedTens(priest)` methods on the
  `diceRoller` Alpine component; reroll button wrapper gated on
  `formula.no_reroll_reason === 'impaired' && finalDice.some(d => d.value === 10) && partyPriests.length > 0`.

**Unit tests:**
- `test_routes.py::TestPriestBlessRituals` (flag + button rendering, priest vs non-priest)
- `test_routes.py::TestPartyPriestsContext` (party_priests includes all party priests at any Dan, excludes self, empty if no group or no priests)

**Clicktests:**
- `test_school_abilities.py::test_priest_bless_conversation_topic_rolls_2k1`
- `test_school_abilities.py::test_priest_bless_research_rolls_2k1`
- `test_school_abilities.py::test_priest_bless_buttons_have_rules_tooltips`
- `test_school_abilities.py::test_priest_bless_roll_allows_conviction_spending`
- `test_school_abilities.py::test_priest_bless_roll_offers_no_void_spending`
- `test_school_abilities.py::test_priest_bless_buttons_absent_on_non_priest`
- `test_school_abilities.py::test_priest_bless_reroll_button_shows_on_impaired_10`
- `test_school_abilities.py::test_priest_bless_reroll_button_tooltip_has_rules_text`
- `test_school_abilities.py::test_priest_bless_reroll_replaces_10s_and_updates_total`
- `test_school_abilities.py::test_priest_bless_reroll_button_hides_after_click`
- `test_school_abilities.py::test_priest_bless_reroll_button_hidden_without_party_priest`
- `test_school_abilities.py::test_priest_bless_reroll_button_hidden_when_not_impaired`

---

## 1st Dan

> Roll one extra die on precepts, any one skill, and any one type of combat roll.

**Status:** Fully implemented via technique_choices.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES` (choices are player-selected, not hardcoded).
- Server: `app/models.py` stores player choices in `technique_choices` JSON column. `app/services/dice.py:_apply_school_technique_bonus()` applies +1 rolled die for chosen skills.
- Editor UI allows selecting skills.

**Implementation:** `app/game_data.py:2167` (`first_dan_extra_die: None`), `app/models.py` (`technique_choices`), `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_extra_die`
- `test_dice.py::TestSchoolAbilities::test_flexible_first_dan_no_choice_no_bonus`

**Clicktests:**
- `test_school_abilities.py::test_priest_1st_dan_skill_selection`

---

## 2nd Dan

> You and your allies get a free raise on all rolls for which you receive an Honor bonus (bragging, precepts, and open sincerity).

**Status:** Partially implemented. The Priest's own free raise on Honor bonus rolls (bragging, precepts, open sincerity) is implemented in `dice.py:build_skill_formula()`. The "allies" part is out of scope (cross-sheet buff).
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- "Honor bonus rolls" are: bragging (gets +2*Honor), precepts (gets +2*Honor), and open sincerity (non-contested sincerity, gets +2*Honor). Contested sincerity (lying, rolled vs interrogation) does NOT qualify.

**Implementation:** `app/game_data.py:2168` (`second_dan_free_raise: None`), `app/services/dice.py:build_skill_formula()`.

**Unit tests:**
- `test_dice.py::TestSchoolAbilities::test_priest_2nd_dan_bragging_bonus`
- `test_dice.py::TestSchoolAbilities::test_priest_2nd_dan_sincerity_conditional`
- `test_dice.py::TestSchoolAbilities::test_priest_below_2nd_dan_no_bonus`

**Clicktests:**
- `test_school_abilities.py::test_priest_2nd_dan_honor_bonus_raise`

---

## 3rd Dan

> Roll X dice at the beginning of combat, where X is equal to your precepts skill. You may swap any of these dice for any rolled die on any attack, parry, wound check, or damage roll. You may swap any of these dice for any lower die on any of those types of rolls made by any ally.

**Status:** Out of scope - requires cross-sheet interaction (swapping dice into allies' rolls).

---

## 4th Dan

> Raise your current and maximum of your School's chosen Ring by 1. Raising that Ring now costs 5 fewer XP. You and your allies get a free raise on all contested rolls for which your opponent has an equal or higher skill rank.

**Status:** Partially implemented. Ring raise is fully implemented; "free raise for self and allies on contested rolls" is out of scope (cross-sheet ally buff).
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.

**Unit tests:** None.
**Clicktests:** None.

---

## 5th Dan

> You may spend the points from your Conviction knack on your allies' rolls, and your Conviction points refresh after each conversation and combat round. You may also spend these points to lower action dice in order for you or an ally to counterattack or parry.

**Status:** Partially implemented.
- **Cross-sheet spending on allies' rolls:** implemented. A 5th Dan priest in the same gaming group appears in `priest_conviction_allies` on party members' sheets, and allies can spend from the priest's pool via `POST /characters/{priest_id}/ally-conviction`. See `app/routes/pages.py` (priest discovery) and `app/routes/characters.py::ally_conviction`.
- **Per-round refresh:** implemented. The `priest_round_conviction_refresh` flag in `school_abilities` (set when dan >= 5) triggers a client-side reset of `adventure_state.conviction_used` whenever the priest rolls initiative. The refreshed pool message "Conviction pool refreshed for the new combat round" shows in the initiative result modal when the pool was not already full. See `app/templates/character/sheet.html` (`_resetPerRoundAbilities`).
- **Per-conversation refresh:** not implemented (no "conversation start" trigger exists in the UI).
- **Lower action dice to counterattack/parry:** not implemented.

**Unit tests:**
- `test_routes.py::TestInitiativePerRoundResetFlags::test_priest_5th_dan_has_round_conviction_refresh`
- `test_routes.py::TestInitiativePerRoundResetFlags::test_priest_4th_dan_does_not_have_round_conviction_refresh`
- `test_routes.py::TestPriestAllyConviction` (ally-spend endpoint suite)

**Clicktests:**
- `test_school_abilities.py::test_priest_5th_dan_initiative_refreshes_conviction`
- `test_school_abilities.py::test_priest_5th_dan_initiative_no_message_when_conviction_unspent`
- `test_school_abilities.py::test_priest_4th_dan_initiative_does_not_reset_conviction`
