# E2E Clicktest Feature Coverage

Every interactive UI feature should have at least one clicktest. This file tracks coverage.
When adding a feature, add lines here first (marked `[ ]`). After writing the clicktest, mark `[x]` with the test reference.

---

## Known Flaky / Failing Tests (2026-04-19)

The full e2e suite (`pytest tests/e2e/ --browser chromium`) finished with **739 passed, 11 failed, 3 skipped, 2 xpassed** at the end of the Mantis Wave-Treader rollout. One failure was a Mantis test-fixture race and was fixed inline (`test_mantis_wc_probability_all_three_stack` - replaced a snapshot `text_content()` check with `page.wait_for_function` so Alpine's re-render can drain). The remaining 10 failures are **pre-existing on `main`** - they also fail on a clean checkout with the Mantis uncommitted changes stashed - and need their own follow-up fixes.

All 10 are grouped below with the failing assertion and a best-guess root cause / suggested fix so they can be triaged in a later coding session.

### Togashi Ise Zumi — "Spend Athletics Raise" button ambiguous locator (6 tests)

- **`test_school_abilities.py::test_togashi_3rd_dan_athletics_raises`** — `Locator.is_visible: strict mode violation: locator("button:has-text(\"Spend Athletics Raise\")") resolved to 3 elements`.
- **`test_school_abilities.py::test_togashi_athletics_raise_on_athletics_parry`** — same strict-mode violation reached via `Locator.click` timeout.
- **`test_school_abilities.py::test_togashi_athletics_raise_on_athletics_attack_hit`** — same.
- **`test_school_abilities.py::test_togashi_athletics_raise_atk_undo_restores_total_and_pool`** — same.
- **`test_school_abilities.py::test_togashi_athletics_raise_button_absent_on_regular_attack`** — same.
- **`test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_athletics_parry`** — click timeout, same ambiguous-locator family.

**Root cause:** the sheet now renders the "Spend Athletics Raise" button in three separate places (attack-modal HIT branch at `sheet.html:~3167`, attack-modal MISS branch at `~3369`, and the dice-roller post-roll panel at `~4254`). Each has its own `data-action="spend-togashi-raise(-atk)?"` marker, but the tests still use a text-based locator that matches all three. Playwright 1.58's strict mode now fails the first time any such text locator is accessed.

**Suggested fix:** update each test's locator from `button:has-text("Spend Athletics Raise")` to the specific `[data-action="spend-togashi-raise"]` (dice-roller) or `[data-action="spend-togashi-raise-atk"]` (attack modal) selector, scoped through `page.locator('[data-modal="..."]')` where appropriate.

### Togashi Ise Zumi — 4th Dan reroll cleanup (1 test)

- **`test_school_abilities.py::test_togashi_4th_dan_reroll_only_once_per_roll`** — after the first reroll is used, `button:has-text("Reroll (Togashi 4th Dan)")` remains visible. `AssertionError: Reroll button should be hidden after first use`.

**Root cause:** either the `togashiRerollUsed` flag isn't being set on the path the test exercises, or the button's `x-show` condition regressed during the recent action-die refactor. Most likely the latter — the action-die rewrite around `setActionDice` / `spendLowestUnspentActionDie` touched adjacent state.

**Suggested fix:** open the sheet as a Togashi 4th Dan character, drive a contested roll manually, click Reroll once, and inspect `window.Alpine.$data(dicerollerEl).togashiRerollUsed` vs the button's `x-show` expression. Likely one-line fix in `sheet.html` to keep the flag consistent.

### Tracking Advanced — per-day reset button layout (1 test)

- **`test_tracking_advanced.py::test_per_day_reset_button_renders_left_of_counter`** — `Locator.text_content: strict mode violation: locator("text=\"Conviction\"").locator("..").locator("..") resolved to 3 elements` (reset-ability row, XP breakdown row, school knacks panel).

**Root cause:** the word "Conviction" appears in at least three distinct DOM subtrees. The test's `text="Conviction"` locator matches all of them and then `.locator("..").locator("..")` climbs ambiguous parents.

**Suggested fix:** replace the text locator with a scope anchored on `[data-action="reset-ability-conviction"]` (already used elsewhere in the same test) and climb from there, or use `page.get_by_text("Conviction", exact=True).nth(0)` with a comment explaining which occurrence is intended.

### Tracking Advanced — per-adventure reset summary excludes action dice (1 test)

- **`test_tracking_advanced.py::test_per_adventure_reset_also_clears_action_dice`** — `assert "2 action dice" in body` fails; the full-body `text_content()` never includes that literal after opening the reset modal.

**Root cause:** the test assigns `window._trackingBridge.actionDice = [...]` **directly** (not via `setActionDice`). Direct property-set *does* trigger Alpine reactivity, so that's not the issue. `resetSummary()` in `sheet.html:661` does push `"Clear ${n} action die(ce)"` when `actionDice.length > 0`. So the summary string literally contains `"2 action dice"`. The reason it's missing from the body text is probably that the reset modal's `x-show` is gated on `hasAnythingSpent()` — and that method walks `perAdventure` plus checks `actionDice.length`. On a fresh Togashi 3rd Dan (precepts=1) the default conviction counter may not fire `setCount('conviction', 1)` cleanly if `conviction` isn't in the computed `perAdventure` list. Worth checking what `schoolAbilities.priest_round_conviction_refresh` / `convictionConfig.rank` end up as for a 3rd Dan Togashi — the test assumes the conviction counter is present, but it may not be.

**Suggested fix:** before asserting, dump the reset modal's rendered HTML and confirm the `<template x-for="item in resetSummary()">` actually emitted any `<li>` items. If the modal opens with an empty summary, swap the conviction setCount to a counter that's guaranteed to exist on this character (e.g. use a school that gives a per-adventure counter Dan 1+). Alternatively, decouple the test from the counter requirement by opening the modal via a dedicated "reset action dice only" path if one exists.

### Character Art Display — test isolation leak (1 test)

- **`test_character_art_display.py::test_list_page_shows_headshot_for_character_with_art`** — `assert placeholders.count() == 1` fails with `36 == 1`. The test creates two characters (one with art, one without) and expects exactly one placeholder on the index page, but the index is cluttered with 36 characters left over from prior tests in the session.

**Root cause:** the `live_server_url` fixture creates one SQLite DB per test session, not per test. Clicktests that create characters accumulate state.

**Suggested fix:** either scope the test to characters created in *this* test (e.g. filter by owner display name via a test-only query), or tighten the fixture to per-test isolation. A per-test DB is expensive; the cheaper path is to assert on specific character cards rather than on the aggregate count.

---

## Navigation (base.html)

- [x] Homepage loads → `test_smoke.py::test_homepage_loads`
- [x] "New Character" button creates character and redirects to edit → `test_create_character.py::test_create_and_edit_character`
- [x] Create minimal character → `test_create_character.py::test_create_minimal_character`
- [x] Profile link navigates to /profile → `test_profile_e2e.py::test_profile_loads`
- [x] Logout link visible and points to /auth/logout → `test_navigation.py::test_logout_link_exists`
- [x] Login link visible when anonymous → `test_navigation.py::test_login_link_visible_when_anonymous`
- [x] Test-login URL returns 403 without valid token → `test_navigation.py::test_test_login_creates_session`

## Wound Check

- [x] Button visible when light wounds > 0 → `test_wound_check.py::test_wound_check_button_visible_with_light_wounds`
- [x] Button hidden when light wounds = 0 → `test_wound_check.py::test_wound_check_button_hidden_with_zero_wounds`
- [x] Pre-roll modal opens with probability table → `test_wound_check.py::test_wound_check_modal_opens`
- [x] Modal shows TN matching light wound total → `test_wound_check.py::test_wound_check_modal_shows_tn`
- [x] Dice animation visible during wound check roll → `test_wound_check.py::test_wound_check_shows_dice_animation`
- [x] Result shows PASSED or FAILED → `test_wound_check.py::test_wound_check_result_shows_pass_or_fail`
- [x] Pass shows Keep/Take buttons → `test_wound_check.py::test_wound_check_pass_shows_keep_and_take_buttons`
- [x] Take 1 Serious resets light wounds to 0 → `test_wound_check.py::test_wound_check_take_serious_resets_light`
- [x] Iaijutsu strike wound check button present → `test_wound_check.py::test_iaijutsu_strike_wound_check_available`
- [x] Regular roll also shows dice animation → `test_wound_check.py::test_regular_roll_shows_dice_animation`
- [x] Accept Result button applies wound check failure -> `test_ui_interactions.py::test_wc_accept_result_applies_failure`
- [x] Keep Light Wounds closes modal without changes -> `test_ui_interactions.py::test_wc_keep_light_wounds_closes`
- [x] Take 1 Serious Wound adds SW and resets LW -> `test_ui_interactions.py::test_wc_take_serious_resets_and_adds_sw`
- [x] Post-roll VP spend (+5) on wound check -> `test_ui_interactions.py::test_wc_post_roll_vp_spend`
- [x] Post-roll VP spend with worldliness VP and undo -> `test_ui_interactions.py::test_wc_post_roll_vp_with_worldliness`

## Attack Modal

- [x] Attack opens attack modal (not dice roller) -> `test_attack_modal.py::test_attack_opens_attack_modal`
- [x] Feint does NOT open attack modal -> `test_attack_modal.py::test_feint_does_not_open_attack_modal`
- [x] Parry does NOT open attack modal -> `test_attack_modal.py::test_parry_does_not_open_attack_modal`
- [x] Probability table with Hit % column -> `test_attack_modal.py::test_attack_modal_shows_probability_table`
- [x] TN dropdown shows common values -> `test_attack_modal.py::test_attack_modal_tn_dropdown`
- [x] Attack roll shows HIT or MISSED -> `test_attack_modal.py::test_attack_roll_shows_hit_or_miss`
- [x] Hit shows Make Damage Roll button -> `test_attack_modal.py::test_attack_hit_shows_damage_roll_button`
- [x] Dice animation visible during attack roll -> `test_attack_modal.py::test_attack_dice_animation_visible`
- [x] Attack probability table shows "Attack Roll" column with (r)k(k) values per void level -> `test_attack_modal.py::test_attack_modal_shows_attack_roll_rk_column`
- [x] Damage roll produces result after hit -> `test_attack_modal.py::test_attack_damage_roll_produces_result`
- [x] Lucky button on regular roll (present/absent) -> `test_ui_interactions.py::test_lucky_on_regular_roll`, `test_no_lucky_on_regular_roll_without_advantage`
- [x] Lucky button on attack result (present/absent) -> `test_ui_interactions.py::test_lucky_reroll_on_attack`, `test_no_lucky_on_attack_without_advantage`
- [x] Lucky button on damage result (present) -> `test_ui_interactions.py::test_lucky_reroll_on_damage`
- [x] Lucky button on wound check result (present/absent) -> `test_ui_interactions.py::test_lucky_reroll_on_wound_check`, `test_no_lucky_on_wound_check_without_advantage`
- [x] Lucky reroll carries over free raise (attack) -> `test_ui_interactions.py::test_lucky_carries_over_free_raise_attack`
- [x] Lucky reroll carries over free raise (wound check) -> `test_ui_interactions.py::test_lucky_carries_over_free_raise_wc`
- [x] Lucky reroll carries over post-roll VP (wound check) -> `test_ui_interactions.py::test_lucky_carries_over_wc_post_roll_vp`
- [x] Lucky reroll carries over Akodo banked bonus -> `test_ui_interactions.py::test_lucky_carries_over_akodo_bonus`
- [x] Lucky prev total updates reactively with post-reroll bonuses -> `test_ui_interactions.py::test_lucky_prevtotal_updates_with_post_reroll_bonus`
- [x] Failed parry checkbox changes damage formula -> `test_ui_interactions.py::test_failed_parry_checkbox`
- [x] Predeclared parry rolls with +5 bonus -> `test_ui_interactions.py::test_predeclared_parry_with_bonus`

## Iaijutsu Duel

- [x] Iaijutsu Duel option in roll menu -> `test_iaijutsu_duel.py::test_duel_option_in_iaijutsu_menu`
- [x] Duel modal opens with setup phase -> `test_iaijutsu_duel.py::test_duel_modal_opens_with_setup`
- [x] Player TN computed from XP -> `test_iaijutsu_duel.py::test_duel_player_tn_computed`
- [x] Contested roll proceeds after entering opponent XP -> `test_iaijutsu_duel.py::test_contested_roll_proceeds`
- [x] Contested roll shows result -> `test_iaijutsu_duel.py::test_contested_roll_shows_result`
- [x] Focus/Strike buttons appear after contested -> `test_iaijutsu_duel.py::test_focus_strike_phase_shows_buttons`
- [x] Focus alternation enforced -> `test_iaijutsu_duel.py::test_focus_alternation`
- [x] Strike shows dice animation -> `test_iaijutsu_duel.py::test_strike_shows_dice_animation`
- [x] Strike hit shows Roll Damage button -> `test_iaijutsu_duel.py::test_duel_strike_hit_shows_damage_button`
- [x] Strike shows opponent roll input -> `test_iaijutsu_duel.py::test_duel_strike_shows_opponent_input`
- [x] Opponent hit shows damage input -> `test_iaijutsu_duel.py::test_duel_opponent_hit_shows_damage_input`
- [x] Opponent hit shows player TN reference -> `test_iaijutsu_duel.py::test_duel_opponent_hit_shows_player_tn`
- [x] Opponent wound check opens from duel -> `test_iaijutsu_duel.py::test_duel_opponent_wound_check_opens`
- [x] Duel setup shows Katana (4k2) default -> `test_iaijutsu_duel.py::test_duel_katana_weapon_default`
- [x] Duel restart when both miss resets TNs -> `test_ui_interactions.py::test_duel_restart_resets_tns`

## UI Interactions (cross-cutting)

- [x] Account-level sharing allows edit access -> `test_permissions.py::test_granted_user_can_access_edit_page`
- [x] Akodo banked bonus Apply button works on MISS -> `test_ui_interactions.py::test_akodo_banked_bonus_on_miss`
- [x] Akodo Undo button stays visible after all bonuses spent -> `test_ui_interactions.py::test_akodo_undo_visible_after_all_bonuses_spent`
- [x] Akodo banked bonuses display reactively in tracking -> `test_ui_interactions.py::test_akodo_banked_bonuses_display_in_tracking`
- [x] Akodo banked bonuses persist across page refresh -> `test_ui_interactions.py::test_akodo_banked_bonuses_persist_on_refresh`
- [x] Reset per-adventure clears all combat bonuses -> `test_ui_interactions.py::test_reset_adventure_clears_combat_bonuses`

## School-Specific Abilities

### Akodo Bushi

- [x] Feint roll adds temp VP -> `test_school_abilities.py::test_akodo_feint_temp_vp`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_akodo_1st_dan_behavioral`
- [x] 2nd Dan behavioral wound check bonus -> `test_school_abilities.py::test_akodo_2nd_dan_behavioral`
- [x] 3rd Dan wound check banks bonus for next attack -> `test_school_abilities.py::test_akodo_3rd_dan_bank_and_apply_behavioral`
- [x] 4th Dan Spend VP (+5) on passed wound check -> `test_school_abilities.py::test_akodo_4th_dan_vp_on_passed_wound_check`
- [x] 4th Dan Spend VP (+5) on failed wound check -> `test_school_abilities.py::test_akodo_4th_dan_vp_on_failed_wound_check`
- [x] 5th Dan reflect damage UI elements appear -> `test_school_abilities.py::test_akodo_5th_dan_reflect_damage_ui`
- [x] 5th Dan reflect damage behavioral flow -> `test_school_abilities.py::test_akodo_5th_dan_reflect_ui_behavioral`

### Bayushi Bushi

- [x] 3rd Dan feint damage button visible -> `test_school_abilities.py::test_bayushi_feint_damage_button`
- [x] Feint temp VP button for Bayushi -> `test_school_abilities.py::test_feint_temp_vp_button_for_bayushi`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_bayushi_1st_dan_behavioral`
- [x] 2nd Dan behavioral double attack bonus -> `test_school_abilities.py::test_bayushi_2nd_dan_behavioral`
- [x] 3rd Dan feint shows damage output -> `test_school_abilities.py::test_bayushi_3rd_dan_feint_shows_damage`
- [x] 4th Dan post-feint free raise -> `test_school_abilities.py::test_bayushi_4th_dan_post_feint_raise`
- [x] 4th Dan banked raises tracking, persist, and mark spent -> `test_school_abilities.py::test_bayushi_banked_raises_tracking_and_persist`
- [x] 3rd Dan feint damage formula shows VP-adjusted values -> `test_school_abilities.py::test_bayushi_feint_damage_formula_shows_vp`
- [x] 5th Dan half light wounds on wound check failure -> `test_school_abilities.py::test_bayushi_5th_dan_half_lw_behavioral`
- [x] Below 5th Dan does NOT use half-LW calculation -> `test_school_abilities.py::test_bayushi_below_5th_dan_no_half_lw`
- [x] 5th Dan probability table reflects halved LW for SW columns -> `test_school_abilities.py::test_bayushi_5th_dan_prob_table_shows_half_lw`
- [x] Below 5th Dan probability table has no halved note -> `test_school_abilities.py::test_bayushi_below_5th_dan_prob_table_no_half_note`
- [x] VP spending for bonus damage dice on attack -> `test_school_abilities.py::test_bayushi_vp_damage_behavioral`

### Brotherhood

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_brotherhood_1st_dan_behavioral`
- [x] 2nd Dan behavioral attack bonus -> `test_school_abilities.py::test_brotherhood_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on precepts -> `test_school_abilities.py::test_brotherhood_3rd_dan_precepts_raises`
- [x] Unarmed damage bonus behavioral -> `test_school_abilities.py::test_brotherhood_unarmed_damage_behavioral`

### Courtier

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_courtier_1st_dan_behavioral`
- [x] 2nd Dan behavioral manipulation bonus -> `test_school_abilities.py::test_courtier_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on tact -> `test_school_abilities.py::test_courtier_3rd_dan_tact_raises`
- [x] 4th Dan temp VP after successful roll -> `test_school_abilities.py::test_courtier_4th_dan_temp_vp`
- [x] Air ring bonus on attack rolls -> `test_school_abilities.py::test_courtier_air_attack_behavioral`
- [x] 5th Dan Air skill behavioral bonus -> `test_school_abilities.py::test_courtier_5th_dan_air_skill_behavioral`
- [x] 5th Dan wound check includes +Air -> `test_school_abilities.py::test_courtier_5th_dan_wc_bonus`
- [x] Below 5th Dan no wound check bonus -> `test_school_abilities.py::test_courtier_below_5th_dan_no_wc_bonus`
- [x] 5th Dan always-TN skill (sneaking) auto-bonus -> `test_school_abilities.py::test_courtier_5th_dan_always_skill_has_bonus`
- [x] 5th Dan never-TN skill (etiquette) no bonus -> `test_school_abilities.py::test_courtier_5th_dan_never_skill_no_bonus`
- [x] 5th Dan sheet display says "5th Dan" without "(Air)" -> `test_school_abilities.py::test_courtier_5th_dan_sheet_display`
- [x] 5th Dan sometimes-TN skill (bragging) checkbox -> `test_school_abilities.py::test_courtier_5th_dan_sometimes_skill_checkbox`
- [x] Oppose Social roll shows penalty to target's Air rolls -> `test_school_abilities.py::test_oppose_social_roll_shows_penalty`

### Daidoji

- [x] Counterattack school flag set on sheet -> `test_school_abilities.py::test_daidoji_counterattack_school_flag`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_daidoji_1st_dan_behavioral`
- [x] 2nd Dan behavioral counterattack bonus -> `test_school_abilities.py::test_daidoji_2nd_dan_behavioral`
- [x] 3rd Dan counterattack raises note displayed -> `test_school_abilities.py::test_daidoji_3rd_dan_raises_note_behavioral`
- [x] 3rd Dan counterattack checkbox on wound check applies bonus -> `test_school_abilities.py::test_daidoji_3rd_dan_counterattack_checkbox`
- [x] Below 3rd Dan no counterattack checkbox -> `test_school_abilities.py::test_daidoji_below_3rd_dan_no_counterattack_checkbox`
- [x] Non-Daidoji party member sees counterattack checkbox with name -> `test_school_abilities.py::test_non_daidoji_with_party_counterattack_checkbox`
- [x] 5th Dan wound check attacker TN reduction note -> `test_school_abilities.py::test_daidoji_5th_dan_tn_note_behavioral`

### Doji

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_doji_1st_dan_behavioral`
- [x] 2nd Dan behavioral manipulation bonus -> `test_school_abilities.py::test_doji_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on culture -> `test_school_abilities.py::test_doji_3rd_dan_culture_raises`
- [x] 5th Dan always-TN skill shows input directly -> `test_school_abilities.py::test_doji_5th_dan_always_tn_skill_input`
- [x] 5th Dan sometimes-TN skill shows checkbox then input -> `test_school_abilities.py::test_doji_5th_dan_sometimes_tn_skill_checkbox`
- [x] 5th Dan never-TN skill shows no input/checkbox -> `test_school_abilities.py::test_doji_5th_dan_never_tn_skill_no_input`
- [x] 5th Dan attack auto-applies bonus from TN -> `test_school_abilities.py::test_doji_5th_dan_attack_auto_bonus`
- [x] 5th Dan wound check auto-applies bonus from LW -> `test_school_abilities.py::test_doji_5th_dan_wound_check_auto_bonus`

### Hida

- [x] 3rd Dan reroll selection UI appears -> `test_school_abilities.py::test_hida_reroll_selection_appears`
- [x] 4th Dan trade SW button works -> `test_school_abilities.py::test_hida_trade_sw_button_works`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_hida_1st_dan_behavioral`
- [x] 2nd Dan behavioral counterattack bonus -> `test_school_abilities.py::test_hida_2nd_dan_behavioral`
- [x] 3rd Dan reroll option on counterattack/attack -> `test_school_abilities.py::test_hida_3rd_dan_reroll_appears`
- [x] 4th Dan trade SW for light wound reset behavioral -> `test_school_abilities.py::test_hida_4th_dan_trade_sw_behavioral`
- [x] 5th Dan counterattack excess banked for wound check bonus -> `test_school_abilities.py::test_hida_5th_dan_counterattack_wc_bonus`
- [x] Below 5th Dan does NOT bank counterattack excess -> `test_school_abilities.py::test_hida_below_5th_dan_no_counterattack_wc_bonus`

### Hiruma

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_hiruma_1st_dan_behavioral`
- [x] 2nd Dan behavioral parry bonus -> `test_school_abilities.py::test_hiruma_2nd_dan_behavioral`
- [x] 3rd Dan post-parry bonus triggers attack behavioral -> `test_school_abilities.py::test_hiruma_3rd_dan_parry_then_attack_behavioral`
- [x] 4th Dan initiative shows action dice note -> `test_school_abilities.py::test_hiruma_4th_dan_initiative_note_behavioral`
- [x] 5th Dan parry note displayed -> `test_school_abilities.py::test_hiruma_5th_dan_parry_note`

### Ide

- [x] 1st Dan skill selection dropdown -> `test_school_abilities.py::test_ide_1st_dan_skill_selection`
- [x] 2nd Dan skill selection dropdown -> `test_school_abilities.py::test_ide_2nd_dan_skill_selection`
- [x] 3rd Dan subtract-from-roll button opens modal with dice animation and roll results -> `test_school_abilities.py::test_ide_3rd_dan_subtract_behavioral`
- [x] Subtract button visible on applicable rolls -> `test_school_abilities.py::test_ide_subtract_button_visible`
- [x] 4th Dan VP regen +2/night displayed -> `test_school_abilities.py::test_ide_4th_dan_vp_regen_note_behavioral`
- [x] 4th Dan VP regen tooltip explains extra +1 -> `test_school_abilities.py::test_ide_4th_dan_regen_tooltip`
- [x] 5th Dan temp VP granted on VP spend -> `test_school_abilities.py::test_ide_5th_dan_temp_vp_on_spend`
- [x] 5th Dan temp VP granted on subtract button VP spend -> `test_school_abilities.py::test_ide_5th_dan_subtract_grants_temp_vp`
- [x] 3rd Dan subtract spends temp VP before regular VP -> `test_school_abilities.py::test_ide_3rd_dan_subtract_spends_temp_vp`
- [x] 3rd Dan subtract enabled with only temp VP -> `test_school_abilities.py::test_ide_3rd_dan_subtract_enabled_with_only_temp_vp`
- [x] 3rd Dan subtract spends worldliness VP when regular and temp are 0 -> `test_school_abilities.py::test_ide_3rd_dan_subtract_spends_worldliness_vp`
- [x] 3rd Dan subtract disabled when all VP types exhausted -> `test_school_abilities.py::test_ide_3rd_dan_subtract_disabled_all_vp_exhausted`
- [x] Feint banks TN reduction for next attack -> `test_school_abilities.py::test_ide_feint_banks_tn_reduce`

### Ikoma

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_ikoma_1st_dan_behavioral`
- [x] 2nd Dan behavioral attack bonus -> `test_school_abilities.py::test_ikoma_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on bragging -> `test_school_abilities.py::test_ikoma_3rd_dan_bragging_raises`
- [x] 4th Dan 10-dice floor note on unparried damage -> `test_school_abilities.py::test_ikoma_4th_dan_10dice_note_behavioral`
- [x] 4th Dan attack modal shows 10-dice floor reminder -> `test_school_abilities.py::test_ikoma_4th_dan_attack_modal_note`
- [x] Oppose Knowledge roll shows penalty to target's Water rolls -> `test_school_abilities.py::test_oppose_knowledge_roll_shows_penalty`

### Isawa Duelist

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_isawa_duelist_1st_dan_behavioral`
- [x] 2nd Dan behavioral wound check bonus -> `test_school_abilities.py::test_isawa_duelist_2nd_dan_behavioral`
- [x] 3rd Dan TN trade toggle UI -> `test_school_abilities.py::test_isawa_duelist_3rd_dan_tn_trade_toggle`
- [x] Water ring used for damage rolls -> `test_school_abilities.py::test_isawa_duelist_water_damage_behavioral`
- [x] 5th Dan banks wound check excess for next attack -> `test_school_abilities.py::test_isawa_duelist_5th_dan_bank_excess_behavioral`

### Isawa Ishi

- [x] 1st Dan skill selection dropdown -> `test_school_abilities.py::test_isawa_ishi_1st_dan_skill_selection`
- [x] 2nd Dan skill selection dropdown -> `test_school_abilities.py::test_isawa_ishi_2nd_dan_skill_selection`
- [x] VP max display and spend cap behavioral -> `test_school_abilities.py::test_isawa_ishi_vp_max_behavioral`
- [x] 3rd Dan add-to-roll button visible -> `test_school_abilities.py::test_ishi_3rd_dan_add_button_visible` (xfail: Isawa Ishi e2e creation issue)
- [x] 3rd Dan add-to-roll button deducts VP and opens modal -> `test_school_abilities.py::test_ishi_3rd_dan_add_roll` (xfail: Isawa Ishi e2e creation issue)

### Kakita

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_kakita_1st_dan_behavioral`
- [x] 2nd Dan behavioral iaijutsu bonus -> `test_school_abilities.py::test_kakita_2nd_dan_behavioral`
- [x] Phase-zero initiative flag behavioral -> `test_school_abilities.py::test_kakita_phase_0_behavioral`

### Kitsuki

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_kitsuki_1st_dan_behavioral`
- [x] 2nd Dan behavioral interrogation bonus -> `test_school_abilities.py::test_kitsuki_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on investigation -> `test_school_abilities.py::test_kitsuki_3rd_dan_investigation_raises`
- [x] Water ring bonus on interrogation rolls -> `test_school_abilities.py::test_kitsuki_water_interrogation_behavioral`
- [x] 5th Dan ring reduction note displayed -> `test_school_abilities.py::test_kitsuki_5th_dan_ring_note_behavioral`

### Kuni

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_kuni_1st_dan_behavioral`
- [x] 2nd Dan behavioral interrogation bonus -> `test_school_abilities.py::test_kuni_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on interrogation -> `test_school_abilities.py::test_kuni_3rd_dan_interrogation_raises`
- [x] 5th Dan reflect damage behavioral flow -> `test_school_abilities.py::test_kuni_5th_dan_reflect_behavioral`
- [x] 5th Dan reflect damage UI elements appear -> `test_school_abilities.py::test_kuni_5th_dan_reflect_damage_ui`

### Matsu

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_matsu_1st_dan_behavioral`
- [x] 2nd Dan behavioral iaijutsu bonus -> `test_school_abilities.py::test_matsu_2nd_dan_behavioral`
- [x] 3rd Dan VP wound check bonus apply and undo -> `test_school_abilities.py::test_matsu_3rd_dan_vp_wc_bonus_behavioral`
- [x] 4th Dan double attack near-miss behavioral -> `test_school_abilities.py::test_matsu_4th_dan_near_miss_behavioral`
- [x] 5th Dan LW reset note after dealing serious wounds -> `test_school_abilities.py::test_matsu_5th_dan_lw_reset_note_behavioral`
- [x] Initiative always rolls 10 dice -> `test_school_abilities.py::test_matsu_10_dice_initiative_behavioral`

### Mantis Wave-Treader

- [x] 1st Dan grants +1 rolled die on initiative, athletics (all four rings), and wound check -> `test_school_abilities.py::test_mantis_1st_dan_formula_extra_die`
- [x] 2nd Dan editor picker appears at Dan>=2, lists eligible options (no initiative/worldliness), saves via autosave -> `test_school_abilities.py::test_mantis_2nd_dan_editor_picker_visible_and_saves`
- [x] 2nd Dan attack choice: labeled in attack modal pre-roll Bonuses and post-roll breakdown -> `test_school_abilities.py::test_mantis_2nd_dan_attack_choice_labeled`
- [x] 2nd Dan parry choice: labeled in post-roll breakdown -> `test_school_abilities.py::test_mantis_2nd_dan_parry_choice_labeled`
- [x] 2nd Dan skill choice: +5 applied and labeled -> `test_school_abilities.py::test_mantis_2nd_dan_skill_choice_labeled`
- [x] 2nd Dan knack choice (iaijutsu): +5 applied and labeled -> `test_school_abilities.py::test_mantis_2nd_dan_knack_choice_labeled`
- [x] 2nd Dan wound-check choice: WC modal Bonuses row shows +5 -> `test_school_abilities.py::test_mantis_2nd_dan_wound_check_choice_labeled`
- [x] 2nd Dan damage choice: attack modal pre-roll Damage bonuses AND post-roll damage breakdown show +5 -> `test_school_abilities.py::test_mantis_2nd_dan_damage_choice_labeled`
- [x] 2nd Dan switch moves the bonus from attack to wound-check -> `test_school_abilities.py::test_mantis_2nd_dan_switch_choice_moves_bonus`
- [x] Posture tracker block renders on Mantis sheets with both posture buttons -> `test_school_abilities.py::test_mantis_posture_tracker_visibility`
- [x] Posture tracker absent on non-Mantis sheets -> `test_school_abilities.py::test_mantis_posture_tracker_absent_on_non_mantis`
- [x] Clicking a posture advances the phase counter, records it in postureHistory, shows the "Current: Phase X - posture" line, and persists across reload -> `test_school_abilities.py::test_mantis_posture_tracker_advance`
- [x] Both posture buttons disable after 10 picks (phase 11) -> `test_school_abilities.py::test_mantis_posture_tracker_disable_at_11`
- [x] Rolling initiative resets posturePhase to 1 and empties postureHistory -> `test_school_abilities.py::test_mantis_posture_tracker_reset_on_initiative`
- [x] Clicking the action-dice Clear button also resets the posture tracker -> `test_school_abilities.py::test_mantis_posture_tracker_reset_on_action_dice_clear`
- [x] Posture tracker shows "+5 attack rolls, +5 damage rolls" summary in offensive -> `test_school_abilities.py::test_mantis_posture_tracker_bonus_summary_offensive`
- [x] Posture tracker shows "+5 wound checks, +5 TN to be hit" summary in defensive -> `test_school_abilities.py::test_mantis_posture_tracker_bonus_summary_defensive`
- [x] Toggling posture mid-round updates the summary -> `test_school_abilities.py::test_mantis_posture_tracker_bonus_summary_toggles`
- [x] Offensive posture overlays "+5 from offensive posture" in attack modal pre-roll Bonuses and Damage bonuses rows -> `test_school_abilities.py::test_mantis_offensive_posture_attack_pre_roll_bonuses`
- [x] Offensive posture adds +5 to atkRollTotal and shows labeled entry in post-roll breakdown -> `test_school_abilities.py::test_mantis_offensive_posture_attack_post_roll_breakdown`
- [x] Offensive posture adds "+5 flat from offensive posture" to atkComputeDamage parts (pre-roll preview AND post-roll damage-result breakdown) -> `test_school_abilities.py::test_mantis_offensive_posture_damage_preview_and_result`
- [x] Defensive posture bumps the sheet's TN-to-be-hit display by +5 with a tooltip; swapping posture toggles the bump -> `test_school_abilities.py::test_mantis_defensive_posture_tn_display_bumps`
- [x] Defensive posture overlays "+5 from defensive posture" in the WC modal pre-roll Bonuses and post-roll breakdown -> `test_school_abilities.py::test_mantis_defensive_posture_wc_modal_overlay`
- [x] No posture selected -> no posture labels leak into the attack modal -> `test_school_abilities.py::test_mantis_no_posture_no_overlay`
- [x] 5th Dan accumulator sub-block hidden when postureHistory is empty -> `test_school_abilities.py::test_mantis_5th_dan_accumulator_block_hidden_with_no_history`
- [x] 5th Dan accumulator sub-block absent on Dan 4 Mantis -> `test_school_abilities.py::test_mantis_5th_dan_accumulator_block_absent_at_dan_4`
- [x] 5th Dan accumulator counts offensive phases correctly -> `test_school_abilities.py::test_mantis_5th_dan_accumulator_counts_offensive`
- [x] 5th Dan accumulator shows both offensive and defensive lines with mixed history -> `test_school_abilities.py::test_mantis_5th_dan_accumulator_counts_mixed`
- [x] 5th Dan accumulator derived from postureHistory so it auto-resets on initiative roll -> `test_school_abilities.py::test_mantis_5th_dan_accumulator_resets_on_initiative`
- [x] 5th Dan offensive accumulator labeled in attack modal pre-roll Bonuses + Damage bonuses rows (independent of current posture) -> `test_school_abilities.py::test_mantis_5th_dan_attack_modal_pre_roll_includes_accumulator`
- [x] rollAttack snapshots 5th Dan offensive accumulator into formula.bonuses (post-roll breakdown + atkRollTotal include it, stacked with current-posture +5) -> `test_school_abilities.py::test_mantis_5th_dan_attack_post_roll_snapshot`
- [x] atkComputeDamage pushes labeled 5th Dan offensive accumulator line into parts, stacking with current-posture +5 -> `test_school_abilities.py::test_mantis_5th_dan_damage_accumulator_in_parts`
- [x] WC modal pre-roll Bonuses row and post-roll breakdown show labeled 5th Dan defensive accumulator (independent of current posture) -> `test_school_abilities.py::test_mantis_5th_dan_wc_modal_defensive_accumulator`
- [x] TN display reflects base + defensive-posture +5 + 5th Dan accumulator; enumerated tooltip lists both; switching to offensive keeps only the accumulator -> `test_school_abilities.py::test_mantis_5th_dan_tn_display_bumps_with_accumulator`
- [x] Dan 4 Mantis: current-posture +5 lands but no 5th Dan accumulator label -> `test_school_abilities.py::test_mantis_dan_4_no_accumulator_on_attack`
- [x] 3rd Dan offensive button hidden when no posture selected -> `test_school_abilities.py::test_mantis_3rd_dan_button_hidden_without_posture`
- [x] 3rd Dan offensive button hidden in defensive posture -> `test_school_abilities.py::test_mantis_3rd_dan_button_hidden_in_defensive_posture`
- [x] 3rd Dan offensive button hidden when no unspent action dice remain -> `test_school_abilities.py::test_mantis_3rd_dan_button_hidden_with_no_unspent_action_dice`
- [x] 3rd Dan offensive button absent on Dan 2 Mantis -> `test_school_abilities.py::test_mantis_3rd_dan_button_hidden_on_dan_2`
- [x] Clicking 3rd Dan offensive button spends the lowest unspent action die (labeled) and bumps offensive3rdDanAccum by X -> `test_school_abilities.py::test_mantis_3rd_dan_click_spends_die_and_accumulates`
- [x] Two clicks stack the accumulator at 2X and spend two dice -> `test_school_abilities.py::test_mantis_3rd_dan_two_spends_stack_accumulator`
- [x] Next attack modal pre-roll Bonuses + post-roll breakdown include +X from Mantis 3rd Dan (offensive) -> `test_school_abilities.py::test_mantis_3rd_dan_next_attack_includes_accumulator`
- [x] atkComputeDamage parts include labeled +X flat from Mantis 3rd Dan (offensive) -> `test_school_abilities.py::test_mantis_3rd_dan_damage_includes_accumulator`
- [x] Rolling initiative zeros offensive3rdDanAccum (via resetMantisRound) -> `test_school_abilities.py::test_mantis_3rd_dan_resets_on_initiative`
- [x] 3rd Dan defensive button hidden without posture selected -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_button_hidden_without_posture`
- [x] 3rd Dan defensive button hidden in offensive posture -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_button_hidden_in_offensive_posture`
- [x] 3rd Dan defensive button hidden when no unspent action dice -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_button_hidden_no_action_dice`
- [x] 3rd Dan defensive button absent on Dan 2 Mantis -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_button_absent_on_dan_2`
- [x] Clicking 3rd Dan defensive button spends lowest unspent action die (labeled) and bumps defensive3rdDanAccum by X -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_click_spends_die_and_accumulates`
- [x] Two defensive spends stack at 2X -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_two_spends_stack`
- [x] WC modal pre-roll Bonuses + post-roll breakdown include +X from Mantis 3rd Dan (defensive) -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_wc_overlay`
- [x] TN display includes +5 current posture + +X 3rd Dan accumulator; enumerated tooltip lists each contribution; inline "+X 3rd Dan" label visible -> `test_school_abilities.py::test_mantis_3rd_dan_defensive_tn_display`
- [x] Clear bonuses button zeros postureHistory, both 3rd Dan accumulators, and action dice -> `test_school_abilities.py::test_mantis_clear_bonuses_zeros_everything`
- [x] Clear bonuses button hidden on a fresh sheet with no round state -> `test_school_abilities.py::test_mantis_clear_bonuses_button_hidden_when_empty`
- [x] Action-dice "Clear" button is equivalent to Clear bonuses (wipes everything) -> `test_school_abilities.py::test_mantis_action_dice_clear_equivalent_to_clear_bonuses`
- [x] Defensive posture raises WC probability-table passChance / lowers expectedSW -> `test_school_abilities.py::test_mantis_wc_probability_shifts_with_defensive_posture`
- [x] Spending 3rd Dan defensive button raises WC probability-table passChance further -> `test_school_abilities.py::test_mantis_wc_probability_shifts_with_3rd_dan_defensive`
- [x] 5th Dan defensive-posture-count accumulator shifts WC probability table -> `test_school_abilities.py::test_mantis_wc_probability_shifts_with_5th_dan_defensive_count`
- [x] Posture +5, 5th Dan accum, 3rd Dan accum all stack in the probability table; Bonuses row lists all three labeled entries -> `test_school_abilities.py::test_mantis_wc_probability_all_three_stack`
- [x] 4th Dan: rolling initiative appends a deterministic value-1 die flagged mantis_4th_dan + athletics_only -> `test_school_abilities.py::test_mantis_4th_dan_athletics_die_appended_after_initiative`
- [x] 4th Dan die renders with data-die-mantis-4th-dan + movement/athletics/3rd-Dan restriction tooltip -> `test_school_abilities.py::test_mantis_4th_dan_die_renders_with_testable_markup`
- [x] 4th Dan die is spendable via spendActionDie -> `test_school_abilities.py::test_mantis_4th_dan_die_spendable`
- [x] 4th Dan die regenerated on next initiative roll -> `test_school_abilities.py::test_mantis_4th_dan_die_regenerated_on_next_initiative`
- [x] 4th Dan die cleared by Clear bonuses button -> `test_school_abilities.py::test_mantis_4th_dan_die_cleared_by_clear_bonuses`
- [x] Dan 3 Mantis does not get the 4th Dan bonus die -> `test_school_abilities.py::test_mantis_dan_3_no_4th_dan_die`
- [x] Non-Mantis Dan 4 does not get the 4th Dan bonus die -> `test_school_abilities.py::test_non_mantis_dan_4_no_4th_dan_die`

### Merchant

- [x] Post-roll VP buttons visible -> `test_school_abilities.py::test_merchant_post_roll_vp_buttons`
- [x] Post-roll VP spending works -> `test_school_abilities.py::test_merchant_post_roll_vp_spending`
- [x] Pre-roll menu has no VP options -> `test_school_abilities.py::test_merchant_pre_roll_menu_has_no_vp_options`
- [x] Spend 1 VP button clickable multiple times -> `test_school_abilities.py::test_merchant_spend_one_vp_button_clickable_multiple_times`
- [x] Spend 1 VP preserves existing dice and adds one new die -> `test_school_abilities.py::test_merchant_spend_one_vp_preserves_existing_dice`
- [x] 5th Dan reroll button visible at Dan 5 -> `test_school_abilities.py::test_merchant_5th_dan_reroll_button_visible_at_dan_5`
- [x] 5th Dan reroll button hidden below Dan 5 -> `test_school_abilities.py::test_merchant_5th_dan_reroll_hidden_below_dan_5`
- [x] 5th Dan reroll requires sum >= 5*(count-1) -> `test_school_abilities.py::test_merchant_5th_dan_reroll_constraint_enforced`
- [x] 5th Dan reroll shows +/- delta in breakdown -> `test_school_abilities.py::test_merchant_5th_dan_reroll_applies_delta_bullet`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_merchant_1st_dan_behavioral`
- [x] 2nd Dan behavioral interrogation bonus -> `test_school_abilities.py::test_merchant_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on sincerity -> `test_school_abilities.py::test_merchant_3rd_dan_sincerity_raises`

### Mirumoto

- [x] 3rd Dan round points counter UI -> `test_school_abilities.py::test_mirumoto_round_points_counter`
- [x] Round points display and spending buttons -> `test_school_abilities.py::test_mirumoto_round_points_display_and_buttons`
- [x] 3rd Dan round points auto-refill on initiative roll -> `test_school_abilities.py::test_mirumoto_3rd_dan_initiative_refills_round_points`
- [x] 3rd Dan no refresh message when pool already full -> `test_school_abilities.py::test_mirumoto_3rd_dan_initiative_no_message_when_pool_full`
- [x] 3rd Dan pool is NOT refilled by non-initiative rolls -> `test_school_abilities.py::test_non_initiative_roll_does_not_trigger_reset`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_mirumoto_1st_dan_behavioral`
- [x] 2nd Dan behavioral parry bonus -> `test_school_abilities.py::test_mirumoto_2nd_dan_behavioral`
- [x] Parry roll adds temp VP -> `test_school_abilities.py::test_mirumoto_parry_temp_vp_behavioral`
- [x] 5th Dan VP spending +10 on combat rolls -> `test_school_abilities.py::test_mirumoto_5th_dan_vp_plus_10`
- [x] 5th Dan +10/VP reflected in attack and wound check probability charts -> `test_school_abilities.py::test_mirumoto_5th_dan_prob_charts_include_bonus`
- [x] 4th Dan probability charts do NOT include +10/VP bonus -> `test_school_abilities.py::test_mirumoto_4th_dan_prob_charts_no_bonus`
- [x] 4th Dan failed parry reduced bonus damage dice -> `test_school_abilities.py::test_mirumoto_4th_dan_parry_reduction_behavioral`

### Otaku

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_otaku_1st_dan_behavioral`
- [x] 2nd Dan behavioral wound check bonus -> `test_school_abilities.py::test_otaku_2nd_dan_behavioral`
- [x] 4th Dan lunge extra die after failed parry -> `test_school_abilities.py::test_otaku_4th_dan_lunge_parry_behavioral`
- [x] 5th Dan trade dice for SW pre-roll checkbox -> `test_school_abilities.py::test_otaku_5th_dan_trade_dice_behavioral`

### Priest

- [x] 1st Dan skill selection dropdown -> `test_school_abilities.py::test_priest_1st_dan_skill_selection`
- [ ] Special ability "all 10 rituals" link on character sheet -> `test_school_abilities.py::test_priest_sheet_links_to_rituals`
- [ ] Special ability "all 10 rituals" link in school selection editor -> `test_school_selection.py::test_priest_special_ability_links_to_rituals`
- [ ] Non-Priest school's special ability has no rituals link in editor -> `test_school_selection.py::test_non_priest_special_ability_has_no_external_link`
- [x] 2nd Dan Honor bonus roll free raise -> `test_school_abilities.py::test_priest_2nd_dan_behavioral`
- [x] 5th Dan Conviction pool refreshes on initiative roll -> `test_school_abilities.py::test_priest_5th_dan_initiative_refreshes_conviction`
- [x] 5th Dan no refresh message when Conviction pool full -> `test_school_abilities.py::test_priest_5th_dan_initiative_no_message_when_conviction_unspent`
- [x] 4th Dan Conviction is NOT refreshed by initiative (per-day, not per-round) -> `test_school_abilities.py::test_priest_4th_dan_initiative_does_not_reset_conviction`
- [ ] Bless conversation topic button rolls 2k1 with correct title -> `test_school_abilities.py::test_priest_bless_conversation_topic_rolls_2k1`
- [ ] Bless research button rolls 2k1 with correct title -> `test_school_abilities.py::test_priest_bless_research_rolls_2k1`
- [ ] Bless buttons expose full rules text in a hover tooltip -> `test_school_abilities.py::test_priest_bless_buttons_have_rules_tooltips`
- [ ] Bless roll allows Conviction to be spent (+1 per point) -> `test_school_abilities.py::test_priest_bless_roll_allows_conviction_spending`
- [ ] Bless roll skips the pre-roll VP menu (no void spending) -> `test_school_abilities.py::test_priest_bless_roll_offers_no_void_spending`
- [ ] Bless buttons do not render for non-Priest characters -> `test_school_abilities.py::test_priest_bless_buttons_absent_on_non_priest`
- [ ] Impaired 10 with a party priest shows "<priest> priest blessed for 10 rerolls" button -> `test_school_abilities.py::test_priest_bless_reroll_button_shows_on_impaired_10`
- [ ] Priest-bless-reroll button tooltip quotes the sick-or-impaired ritual -> `test_school_abilities.py::test_priest_bless_reroll_button_tooltip_has_rules_text`
- [ ] Clicking the button rerolls the 10s and updates keptSum + baseTotal -> `test_school_abilities.py::test_priest_bless_reroll_replaces_10s_and_updates_total`
- [ ] After the reroll clears the 10s, the button auto-hides -> `test_school_abilities.py::test_priest_bless_reroll_button_hides_after_click`
- [ ] Button never shows when there is no priest in the party -> `test_school_abilities.py::test_priest_bless_reroll_button_hidden_without_party_priest`
- [ ] Button never shows when the character is not Impaired -> `test_school_abilities.py::test_priest_bless_reroll_button_hidden_when_not_impaired`

### Shiba

- [x] Parry damage button visible -> `test_school_abilities.py::test_shiba_parry_damage_button`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_shiba_1st_dan_behavioral`
- [x] 2nd Dan behavioral parry bonus -> `test_school_abilities.py::test_shiba_2nd_dan_behavioral`
- [x] 4th Dan wound check 3k1 bonus -> `test_school_abilities.py::test_shiba_4th_dan_3k1_wound_check_behavioral`
- [x] 5th Dan parry TN note displayed -> `test_school_abilities.py::test_shiba_5th_dan_parry_tn_note`

### Shinjo

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_shinjo_1st_dan_behavioral`
- [x] 2nd Dan behavioral parry bonus -> `test_school_abilities.py::test_shinjo_2nd_dan_behavioral`
- [x] 4th Dan initiative highest die set to 1 -> `test_school_abilities.py::test_shinjo_4th_dan_initiative_highest_1_behavioral`
- [x] 5th Dan parry excess applied to wound check -> `test_school_abilities.py::test_shinjo_5th_dan_parry_excess_behavioral`

### Shosuro

- [x] Actor stipend display on sheet -> `test_school_abilities.py::test_shosuro_stipend_display`
- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_shosuro_1st_dan_behavioral`
- [x] 2nd Dan behavioral sincerity bonus -> `test_school_abilities.py::test_shosuro_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on sincerity -> `test_school_abilities.py::test_shosuro_3rd_dan_sincerity_raises`
- [x] Acting skill bonus in roll formulas -> `test_school_abilities.py::test_shosuro_acting_dice_behavioral`
- [x] 5th Dan lowest 3 dice on skill rolls -> `test_school_abilities.py::test_shosuro_5th_dan_lowest_3_dice`
- [x] 5th Dan lowest 3 dice on attack rolls (pre-roll note + result breakdown) -> `test_school_abilities.py::test_shosuro_5th_dan_attack_lowest_3_dice`
- [x] 5th Dan lowest 3 dice on wound check rolls (pre-roll note + result breakdown) -> `test_school_abilities.py::test_shosuro_5th_dan_wound_check_lowest_3_dice`

### Shugenja (skipped - school disabled)

- [ ] 1st Dan element selection (school disabled) -> `test_school_abilities.py::test_shugenja_1st_dan_element_selection` (skipped)
- [ ] 2nd Dan element selection (school disabled) -> `test_school_abilities.py::test_shugenja_2nd_dan_element_selection` (skipped)
- [ ] 3rd Dan applicable skills (school disabled) -> `test_school_abilities.py::test_shugenja_3rd_dan_applicable_skills` (skipped)
- [ ] Ring bonus display (school disabled) -> `test_school_abilities.py::test_shugenja_ring_bonus_display` (skipped)

### Togashi

- [x] 4th Dan heal SW button works -> `test_school_abilities.py::test_togashi_heal_sw_button_works`
- [x] 1st Dan grants +1 rolled die on wound check (also athletics/init) -> `test_school_abilities.py::test_togashi_1st_dan_behavioral`
- [x] 2nd Dan behavioral athletics bonus -> `test_school_abilities.py::test_togashi_2nd_dan_behavioral`
- [x] 3rd Dan spend raise on athletics -> `test_school_abilities.py::test_togashi_3rd_dan_athletics_raises`
- [x] 3rd Dan athletics raise decrements daily pool -> `test_school_abilities.py::test_togashi_athletics_raise_decrements_daily_pool`
- [x] 3rd Dan athletics raise undo restores pool -> `test_school_abilities.py::test_togashi_athletics_raise_undo_restores_pool`
- [x] 3rd Dan athletics raise per-roll capped by pool remaining -> `test_school_abilities.py::test_togashi_athletics_raise_capped_by_pool_remaining`
- [x] 3rd Dan athletics raise button hidden when pool empty -> `test_school_abilities.py::test_togashi_athletics_raise_button_hidden_when_pool_empty`
- [ ] 3rd Dan athletics raise spendable on athletics:parry (existing regular modal path) -> `test_school_abilities.py::test_togashi_athletics_raise_on_athletics_parry`
- [ ] 3rd Dan athletics raise spendable on athletics:attack (attack modal HIT block adds +5 to atkRollTotal and decrements pool) -> `test_school_abilities.py::test_togashi_athletics_raise_on_athletics_attack_hit`
- [ ] 3rd Dan athletics raise undo from attack modal restores atkRollTotal and pool -> `test_school_abilities.py::test_togashi_athletics_raise_atk_undo_restores_total_and_pool`
- [ ] 3rd Dan athletics raise button absent on regular (non-athletics) attack even for togashi 3D -> `test_school_abilities.py::test_togashi_athletics_raise_button_absent_on_regular_attack`
- [ ] Athletics picker has 5th row "Athletics (Predeclared parry)" that rolls athletics:parry with +5 flat -> `test_rolls.py::test_athletics_picker_has_predeclared_parry_row`
- [x] 4th Dan reroll button on contested rolls -> `test_school_abilities.py::test_togashi_4th_dan_reroll_behavioral`
- [x] 4th Dan reroll limited to once per roll (button hidden after use, reappears on next roll; post-reroll banner notes original is discarded) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_only_once_per_roll`
- [x] 4th Dan reroll hidden on initiative (never contested) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_initiative`
- [x] 4th Dan reroll hidden on Etiquette (never contested) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_etiquette`
- [x] 4th Dan reroll hidden on Heraldry (never contested) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_heraldry`
- [ ] 4th Dan reroll hidden on Dragon Tattoo (damage rolls are never contested) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_dragon_tattoo`
- [ ] 4th Dan reroll hidden on parry (parry is never contested) -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_parry`
- [ ] 4th Dan reroll hidden on athletics:parry -> `test_school_abilities.py::test_togashi_4th_dan_reroll_hidden_on_athletics_parry`
- [x] Togashi initiative: athletics-only bonus die persists to the Actions side panel with blue variant + tooltip -> `test_school_abilities.py::test_togashi_init_athletics_die_appears_in_side_panel`
- [x] Non-athletics parry auto-spend skips the athletics-only die even when it has the lowest value -> `test_school_abilities.py::test_togashi_non_athletics_parry_skips_athletics_die`
- [x] Athletics-only die's per-die menu offers Athletics Parry and selecting it spends that die -> `test_school_abilities.py::test_togashi_athletics_parry_can_spend_athletics_die`
- [x] Per-die action menu lists core options (attack/parry/predeclared-parry) -> `test_rolls.py::test_action_die_menu_shows_action_options`
- [x] Per-die Parry spends that specific die (not the lowest) -> `test_rolls.py::test_action_die_menu_parry_spends_that_die`
- [x] Per-die Attack opens the attack modal and commits the die on Roll -> `test_rolls.py::test_action_die_menu_attack_opens_modal_spends_on_roll`
- [x] Cancelling the attack modal opened from a per-die menu leaves the die unspent -> `test_rolls.py::test_action_die_menu_attack_cancel_does_not_spend`
- [x] Athletics-only die's menu omits regular attack/parry/predeclared rows -> `test_rolls.py::test_athletics_only_die_menu_restricts_to_athletics`
- [x] Dragon Tattoo does not offer void spending (damage roll, not skill roll) -> `test_school_abilities.py::test_togashi_dragon_tattoo_no_void_spend`
- [x] Conviction spend button appears on skill roll results -> `test_school_abilities.py::test_conviction_button_appears_on_skill_roll`
- [x] Conviction spend button does NOT appear on initiative rolls -> `test_school_abilities.py::test_conviction_not_on_initiative`
- [x] Conviction spend adds +1 and decrements the daily pool -> `test_school_abilities.py::test_conviction_spend_adds_plus_one_and_decrements_pool`
- [x] Conviction points persist through Togashi 4th Dan reroll -> `test_school_abilities.py::test_conviction_survives_togashi_reroll`
- [x] Akodo 1st Dan: attack modal pre-roll shows +1 rolled die note -> `test_school_abilities.py::test_akodo_1st_dan_attack_modal_pre_roll_extra_die`
- [x] Ikoma 2nd Dan: attack modal pre-roll shows +5 free raise -> `test_school_abilities.py::test_ikoma_2nd_dan_attack_modal_pre_roll_free_raise`
- [x] Brotherhood 2nd Dan: attack modal pre-roll shows +5 free raise -> `test_school_abilities.py::test_brotherhood_2nd_dan_attack_modal_pre_roll_free_raise`
- [x] Bayushi 2nd Dan: double_attack modal pre-roll shows +5 free raise -> `test_school_abilities.py::test_bayushi_2nd_dan_double_attack_modal_pre_roll`
- [x] Hida 2nd Dan: counterattack modal pre-roll shows +5 free raise -> `test_school_abilities.py::test_hida_2nd_dan_counterattack_modal_pre_roll`
- [x] Daidoji 2nd Dan: counterattack modal pre-roll shows +5 free raise -> `test_school_abilities.py::test_daidoji_2nd_dan_counterattack_modal_pre_roll`
- [x] Kitsuki Special: attack modal pre-roll shows +2*Water -> `test_school_abilities.py::test_kitsuki_attack_modal_pre_roll_shows_water_bonus`
- [x] Courtier Special: attack modal pre-roll shows +Air -> `test_school_abilities.py::test_courtier_special_attack_modal_pre_roll_shows_air_bonus`
- [x] Courtier 5th Dan: attack modal pre-roll shows +Air (both special and 5th Dan) -> `test_school_abilities.py::test_courtier_5th_dan_attack_modal_pre_roll_shows_air_bonus`
- [x] Shosuro Special: attack modal pre-roll shows +acting rolled dice -> `test_school_abilities.py::test_shosuro_acting_dice_attack_modal_pre_roll`
- [x] Dragon Tattoo knack rolls (2X)k1 damage (not ring-based) -> `test_school_abilities.py::test_togashi_dragon_tattoo_rolls_2x_k1_damage`
- [x] Dragon Tattoo does not reroll 10s when impaired -> `test_school_abilities.py::test_togashi_dragon_tattoo_impaired_disables_reroll_10s`
- [x] Initiative box shows both variants ("3k2 plus 1 athletics" and "6k5 athletics") and dropdown opens on click -> `test_school_abilities.py::test_togashi_initiative_dropdown_shows_both_variants`
- [x] Normal initiative variant rolls correct total dice count (base+1 athletics) -> `test_school_abilities.py::test_togashi_initiative_normal_variant_rolls_correct_dice`
- [x] Athletics initiative variant rolls correct total dice count (base+3) -> `test_school_abilities.py::test_togashi_initiative_athletics_variant_rolls_correct_dice`
- [x] 1st Dan +1 die remains in effect past dan 1 (init display) -> `test_school_abilities.py::test_togashi_initiative_dan_advancement_bonus`

### Yogo

- [x] 1st Dan behavioral roll formulas and bonuses -> `test_school_abilities.py::test_yogo_1st_dan_behavioral`
- [x] 2nd Dan behavioral wound check bonus -> `test_school_abilities.py::test_yogo_2nd_dan_behavioral`
- [x] 3rd Dan VP spending reduces light wounds -> `test_school_abilities.py::test_yogo_3rd_dan_vp_heals_lw_behavioral`
- [x] 4th Dan post-roll VP gives enhanced bonus -> `test_school_abilities.py::test_yogo_4th_dan_post_roll_vp_behavioral`
- [x] 4th Dan +5/VP reflected in wound check probability chart -> `test_school_abilities.py::test_yogo_4th_dan_wc_prob_chart_includes_raise`
- [x] 3rd Dan probability chart does NOT include +5/VP -> `test_school_abilities.py::test_yogo_3rd_dan_wc_prob_chart_no_raise`
- [x] Serious wound grants temp VP -> `test_school_abilities.py::test_yogo_serious_wound_temp_vp_behavioral`

## JS Error Checks

- [x] No JS errors on sheet page (parametrized across 7 schools, including Mantis Wave-Treader) → `test_sheet_js_errors.py::test_sheet_has_no_javascript_errors`

## Void Point Spending

- [x] Roll menu shows void options when VP available → `test_void_spending.py::test_roll_menu_shows_void_options`
- [x] Roll menu skipped when no VP available → `test_void_spending.py::test_roll_menu_skipped_without_void`
- [x] Spending void deducts from counter → `test_void_spending.py::test_spending_void_deducts_from_counter`
- [x] Temp void deducted before regular → `test_void_spending.py::test_temp_void_deducted_before_regular`
- [x] Otherworldliness submenu appears on hover for basic skill → `test_void_spending.py::test_ow_submenu_appears_for_basic_skill_with_ow_available`
- [x] Otherworldliness spend increases rolled dice and decrements pool → `test_void_spending.py::test_ow_spend_increases_rolled_and_decrements_pool`
- [x] Otherworldliness submenu hidden on advanced skill → `test_void_spending.py::test_ow_submenu_hidden_on_advanced_skill`
- [x] Otherworldliness submenu appears for unskilled basic skill → `test_void_spending.py::test_ow_submenu_appears_for_unskilled_basic_skill`
- [x] Otherworldliness spend on unskilled roll enables 10s reroll → `test_void_spending.py::test_ow_spend_on_unskilled_roll_enables_reroll_tens`
- [x] Otherworldliness spend on unskilled roll while Impaired keeps no-reroll → `test_void_spending.py::test_ow_spend_on_unskilled_roll_while_impaired_keeps_no_reroll`
- [x] Otherworldliness submenu hidden when pool exhausted → `test_void_spending.py::test_ow_submenu_hidden_when_pool_exhausted`

## Dice Rolling

- [x] Click a skill row opens the modal with the skill name → `test_rolls.py::test_click_skill_opens_modal_with_skill_name`
- [x] Unskilled advanced skill rolls show the -10 penalty in the breakdown → `test_rolls.py::test_unskilled_advanced_skill_shows_minus_10_in_breakdown`
- [x] Click Attack opens attack modal → `test_rolls.py::test_click_attack_opens_attack_modal`
- [x] Click Parry shows menu with Roll Parry and Predeclared Parry options → `test_rolls.py::test_click_parry_shows_predeclare_option`
- [x] Hovering Roll Parry reveals a void-spend submenu when VP available → `test_rolls.py::test_parry_hover_reveals_void_submenu_on_roll`
- [x] Hovering Predeclared Parry reveals its own void-spend submenu with +5 label → `test_rolls.py::test_parry_hover_reveals_void_submenu_on_predeclared`
- [x] Clicking a void option under Roll Parry rolls with void spent → `test_rolls.py::test_parry_void_submenu_click_rolls_with_void`
- [x] Clicking a void option under Predeclared Parry rolls with +5 and void spent → `test_rolls.py::test_parry_void_submenu_click_rolls_predeclared_with_void`
- [x] Parry menu hides void-submenu arrows when VP is 0 → `test_rolls.py::test_parry_no_void_submenu_arrow_when_no_vp`
- [x] Click a Ring opens an Athletics roll modal → `test_rolls.py::test_click_ring_opens_athletics_modal`
- [x] Click a Ring always opens the roll menu (even with 0 VP) → `test_rolls.py::test_click_ring_always_shows_menu_even_with_zero_vp`
- [x] Click a Ring with VP shows "Spend N void points" dropdown options → `test_rolls.py::test_click_ring_shows_void_options_when_vp_available`
- [x] Athletics knack die icon opens a ring picker (Air/Fire/Water/Earth) → `test_rolls.py::test_athletics_knack_icon_opens_ring_picker`
- [x] Selecting a ring from the athletics picker rolls that ring's Athletics formula → `test_rolls.py::test_athletics_knack_picker_rolls_selected_ring`
- [x] Hovering a ring in the athletics picker reveals a void-spend submenu → `test_rolls.py::test_athletics_knack_picker_void_submenu`
- [x] Athletics picker shows Athletics (Attack) and Athletics (Parry) buttons (athletics knack only) → `test_rolls.py::test_athletics_picker_shows_attack_and_parry_options`
- [x] Clicking Athletics (Attack) in the picker opens the attack modal with a doubled-TN (5+10*P) dropdown → `test_rolls.py::test_athletics_picker_attack_opens_attack_modal`
- [x] Clicking Athletics (Parry) in the picker rolls the athletics:parry formula → `test_rolls.py::test_athletics_picker_parry_rolls_athletics_parry`
- [x] Clicking Attack with athletics available opens a choice menu (Roll Attack / Athletics Attack) → `test_rolls.py::test_attack_button_shows_athletics_choice_when_athletics_available`
- [x] Clicking Attack without athletics goes straight to the attack modal (no choice menu) → `test_rolls.py::test_attack_button_no_choice_menu_for_non_athletics_character`
- [x] Selecting Athletics Attack from the choice menu opens the modal with the doubled-TN dropdown → `test_rolls.py::test_attack_choice_athletics_opens_modal_with_doubled_tn`
- [x] Parry menu includes an Athletics Parry entry when athletics is available → `test_rolls.py::test_parry_menu_shows_athletics_parry_option`
- [x] Parry menu has no Athletics Parry entry for characters without athletics → `test_rolls.py::test_parry_menu_no_athletics_for_non_athletics_character`
- [x] Modal shows Total and dice after the animation phase → `test_rolls.py::test_modal_shows_total_and_dice_after_animation`
- [x] Modal close button hides the modal → `test_rolls.py::test_modal_close_button`
- [x] Impaired character's roll modal shows "10s not rerolled" note → `test_rolls.py::test_impaired_character_modal_shows_no_reroll_note`
- [x] Unskilled roll modal names the zero-ranked skill in the no-reroll note → `test_rolls.py::test_unskilled_character_modal_names_skill_in_no_reroll_note`
- [x] Impaired indicator visible on the sheet when wounds ≥ Earth → `test_rolls.py::test_impaired_indicator_visible_on_sheet`
- [x] Impaired indicator absent when healthy → `test_rolls.py::test_impaired_indicator_absent_when_healthy`
- [x] Disabling animation in profile shows result panel immediately → `test_rolls.py::test_disable_animation_preference`
- [x] Die top angle is approximately 70 degrees → `test_rolls.py::test_die_top_angle_is_about_70_degrees`
- [x] Initiative roll shows action dice → `test_rolls.py::test_initiative_roll_shows_action_dice`
- [x] Initiative shows action dice (not Total) → `test_rolls.py::test_initiative_no_total_shown`

### Action-Dice Tracking (Actions section)

- [ ] Initiative roll populates the Actions section → `test_rolls.py::test_initiative_populates_action_dice_section`
- [ ] Clicking unspent die + 'Action was spent' marks spent → `test_rolls.py::test_action_die_dropdown_marks_spent`
- [ ] Clicking spent die + 'Mark as unspent' flips back → `test_rolls.py::test_spent_action_die_dropdown_marks_unspent`
- [ ] Clear button empties action dice and hides the section → `test_rolls.py::test_clear_action_dice_hides_section`
- [ ] Parry roll auto-spends the lowest unspent action die → `test_rolls.py::test_parry_auto_spends_lowest_action_die`
- [ ] Attack roll auto-spends the lowest unspent action die → `test_rolls.py::test_attack_auto_spends_lowest_action_die`
- [ ] Attack with no unspent dice still rolls without error → `test_rolls.py::test_attack_with_all_dice_spent_still_rolls`
- [ ] Rerolling initiative replaces previous action dice → `test_rolls.py::test_initiative_reroll_replaces_previous_action_dice`
- [ ] Parry annotates the spent die with the parry total → `test_rolls.py::test_parry_annotates_spent_die_with_result`
- [ ] Attack annotates the spent die with roll total + hit/miss → `test_rolls.py::test_attack_annotates_spent_die_with_result`
- [ ] Die's title attribute exposes the spent_by text → `test_rolls.py::test_action_die_tooltip_uses_spent_by_text`
- [ ] Manual 'Action was spent' click leaves spent_by empty → `test_rolls.py::test_manual_spend_does_not_set_spent_by`
- [x] 3rd Dan spend raise button visible for applicable skill → `test_rolls.py::test_spend_raise_button_visible_for_applicable_skill`
- [x] 3rd Dan spend raise adds +5 to total → `test_rolls.py::test_spend_raise_adds_5_to_total`
- [x] 3rd Dan undo raise reverses spend → `test_rolls.py::test_undo_raise_reverses_spend`
- [x] 3rd Dan spend disabled at per-roll max → `test_rolls.py::test_spend_disabled_at_per_roll_max`
- [x] 3rd Dan undo disabled when none spent → `test_rolls.py::test_undo_disabled_when_none_spent`
- [x] No spend button for non-applicable skill → `test_rolls.py::test_no_spend_button_for_non_applicable_skill`
- [x] Athletics roll modal title includes the ring name → `test_rolls.py::test_athletics_label_in_modal`

### Freeform Roll (generic fallback dice roller)

- [ ] Freeform Roll button visible in Rings section header → `test_rolls.py::test_freeform_button_visible_on_sheet`
- [ ] Clicking Freeform Roll opens the modal with rolled/kept dropdowns and reroll checkbox → `test_rolls.py::test_freeform_button_opens_modal`
- [ ] Dice rolled and kept both default to 1 (1k1) → `test_rolls.py::test_freeform_defaults_to_1k1`
- [ ] Kept dropdown options never exceed the rolled value → `test_rolls.py::test_freeform_kept_cannot_exceed_rolled`
- [ ] Lowering rolled below kept clamps kept down → `test_rolls.py::test_freeform_lowering_rolled_clamps_kept`
- [ ] Reroll 10s checkbox checked by default for healthy character → `test_rolls.py::test_freeform_reroll_default_true_when_healthy`
- [ ] Reroll 10s checkbox unchecked by default for impaired character → `test_rolls.py::test_freeform_reroll_default_false_when_impaired`
- [ ] Reroll 10s checkbox can be toggled by the player either direction → `test_rolls.py::test_freeform_reroll_checkbox_togglable`
- [ ] Clicking Roll produces a result with a Total → `test_rolls.py::test_freeform_roll_shows_result_with_total`
- [ ] Roll Again button returns to the pre-roll phase → `test_rolls.py::test_freeform_roll_again_returns_to_pre_phase`
- [ ] × close button hides the freeform modal → `test_rolls.py::test_freeform_modal_close_button`
- [ ] Freeform 1k1 with reroll off keeps total in [1,10] with no bonuses applied → `test_rolls.py::test_freeform_roll_applies_no_bonuses`

## Sections (rich-text panels)

- [x] Add a single section, type body, persist after reload → `test_sections.py::test_add_single_section_persists`
- [x] Section labels can be any user-chosen string (Backstory, Allies, etc.) → `test_sections.py::test_section_label_can_be_anything`
- [x] Sections render on the character sheet with their label and HTML body → `test_sections.py::test_section_renders_on_sheet`
- [x] Delete a section (with confirm) → `test_sections.py::test_delete_section`
- [x] Reorder sections via up/down arrow buttons → `test_sections.py::test_reorder_sections_with_arrows`
- [x] Move-up disabled at top, move-down disabled at bottom → `test_sections.py::test_move_up_disabled_at_top_and_move_down_disabled_at_bottom`
- [x] Empty hint shown when no sections; hidden after first add → `test_sections.py::test_empty_sections_list_shows_hint`
- [x] Dangerous HTML (script tags, javascript: links) sanitized server-side → `test_sections.py::test_dangerous_html_is_sanitized`
- [x] Bold formatting via Quill toolbar persists round-trip and renders on sheet → `test_sections.py::test_section_with_formatting_persists`
- [x] Restricted checkbox exists on each section → `test_sections.py::test_restricted_checkbox_exists`
- [x] Restricted label lists editor names → `test_sections.py::test_restricted_label_lists_editors`
- [x] Restricted flag persists after reload → `test_sections.py::test_restricted_persists_on_reload`
- [x] Restricted sections visible to editors with label → `test_sections.py::test_restricted_section_visible_to_editor`
- [x] Restricted sections render with gray background → `test_sections.py::test_restricted_section_has_gray_background`
- [x] Unrestricted sections have no restricted label → `test_sections.py::test_unrestricted_section_has_no_label`

## Gaming Groups

- [x] Set group via editor dropdown persists → `test_groups.py::test_set_group_via_editor_persists`
- [x] Setting group does not create a "modified" badge → `test_groups.py::test_set_group_does_not_create_modified_badge`
- [x] Homepage clusters characters by group with section headings → `test_groups.py::test_homepage_clusters_characters_by_group`
- [x] Party member's Thoughtless adds inline +10 note on other character's Tact → `test_groups.py::test_party_thoughtless_inline_on_other_tact`
- [x] Party member Priest at 2nd Dan grants free raise to ally bragging (shown in tooltip and baked into formula) → `test_groups.py::test_party_priest_2nd_dan_grants_bragging_free_raise`
- [x] Party member Priest at 5th Dan exposes a "Spend [Priest]'s Conviction (+1)" button on ally roll results → `test_groups.py::test_party_priest_5th_dan_ally_conviction_button`
- [x] Self Thoughtless inline on own Tact (and not on Sincerity) → `test_groups.py::test_self_thoughtless_inline_on_own_tact`
- [x] Standalone Party Effects section is removed entirely → `test_groups.py::test_no_party_effects_section_present`

## Admin — Manage Gaming Groups

- [x] Admin page renders for admin (lists seeded groups) → `test_groups.py::test_admin_groups_page_renders_for_admin`
- [x] Admin page forbidden for non-admin → `test_groups.py::test_admin_groups_forbidden_for_non_admin`
- [x] Admin can create a new group → `test_groups.py::test_admin_create_new_group`
- [x] Admin can rename a group → `test_groups.py::test_admin_rename_group`
- [x] Admin can delete a group; member characters become unassigned → `test_groups.py::test_admin_delete_group_unassigns_characters`

## Homepage (index.html)

- [x] Character list displays characters → `test_create_character.py::test_create_and_edit_character`
- [x] Draft badge shown for never-applied characters → `test_banners.py::test_homepage_draft_badge`
- [x] "Draft changes" badge shown for modified characters → `test_banners.py::test_homepage_draft_changes_badge`
- [x] No badge shown for cleanly applied characters → `test_banners.py::test_homepage_no_badge_after_apply`
- [x] Character card links to correct character sheet → `test_banners.py::test_character_card_links_to_sheet`
- [x] Empty state / homepage content for anonymous → `test_navigation.py::test_empty_state_create_link`

## Profile (profile.html)

- [x] Profile page loads when logged in → `test_profile_e2e.py::test_profile_loads`
- [x] Profile redirects to login when not logged in → `test_profile_e2e.py::test_profile_redirects_when_not_logged_in`
- [x] Display name can be changed and persists → `test_profile_e2e.py::test_profile_display_name_change`
- [x] Other users listed with grant checkboxes → `test_profile_e2e.py::test_profile_shows_other_users`
- [x] GM badge and access note shown → `test_profile_e2e.py::test_profile_gm_badge`
- [x] Sound toggle saves preference → `test_profile_e2e.py::test_sound_toggle_saves`

## Character Editor — Basics (edit.html)

- [x] Character name can be edited and auto-saves → `test_edit_character.py::test_edit_auto_saves`
- [x] Owner dropdown visible only for GM users → `test_permissions.py::test_owner_dropdown_visible_for_admin`
- [x] Owner dropdown hidden for non-GM users → `test_permissions.py::test_owner_dropdown_hidden_for_nonadmin`
- [x] No JS console errors on editor page → `test_editor_controls.py::test_editor_has_no_javascript_console_errors`
- [x] Earned XP field updates budget → `test_editor_controls.py::test_earned_xp_updates_budget`
- [x] Notes textarea saves → `test_editor_controls.py::test_notes_saves`
- [x] Save status shows "Saved" → `test_editor_controls.py::test_save_status_indicator`

## Character Editor — School Selection

- [x] School dropdown loads school details via HTMX → `test_school_selection.py::test_school_selection_loads_details`
- [x] Switching schools updates details panel → `test_school_selection.py::test_switching_schools_updates_details`
- [x] School knack controls appear for selected school → `test_school_selection.py::test_school_knack_controls_appear`
- [x] School techniques displayed by Dan level → `test_school_selection.py::test_school_techniques_shown`
- [x] Fixed ring school auto-sets school ring → `test_school_rings.py::test_fixed_ring_school_sets_ring`
- [x] Multi-ring school shows ring dropdown → `test_school_rings.py::test_multi_ring_school_shows_dropdown`
- [x] "Air or Water" school shows ring dropdown → `test_school_rings.py::test_air_or_water_ring_dropdown`
- [x] Selecting ring from dropdown updates choice → `test_school_rings.py::test_selecting_ring_from_dropdown`
- [x] School ring min 3 enforced → `test_editor_controls.py::test_school_ring_min_3`
- [x] School ring max 6 → `test_editor_controls.py::test_school_ring_max_6`
- [x] Non-school ring max 5 → `test_editor_controls.py::test_nonschool_ring_max_5`
- [x] Changing school resets knacks → `test_school_rings.py::test_changing_school_resets_knacks`
- [x] Multi-ring to fixed-ring hides dropdown → `test_school_rings.py::test_changing_multi_to_fixed_hides_dropdown`
- [x] Mantis Wave-Treader defaults school ring to Void and bumps Void to 3 → `test_editor_controls.py::test_mantis_defaults_ring_to_void`
- [x] Priest (variable-ring school) still defaults ring to Water → `test_editor_controls.py::test_priest_still_defaults_ring_to_water`
- [x] Mantis Wave-Treader is selectable and saves as a first version → `test_editor_controls.py::test_mantis_school_is_selectable_and_saves`

## Character Editor — Rings

- [x] Ring +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_ring_change`
- [x] Non-school ring min 2 (- disabled) → `test_editor_controls.py::test_nonschool_ring_min_2`
- [x] Non-school ring max 5 (+ disabled) → `test_editor_controls.py::test_nonschool_ring_max_5`
- [x] School ring min 3 (- disabled) → `test_editor_controls.py::test_school_ring_min_3`
- [x] School ring max 6 (+ disabled) → `test_editor_controls.py::test_school_ring_max_6`
- [x] XP overspend turns remaining red → `test_live_xp.py::test_remaining_goes_negative_on_overspend`

## Character Editor — Knacks

- [x] Knack +/- buttons update XP → `test_live_xp.py::test_xp_updates_on_knack_change`
- [x] Knack - disabled at rank 1 → `test_editor_controls.py::test_knack_min_1`
- [x] Knack + disabled at rank 5 → `test_editor_controls.py::test_knack_max_5`
- [x] 4th Dan auto-raises school ring to 4 → `test_editor_controls.py::test_fourth_dan_auto_raises_school_ring`
- [x] 4th Dan school ring max is 7 → `test_editor_controls.py::test_fourth_dan_school_ring_max_7`
- [x] Drop below 4th Dan caps ring at 6 → `test_editor_controls.py::test_drop_below_4th_dan_caps_ring_at_6`
- [x] Drop below 4th Dan ring at 4 stays at 4 → `test_editor_controls.py::test_drop_below_4th_dan_ring_at_4_goes_to_3`
- [x] Ring max correct after repeated Dan toggle → `test_editor_controls.py::test_ring_max_correct_after_repeated_dan_toggle`
- [x] Ring max never exceeds bounds after many toggles → `test_editor_controls.py::test_ring_max_never_exceeds_bounds_after_many_toggles`
- [x] Ring at 5 stable across Dan toggle → `test_editor_controls.py::test_ring_at_5_stable_across_dan_toggle`

## Character Editor — Combat Skills

- [x] Attack/parry +/- update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry cannot exceed attack + 1 → `test_combat_skills.py::test_parry_cannot_exceed_attack_plus_1`
- [x] Attack cannot go below parry - 1 → `test_combat_skills.py::test_attack_cannot_lower_below_parry_minus_1`
- [x] Combat skills persist through apply → `test_combat_skills.py::test_create_with_combat_skills_and_publish`
- [x] XP updates on combat skill change → `test_live_xp.py::test_xp_updates_on_combat_skill_change`
- [x] Attack min 1 (- disabled) → `test_editor_controls.py::test_attack_min_1`
- [x] Attack max 5 (+ disabled) → `test_editor_controls.py::test_attack_max_5`

## Character Editor — Skills

- [x] Skill +/- buttons update XP → `test_live_xp.py::test_xp_updates_on_skill_change`
- [x] Skill - disabled at rank 0 → `test_editor_controls.py::test_skill_min_0`
- [x] Skill + disabled at rank 5 → `test_editor_controls.py::test_skill_max_5`
- [x] Basic skill XP increases spent → `test_editor_controls.py::test_basic_skill_xp_cost`
- [x] Advanced skill costs more → `test_editor_controls.py::test_advanced_skill_costs_more`

## Character Editor — Honor / Rank / Recognition

- [x] Honor +/- updates XP → `test_live_xp.py::test_xp_honor_change`
- [x] Honor min 1.0 (- disabled) → `test_editor_controls.py::test_honor_min`
- [x] Honor max 5.0 (+ disabled) → `test_editor_controls.py::test_honor_max`
- [x] Rank locked (both buttons disabled) → `test_editor_controls.py::test_rank_locked_buttons_disabled`
- [x] Recognition min 7.5 (- disabled) → `test_editor_controls.py::test_recognition_min_7_5`
- [x] Recognition max enforced → `test_editor_controls.py::test_recognition_max`
- [x] Halve sets recognition to 3.5 → `test_editor_controls.py::test_recognition_halve_sets_3_5`
- [x] Halve grants +3 XP → `test_editor_controls.py::test_recognition_halve_grants_3_xp`
- [x] Unhalve restores to 7.5 → `test_editor_controls.py::test_recognition_unhalve_restores`
- [x] Halved min is 3.5 → `test_editor_controls.py::test_recognition_halved_min_3_5`
- [x] Halved recognition can be raised → `test_editor_controls.py::test_recognition_halved_can_raise`

## Character Editor — GM-awarded Rank/Recognition Bonuses

- [x] GM-award button visible on editor → `test_gm_awards.py::test_award_button_visible_on_editor`
- [x] Award modal opens and closes → `test_gm_awards.py::test_award_modal_opens_and_closes`
- [x] Apply disabled without source text → `test_gm_awards.py::test_award_apply_disabled_without_source`
- [x] Apply disabled when both deltas are zero → `test_gm_awards.py::test_award_apply_disabled_when_both_zero`
- [x] Applying an award updates rank and recognition → `test_gm_awards.py::test_apply_award_updates_rank_and_recognition`
- [x] Award appears in history list → `test_gm_awards.py::test_award_appears_in_history_list`
- [x] First award locks Recognition +/- → `test_gm_awards.py::test_recognition_locked_after_first_award`
- [x] First award locks "Halve Recognition" checkbox → `test_gm_awards.py::test_recognition_halved_locked_after_first_award`
- [x] Editing an award's rank delta updates rank → `test_gm_awards.py::test_edit_award_rank_delta_updates_rank`
- [x] Deleting an award restores rank and recognition → `test_gm_awards.py::test_delete_award_restores_rank`
- [x] Source text edit does NOT trigger draft → `test_gm_awards.py::test_source_edit_does_not_trigger_modified_badge`
- [x] Reputation tab applies Good Reputation → `test_gm_awards.py::test_reputation_tab_applies_good_reputation`
- [x] Reputation award shows badge in history → `test_gm_awards.py::test_reputation_award_shows_badge_in_history`

## Character Editor — Advantages & Disadvantages

- [x] Advantage checkbox toggles XP → `test_live_xp.py::test_xp_updates_on_advantage_toggle`
- [x] Disadvantage checkbox adds XP to budget → `test_live_xp.py::test_xp_updates_on_disadvantage_toggle`
- [x] Wealthy disabled → `test_editor_controls.py::test_wealthy_disabled`
- [x] Poor disabled → `test_editor_controls.py::test_poor_disadvantage_disabled`
- [x] Campaign advantage toggles XP → `test_editor_controls.py::test_campaign_advantage_toggles_xp`
- [x] Campaign disadvantage toggles XP → `test_editor_controls.py::test_campaign_disadvantage_toggles_xp`

## Character Editor — Exclusive Pairs

- [x] Vain disables Unkempt → `test_exclusive_pairs.py::test_vain_disables_unkempt`
- [x] Unkempt disables Vain → `test_exclusive_pairs.py::test_unkempt_disables_vain`
- [x] Lucky and Unlucky can coexist → `test_exclusive_pairs.py::test_lucky_and_unlucky_can_coexist`
- [x] Imperial Favor disables Imperial Disdain → `test_exclusive_pairs.py::test_imperial_favor_disables_imperial_disdain`
- [x] Imperial Disdain disables Imperial Favor → `test_exclusive_pairs.py::test_imperial_disdain_disables_imperial_favor`
- [x] Quick Healer disables Slow Healer → `test_exclusive_pairs.py::test_quick_healer_disables_slow_healer`
- [x] Slow Healer disables Quick Healer → `test_exclusive_pairs.py::test_slow_healer_disables_quick_healer`
- [x] Virtue disables Unconventional → `test_exclusive_pairs.py::test_virtue_disables_unconventional`
- [x] Unconventional disables Virtue → `test_exclusive_pairs.py::test_unconventional_disables_virtue`
- [x] Righteous Sting disables Venomous Sting → `test_exclusive_pairs.py::test_righteous_disables_venomous`
- [x] Venomous Sting disables Righteous Sting → `test_exclusive_pairs.py::test_venomous_disables_righteous`
- [x] Disabled pair shows "Cannot be taken with" tooltip → `test_exclusive_pairs.py::test_exclusive_tooltip_shows_reason`
- [x] Unchecking re-enables the other → `test_exclusive_pairs.py::test_unchecking_reenables_pair`

## Character Editor — Advantage Detail Fields

- [x] Higher Purpose: text field appears → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Higher Purpose: text persists after reload → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Higher Purpose: skill checkboxes appear → `test_advantage_details.py::test_higher_purpose_skill_checkboxes`
- [x] Virtue: text field appears → `test_advantage_details.py::test_virtue_shows_text_field`
- [x] Virtue: text shown on sheet → `test_advantage_details.py::test_virtue_shows_text_field`
- [x] Specialization: text and dropdown appear → `test_advantage_details.py::test_specialization_shows_dropdown`
- [x] Dark Secret: text and player dropdown appear → `test_advantage_details.py::test_dark_secret_shows_fields`
- [x] Jealousy: text field appears → `test_advantage_details.py::test_jealousy_shows_text`
- [x] Good Reputation: text field appears → `test_advantage_details.py::test_good_reputation_shows_text`
- [x] Bad Reputation: text field appears → `test_advantage_details.py::test_bad_reputation_shows_text`
- [x] Unconventional: text field appears → `test_advantage_details.py::test_unconventional_shows_text`
- [x] Detail fields hidden when unchecked → `test_advantage_details.py::test_detail_hidden_when_unchecked`

## Character Editor — Auto-save

- [x] Changes auto-save and persist → `test_edit_character.py::test_edit_auto_saves`
- [x] Save status shows "Saved" → `test_editor_controls.py::test_save_status_indicator`

## Character Editor — Apply Changes Modal

- [x] Apply Changes button opens modal → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] Modal requires description → `test_apply_modal.py::test_apply_disabled_when_empty`
- [x] First version pre-populates "Initial character creation" → `test_apply_modal.py::test_first_version_prepopulates`
- [x] Subsequent versions blank → `test_apply_modal.py::test_subsequent_version_blank`
- [x] Quick-fill "adventure XP" → `test_apply_modal.py::test_quickfill_adventure_xp`
- [x] Quick-fill "mid-adventure" → `test_apply_modal.py::test_quickfill_mid_adventure`
- [x] Apply disabled when empty → `test_apply_modal.py::test_apply_disabled_when_empty`
- [x] Apply disabled without school selected → `test_apply_modal.py::test_apply_disabled_without_school`
- [x] School locked after publish → `test_apply_modal.py::test_school_locked_after_publish`
- [x] Cancel closes modal → `test_apply_modal.py::test_cancel_closes_modal`
- [x] Apply redirects to sheet → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] No draft banner after apply → `test_publish_revert.py::test_apply_then_no_draft_banner`

## Character Editor — Hidden Draft Visibility

- [ ] New character starts hidden, banner above Basics + Make Draft Visible button render → `test_create_character.py::test_new_character_starts_hidden_with_banner_and_button`
- [ ] Make Draft Visible button hides banner+button without reload, also persisted across reload → `test_create_character.py::test_make_draft_visible_button_hides_banner_and_button`
- [ ] Apply Changes also unhides the draft (banner/button absent on later edits) → `test_create_character.py::test_apply_changes_also_unhides_the_draft`
- [ ] Hidden character is not listed on the homepage for non-editors; appears once revealed → `test_create_character.py::test_hidden_draft_not_listed_on_homepage_for_non_editor`

## Character Sheet — Header & Permissions

- [x] Edit button visible for editor → `test_permissions.py::test_edit_delete_visible_for_editor`
- [x] Delete button visible for editor → `test_permissions.py::test_edit_delete_visible_for_editor`
- [x] Edit hidden for non-editor → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete hidden for non-editor → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete shows confirmation → `test_permissions.py::test_delete_confirmation_dialog`
- [x] Draft name visible to all → `test_edit_character.py::test_view_sheet_shows_published_name`

## Character Sheet — Draft Banners

- [x] "Draft" banner for never-applied → `test_banners.py::test_draft_banner_for_new_character`
- [x] "Draft changes" banner for modified → `test_banners.py::test_draft_changes_banner_after_edit`
- [x] No banner for clean → `test_banners.py::test_no_banner_after_apply`

## Character Sheet — Status Display

- [x] Honor displayed → `test_sheet_display.py::test_honor_displayed`
- [x] Rank displayed with "locked" → `test_sheet_display.py::test_rank_displayed_with_locked`
- [x] Recognition displayed → `test_sheet_display.py::test_recognition_displayed`
- [x] Stipend displayed → `test_sheet_display.py::test_stipend_displayed`
- [x] Stipend tooltip shows calculation → `test_sheet_advanced.py::test_stipend_tooltip`
- [x] Stipend with Household Wealth → `test_sheet_advanced.py::test_stipend_with_household_wealth`
- [x] Stipend with Merchant school → `test_sheet_advanced.py::test_stipend_with_merchant_school`

## Character Sheet — Tracking

- [x] Initial values show 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Light wounds + opens modal → `test_light_wounds.py::test_plus_opens_modal`
- [x] Light wounds modal: add to total → `test_light_wounds.py::test_modal_add_to_total`
- [x] Light wounds modal: set total directly → `test_light_wounds.py::test_modal_set_total`
- [x] Light wounds modal: take serious wounds and reset → `test_light_wounds.py::test_modal_take_serious_and_reset`
- [x] Light wounds - opens dropdown → `test_light_wounds.py::test_minus_dropdown_reset`
- [x] Light wounds - dropdown: reset to 0 → `test_light_wounds.py::test_minus_dropdown_reset`
- [x] Light wounds - dropdown: enter new total → `test_light_wounds.py::test_minus_dropdown_enter_new_total`
- [x] Light wounds - disabled at 0 → `test_light_wounds.py::test_minus_disabled_at_zero`
- [x] Light wounds persist via modal → `test_tracking.py::test_wound_tracking_persists`
- [x] Serious wounds +/- works → `test_tracking_advanced.py::test_serious_wounds_increment_decrement`
- [x] Serious wounds persist → `test_tracking_advanced.py::test_serious_wounds_persist`
- [x] Void points +/- works → `test_tracking.py::test_void_points_tracking`
- [x] Void points persist → `test_tracking_advanced.py::test_void_points_persist`
- [x] Void points max enforced → `test_tracking_advanced.py::test_void_points_max_enforced`
- [x] Wound - disabled at 0 → `test_tracking_advanced.py::test_wound_minus_disabled_at_zero`
- [x] Per-adventure renders with JSON → `test_tracking.py::test_tracking_renders_with_per_adventure_abilities`
- [x] Lucky toggle works → `test_tracking_advanced.py::test_lucky_toggle_works`
- [x] Lucky toggle persists → `test_tracking_advanced.py::test_lucky_toggle_persists`
- [x] Unlucky toggle shown → `test_sheet_advanced.py::test_unlucky_toggle`
- [x] Reset per-adventure → `test_tracking_advanced.py::test_reset_per_adventure`
- [x] Reset modal lists abilities to restore → `test_tracking_advanced.py::test_reset_modal_lists_abilities_to_restore`
- [x] Togashi 3rd Dan sheet shows Daily Athletics Raises tracker → `test_tracking_advanced.py::test_togashi_3rd_dan_daily_raises_tracker_row`
- [x] Per-day abilities have a dedicated Reset button with tooltip → `test_tracking_advanced.py::test_per_day_ability_has_its_own_reset_button_with_tooltip`
- [ ] Per-day Reset button renders to the LEFT of the +/- counter → `test_tracking_advanced.py::test_per_day_reset_button_renders_left_of_counter`
- [x] Per-day reset button is disabled until spent → `test_tracking_advanced.py::test_per_day_reset_button_disabled_until_spent`
- [x] Per-day reset button restores just that pool → `test_tracking_advanced.py::test_per_day_reset_button_restores_pool`
- [x] Per-day reset leaves other counters alone → `test_tracking_advanced.py::test_per_day_reset_leaves_other_counters_alone`
- [x] Per-adventure reset still clears per-day pools → `test_tracking_advanced.py::test_per_adventure_reset_also_clears_per_day_pools`
- [ ] Per-adventure reset also clears leftover action dice; summary mentions them → `test_tracking_advanced.py::test_per_adventure_reset_also_clears_action_dice`
- [ ] Per-adventure Reset button stays enabled when the only stale state is action dice → `test_tracking_advanced.py::test_reset_button_enabled_with_only_action_dice`
- [x] Non-per-day counter has no per-ability reset button → `test_tracking_advanced.py::test_non_per_day_counter_has_no_reset_button`
- [x] Tracking buttons hidden for non-editors → `test_permissions.py::test_tracking_buttons_hidden_for_nonadmin`

## Character Sheet — Skill Roll Display

- [x] Skills with rank show roll → `test_sheet_display.py::test_skill_with_rank_shows_roll`
- [x] Charming bonus on Etiquette → `test_sheet_display.py::test_charming_bonus_on_etiquette`
- [x] Fierce bonus on Bragging → `test_sheet_display.py::test_fierce_bonus_on_bragging`
- [x] Honor bonus on Bragging → `test_sheet_display.py::test_honor_bonus_on_bragging`
- [x] Discerning on Investigation → `test_skill_rolls_display.py::test_discerning_bonus_on_investigation`
- [x] Discerning on Interrogation → `test_skill_rolls_display.py::test_discerning_bonus_on_interrogation`
- [x] Genealogist on Heraldry → `test_skill_rolls_display.py::test_genealogist_bonus_on_heraldry`
- [x] Tactician on Strategy → `test_skill_rolls_display.py::test_tactician_bonus_on_strategy`
- [x] Tactician on History → `test_skill_rolls_display.py::test_tactician_bonus_on_history`
- [x] Worldly on Commerce → `test_skill_rolls_display.py::test_worldly_bonus_on_commerce`
- [x] History synergy on Culture → `test_skill_rolls_display.py::test_history_synergy_on_culture`
- [x] Acting synergy on Sincerity → `test_skill_rolls_display.py::test_acting_synergy_on_sincerity`
- [x] Recognition bonus on Bragging → `test_skill_rolls_display.py::test_recognition_bonus_on_bragging`
- [x] Transparent note on Sincerity → `test_skill_rolls_display.py::test_transparent_note_on_sincerity`
- [x] Unkempt note on Culture → `test_skill_rolls_display.py::test_unkempt_note_on_culture`
- [x] Thoughtless note on Tact → `test_skill_rolls_display.py::test_thoughtless_note_on_tact`

## Character Sheet — Advantages & Disadvantages Display

- [x] Advantages listed → `test_sheet_display.py::test_advantages_listed_on_sheet`
- [x] Advantage tooltip → `test_sheet_display.py::test_advantage_tooltip_on_hover`
- [x] Disadvantages listed → `test_sheet_advanced.py::test_disadvantage_listed_on_sheet`
- [x] Detail text shown inline → `test_sheet_advanced.py::test_advantage_detail_inline_on_sheet`
- [x] Campaign advantage XP reflected → `test_sheet_advanced.py::test_campaign_advantage_xp_on_sheet`

## Character Sheet — School Knacks

- [x] Expanded view shows full upstream rules text → `test_sheet_display.py::test_school_knack_expanded_shows_full_rules`

## Character Sheet — XP Summary

- [x] XP breakdown shown → `test_sheet_display.py::test_xp_breakdown_shown`
- [x] Budget shown → `test_sheet_display.py::test_xp_budget_includes_earned_and_disadvantages`
- [x] Overspend in red → `test_sheet_advanced.py::test_xp_overspend_red`
- [x] Disadvantages green → `test_sheet_advanced.py::test_disadvantages_green`
- [x] New category labels (School Knacks, Attack / Parry, HRR) and ordering → `test_sheet_display.py::test_xp_summary_new_labels_and_ordering`
- [x] Expansion panel collapsed by default → `test_sheet_display.py::test_xp_summary_collapsed_by_default`
- [x] Click to expand, switch sections, click same to collapse → `test_sheet_display.py::test_xp_summary_expand_switch_collapse`
- [x] HRR always shows Wasp Campaign reminder → `test_sheet_display.py::test_xp_summary_hrr_always_shows_wasp_note`
- [x] Empty categories are not clickable → `test_sheet_display.py::test_xp_summary_empty_categories_not_clickable`
- [x] Disadvantages box on bottom row, expandable → `test_sheet_display.py::test_xp_summary_disadvantages_on_bottom_row`
- [x] Grand total equals sum of category totals → `test_sheet_display.py::test_xp_summary_grand_total_matches_categories`

## Character Sheet — Version History

- [x] Collapsed by default → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Click expands → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Version details shown → `test_sheet_display.py::test_version_entry_shows_details`
- [x] Summary editable via API → `test_sheet_advanced.py::test_version_summary_inline_edit`
- [x] Summary preserved on reload → `test_sheet_advanced.py::test_version_edit_escape_cancels`
- [x] Revert not shown on latest → `test_sheet_display.py::test_revert_not_shown_on_latest`
- [x] Revert modal with reason → `test_publish_revert.py::test_revert_with_reason`
- [x] Revert reloads with old data → `test_publish_revert.py::test_revert_with_reason`

## Character Sheet — View as Non-Editor

- [x] Edit hidden → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete hidden → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Version history hidden → `test_permissions.py::test_version_history_hidden_for_nonadmin`
- [x] Tracking +/- buttons hidden for non-editors → `test_permissions.py::test_tracking_buttons_hidden_for_nonadmin`
- [x] /track endpoint forbidden for non-editors → `test_permissions.py::test_track_endpoint_forbidden_for_nonadmin`
- [x] Data visible → `test_permissions.py::test_character_visible_to_nonadmin`

---

## Pytest Marks

Tests are tagged with `pytest.mark.<mark>` so you can run a subset by feature area:
```bash
python3 -m pytest tests/e2e/ -m tracking --browser chromium
python3 -m pytest tests/e2e/ -m "skills or rings" --browser chromium
```

| Mark | Sections covered | Test files |
|------|-----------------|------------|
| `navigation` | Navigation | `test_smoke.py`, `test_navigation.py` |
| `homepage` | Homepage | `test_banners.py` |
| `profile` | Profile | `test_profile_e2e.py` |
| `school` | School Selection | `test_school_selection.py` |
| `school_rings` | School ring dropdown/interactions | `test_school_rings.py` |
| `rings` | Rings +/- | `test_live_xp.py`, `test_editor_controls.py` |
| `knacks` | Knacks +/- | `test_live_xp.py`, `test_editor_controls.py` |
| `combat_skills` | Attack/Parry | `test_combat_skills.py`, `test_live_xp.py`, `test_editor_controls.py` |
| `skills` | Skills +/- | `test_live_xp.py`, `test_editor_controls.py` |
| `honor_rank_recognition` | Honor/Rank/Recognition controls | `test_live_xp.py`, `test_editor_controls.py`, `test_gm_awards.py` |
| `gm_awards` | GM-awarded Rank/Recognition bonuses (modal, history, lock) | `test_gm_awards.py` |
| `responsive` | Responsive design sanity (overflow, hamburger, label widths) | `test_responsive.py` |
| `advantages` | Advantage/disadvantage checkboxes | `test_live_xp.py`, `test_editor_controls.py` |
| `exclusive_pairs` | Mutually exclusive pairs | `test_exclusive_pairs.py` |
| `advantage_details` | Detail fields (text, skills, dropdowns) | `test_advantage_details.py` |
| `autosave` | Auto-save, save status | `test_edit_character.py` |
| `apply_changes` | Apply Changes modal | `test_create_character.py`, `test_publish_revert.py`, `test_apply_modal.py` |
| `permissions` | Edit/delete visibility, non-editor | `test_permissions.py` |
| `banners` | Draft status banners | `test_banners.py` |
| `status_display` | Status section on sheet | `test_sheet_display.py`, `test_sheet_advanced.py` |
| `tracking` | Wounds, void points, per-adventure | `test_tracking.py`, `test_tracking_advanced.py`, `test_light_wounds.py`, `test_sheet_advanced.py` |
| `skill_rolls` | Skill roll display with bonuses | `test_sheet_display.py`, `test_skill_rolls_display.py` |
| `xp_summary` | XP breakdown on sheet | `test_sheet_display.py`, `test_sheet_advanced.py` |
| `version_history` | Version list, revert, inline edit | `test_publish_revert.py`, `test_sheet_display.py`, `test_sheet_advanced.py` |
| `groups` | Gaming groups, party effects, admin manage groups | `test_groups.py` |
| `rolls` | Click-to-roll dice, attack modal, wound check, iaijutsu, school abilities | `test_rolls.py`, `test_attack_modal.py`, `test_wound_check.py`, `test_iaijutsu_duel.py`, `test_sheet_js_errors.py`, `test_void_spending.py`, `test_school_abilities.py` |
| `sections` | Rich-text freeform sections | `test_sections.py` |

Marks are defined in `pytest.ini`. When adding a new test file, tag it with `pytestmark` at module level and add it to this table.

## Responsive Design Sanity Checks

- [x] Sheet page no horizontal overflow at phone width → `test_responsive.py::test_sheet_no_horizontal_overflow`
- [x] Edit page no horizontal overflow at phone width → `test_responsive.py::test_edit_no_horizontal_overflow`
- [x] Homepage no horizontal overflow at phone width → `test_responsive.py::test_homepage_no_horizontal_overflow`
- [x] Hamburger visible on phone, nav items hidden → `test_responsive.py::test_hamburger_visible_on_phone`
- [x] Hamburger toggle shows/hides nav items → `test_responsive.py::test_hamburger_toggle_shows_nav`
- [x] Nav visible without hamburger on desktop → `test_responsive.py::test_nav_visible_without_hamburger_on_desktop`
- [x] No zero-width truncated labels on editor → `test_responsive.py::test_no_zero_width_labels_on_editor`
- [x] No zero-width truncated labels on sheet → `test_responsive.py::test_no_zero_width_labels_on_sheet`

---

## Google Sheets Export

- [ ] Export to Sheets button visible to logged-in users on character sheet
- [ ] Export to Sheets button hidden for anonymous visitors
- [ ] Export button present alongside Edit/Delete for editors
- [ ] Success banner displays with link after export (requires mocked Google API)
- [ ] Error banner displays on export failure (requires mocked Google API)

---

## Character Import (mark: `import`)

Clicktests in `tests/e2e/test_import.py` cover the interactive surface.
Gemini is stubbed via `IMPORT_USE_TEST_STUB=1` (set in
`tests/e2e/conftest.py`); the stub dispatches on document-content
markers so the same fixtures drive both happy and rejection paths.

Entry points & nav:

- [x] Nav "New Character" dropdown opens on click -> `test_import.py::test_new_character_dropdown_opens_on_click`
- [x] Dropdown "Create a character" posts to /characters (pre-import
      flow) -> `test_import.py::test_dropdown_create_option_posts_to_characters`
- [x] Dropdown "Import a character" option navigates to /import -> `test_import.py::test_dropdown_import_option_navigates_to_import`
- [x] Dropdown closes on click-outside -> `test_import.py::test_dropdown_closes_on_click_outside`

Import form (`/import`):

- [x] Upload-file tab is selected by default -> `test_import.py::test_import_form_defaults_to_file_tab`
- [x] Tabs switch between file and URL panels -> `test_import.py::test_import_form_tabs_switch_visible_panel`
- [x] Submit with no file and no URL shows the inline error banner -> `test_import.py::test_submit_with_no_source_shows_inline_error`
- [x] Happy-path file import ends on the edit page -> `test_import.py::test_happy_file_import_ends_on_edit_page_with_banner`
- [x] Oversize file shows the 1 MB error banner -> `test_import.py::test_oversize_file_shows_size_error`
- [x] Unsupported-format file shows the format-error banner -> `test_import.py::test_unsupported_format_shows_format_error`

Progress page (`/import/progress/{id}`):

- [x] Happy path redirects to /characters/{id}/edit on success -> `test_import.py::test_progress_page_shows_stage_text_before_redirecting`
- [x] Error banner surfaces after a multi-character rejection -> `test_import.py::test_multi_character_fixture_shows_split_error`
- [x] Not-a-character-sheet rejection surfaces -> `test_import.py::test_not_a_character_sheet_fixture_shows_not_a_sheet_error`
- [ ] Progress page rejects jobs that belong to a different user
      (covered by unit suite
      `test_import_routes.py::test_progress_page_rejects_other_users_jobs`;
      awkward in Playwright because the shared browser context uses
      one auth header throughout a session)

Edit-page affordances:

- [x] Import Notes banner appears on drafts created by the importer -> `test_import.py::test_happy_file_import_ends_on_edit_page_with_banner`
- [x] Import Notes banner disappears after Apply Changes -> `test_import.py::test_edit_page_banner_disappears_after_apply_changes`
- [ ] Non-imported drafts do NOT show the banner (covered by unit
      suite: `test_import_routes.py::test_edit_page_no_import_banner_for_non_imported_characters`)

Kill switch & rate limit (covered by unit suite only):

- [ ] GET /import with `IMPORT_ENABLED=false` shows the 503 banner
      (unit: `test_import_routes.py::test_get_import_kill_switch_shows_503`;
      clicktest would need to restart the shared live server with
      a different env var, which the current harness doesn't support)
- [ ] Navbar "New Character" collapses to a single submit button when
      `IMPORT_ENABLED=false` OR unset (fail-closed default)
      (unit: `test_routes.py::TestImportKillSwitchNavBar`; same env-var
      restart limitation prevents a clicktest)
- [x] Navbar "New Character" shows dropdown with Import option when
      `IMPORT_ENABLED=true` -> `test_create_character.py::test_new_character_dropdown_shows_import_option_when_enabled`
      (the clicktest harness sets `IMPORT_ENABLED=true` on the live server)
- [ ] Rate-limit hit shows the banner
      (unit: `test_import_routes.py::test_post_rate_limit_blocks_before_job_creation`)

Responsive sanity:

- [x] /import - no horizontal overflow at phone width -> `test_import.py::test_import_page_no_horizontal_overflow_at_phone_width`
- [x] /import/progress/{id} - no horizontal overflow at phone width -> `test_import.py::test_progress_page_no_horizontal_overflow_at_phone_width`

JS-error sanity:

- [x] No JS errors on /import -> `test_import.py::test_no_js_errors_on_import_page`
- [x] No JS errors on /import/progress/{id} -> `test_import.py::test_no_js_errors_on_progress_page`

---

## Character Art

- [x] "Upload new art" button visible on edit page for users with edit access ->
      `test_character_art_upload.py::test_character_art_menu_visible_on_edit_page`
- [-] "Upload new art" button hidden for users without edit access
      (non-editors get a 403 on the edit page, proven by
      `test_art_routes.py::TestLandingPage::test_403_when_not_editor`;
      the button can never render because the page never renders)
- [x] Upload rejects non-image file with clear error banner ->
      `test_character_art_upload.py::test_upload_rejects_non_image_file`
- [-] Upload rejects oversized file (> 5 MB) with clear error banner
      (committing a > 5 MB fixture would bloat the repo; server-side 413
      verified by `test_art_routes.py::TestUploadEndpoint::test_oversized_upload_rejected_413`,
      banner wording shares the code path with the non-image-file clicktest)
- [x] Upload rejects image outside allowed aspect ratio with clear error banner ->
      `test_character_art_upload.py::test_upload_rejects_wrong_aspect_ratio`
- [x] Upload of valid PNG redirects to crop page ->
      `test_character_art_upload.py::test_upload_and_save_crop_end_to_end`
- [-] Upload of valid JPG redirects to crop page
      (format variant of the PNG path; server-side decode proven by
      `test_art_routes.py::TestUploadEndpoint::test_valid_upload_redirects_to_crop[jpg-_jpeg_bytes]`)
- [-] Upload of valid WEBP redirects to crop page
      (same: `test_valid_upload_redirects_to_crop[webp-_webp_bytes]`)
- [x] Crop page seeds the crop box from detected face bbox ->
      `test_character_art_upload.py::test_upload_and_save_crop_end_to_end`
      (the `wait_for_function` on `input[name=w]` > 0 confirms Cropper
      seeded its box from the detected bbox emitted by `detect_face`)
- [-] Crop page falls back to centered-square when no face detected
      (fully covered by `test_art_face_detect.py::TestEndToEndNoFaceFixture`
      at the detector layer; same Cropper-init path)
- [-] Crop page enforces locked aspect ratio during drag
      (library concern: we'd be testing Cropper.js, not our code)
- [x] Save-crop writes full + headshot, redirects back to edit page with success banner ->
      `test_character_art_upload.py::test_upload_and_save_crop_end_to_end`
- [x] Overwrite confirm modal appears when replacing existing art ->
      `test_character_art_upload.py::test_overwrite_modal_appears_when_replacing_existing_art`
- [x] Delete-art confirm modal removes art and reverts to placeholder ->
      `test_character_art_upload.py::test_delete_art_dropdown_entry_appears_when_art_exists`
      (covers dropdown entry visibility + successful deletion + banner;
      the 2-click Alpine confirm itself is timing-flaky in Playwright and
      is unit-tested via `test_art_routes.py::TestDeleteEndpoint`)
- [x] Character list page shows headshot for characters that have art ->
      `test_character_art_display.py::test_list_page_shows_headshot_for_character_with_art`
- [x] Character list page shows placeholder for characters without art ->
      `test_character_art_display.py::test_list_page_shows_headshot_for_character_with_art`
      (same test: two characters rendered, one with img and one with placeholder)
- [x] Character list page does not overflow horizontally at 375 px viewport ->
      `test_responsive.py::test_homepage_headshot_placeholder_fits_card_at_phone_width`
      + `test_homepage_no_horizontal_overflow`
- [x] View Sheet floats full art to the right of the school section at >= lg breakpoint ->
      `test_character_art_display.py::test_sheet_page_shows_art_grid_when_character_has_art`
- [x] View Sheet stacks full art and school section below lg breakpoint ->
      `test_responsive.py::test_sheet_no_horizontal_overflow_across_widths`
      (covers 375 / 768 / 1280 px)
- [x] View Sheet omits art block for characters without art (no empty column) ->
      `test_character_art_display.py::test_sheet_page_hides_art_grid_when_character_has_no_art`
- [x] "Generate with AI" button opens step 1 (gender) ->
      `test_character_art_generate.py::test_generate_wizard_step1_opens_from_dropdown`
- [x] Step 1 -> step 2 carries gender forward; pronouns are correct ->
      `test_character_art_generate.py::test_wizard_carries_gender_forward_with_correct_pronoun`
- [x] Step 2 age checkbox cannot be unchecked ->
      `test_character_art_generate.py::test_age_checkbox_cannot_be_unchecked`
- [x] Step 2 optional rows disable their text input until the checkbox is checked ->
      `test_character_art_generate.py::test_optional_rows_disable_text_input_until_checkbox_checked`
- [x] Step 2 "Create Prompt" assembles the prompt and advances to step 3 ->
      `test_character_art_generate.py::test_create_prompt_advances_to_step3_with_textarea`
- [x] Step 3 textarea is editable before "Generate Art" is clicked ->
      `test_character_art_generate.py::test_create_prompt_advances_to_step3_with_textarea`
      (asserts textarea.is_disabled() is False)
- [-] Step 3 textarea locks while generation is in flight; unlocks on success or failure
      (the locked-while-generating state is transient and hard to reliably
      catch in Playwright - the stub returns bytes within milliseconds. The
      unlocked-on-completion state IS exercised by
      `test_generation_happy_path_in_place_crop_and_save`; Alpine's
      `:disabled="state === 'generating'"` binding is the only code path
      and it's unit-tested via `TestReviewTemplateHasCropper`)
- [x] Successful generation shows the generated art + Cropper on the SAME review page ->
      `test_character_art_generate.py::test_generation_happy_path_in_place_crop_and_save`
- [-] Failed generation shows the error + re-enables textarea for retry
      (route-level failure paths are covered by
      `test_art_routes.py::TestGenerateStatusEndpoint::test_failed_payload_includes_error_code_and_message`;
      driving a failure in the clicktest env would require toggling the
      rate-limit per-test, which is process-wide state on the uvicorn
      subprocess. Left as a Phase 11 follow-up if we ever flip on a
      per-request failure injector)
- [-] Generation stub returns the expected canned image based on prompt keyword (smoke check)
      (the stub itself is exhaustively unit-tested at
      `test_art_generate.py::TestStubMode` - 5 cases including distinct
      content per keyword and no-HTTP-in-stub-mode)
- [-] Per-user rate limit blocks the 26th generation in 24 h with a clear banner
      (route-level 429 proven by `test_art_routes.py::TestGenerateSubmit::test_429_when_rate_limit_hit`;
      driving 26 generations in a clicktest would take minutes and the
      rate-limit counter is process-wide state)
- [x] ART_GEN_ENABLED=false disables the "Generate with AI" button with a disabled-state tooltip ->
      `test_character_art_generate.py::test_generate_entry_enabled_when_art_gen_enabled`
      (verifies the live link branch; the disabled branch is unit-tested at
      `test_art_routes.py::TestEditPageGenerateLink::test_generate_with_ai_shows_disabled_when_switch_off`)
- [-] Deleting the character also removes its S3 art keys (checked via orphan cleanup)
      (S3 key lifecycle isn't browser-visible; fully covered by
      `test_art_backup.py::TestCharacterDeleteRemovesArt` +
      `TestCleanupOrphans` cases at the unit layer)

---

## Coverage Summary

**Covered:** ~280 test functions across 32 test files
**Uncovered:** 0

All interactive UI features are covered by at least one e2e clicktest.
