# E2E Clicktest Feature Coverage

Every interactive UI feature should have at least one clicktest. This file tracks coverage.
When adding a feature, add lines here first (marked `[ ]`). After writing the clicktest, mark `[x]` with the test reference.

---

## Navigation (base.html)

- [x] Homepage loads → `test_smoke.py::test_homepage_loads`
- [x] "New Character" button creates character and redirects to edit → `test_create_character.py::test_create_and_edit_character`
- [x] Profile link navigates to /profile → `test_profile_e2e.py::test_profile_loads`
- [ ] Logout link logs out and redirects
- [ ] Login link navigates to Discord OAuth
- [ ] Login via test-login secret URL creates session and redirects

## Homepage (index.html)

- [x] Character list displays characters → `test_create_character.py::test_create_and_edit_character`
- [x] Draft badge shown for never-applied characters → `test_banners.py::test_homepage_draft_badge`
- [x] "Draft changes" badge shown for characters modified since last version → `test_banners.py::test_homepage_draft_changes_badge`
- [x] No badge shown for characters matching their latest version → `test_banners.py::test_homepage_no_badge_after_apply`
- [x] Character card links to correct character sheet → `test_banners.py::test_character_card_links_to_sheet`
- [ ] Empty state shows "Create Your First Character"

## Profile (profile.html)

- [x] Profile page loads when logged in → `test_profile_e2e.py::test_profile_loads`
- [x] Profile redirects to login when not logged in → `test_profile_e2e.py::test_profile_redirects_when_not_logged_in`
- [x] Display name can be changed and persists after save → `test_profile_e2e.py::test_profile_display_name_change`
- [ ] Other users listed with grant checkboxes
- [ ] GM users shown with "GM" badge and disabled (always-checked) checkbox
- [ ] Granting access to a non-GM user persists after save
- [ ] Revoking access from a non-GM user persists after save

## Character Editor — Basics (edit.html)

- [x] Character name can be edited and auto-saves → `test_edit_character.py::test_edit_auto_saves`
- [x] Owner dropdown visible only for GM users → `test_permissions.py::test_owner_dropdown_visible_for_admin`
- [x] Owner dropdown hidden for non-GM users → `test_permissions.py::test_owner_dropdown_hidden_for_nonadmin`
- [ ] Owner dropdown reassigns character and updates player name
- [ ] Earned XP field updates XP calculations live
- [ ] Notes textarea saves

## Character Editor — School Selection

- [x] School dropdown loads school details via HTMX → `test_school_selection.py::test_school_selection_loads_details`
- [x] Switching schools updates details panel → `test_school_selection.py::test_switching_schools_updates_details`
- [x] School knack controls appear for selected school → `test_school_selection.py::test_school_knack_controls_appear`
- [x] School techniques displayed by Dan level → `test_school_selection.py::test_school_techniques_shown`
- [ ] School with fixed ring auto-sets school ring
- [ ] School with "any non-Void" ring shows ring dropdown
- [ ] School with "Air or Water" ring shows ring dropdown
- [ ] Selecting a ring from the dropdown updates school_ring_choice
- [x] School ring enforces minimum of 3 → `test_editor_controls.py::test_school_ring_min_3`
- [x] School ring allows maximum of 6 → `test_editor_controls.py::test_school_ring_max_6`
- [x] Non-school rings max at 5 → `test_editor_controls.py::test_nonschool_ring_max_5`
- [ ] Changing school resets knacks to match new school's knacks
- [ ] Changing school from multi-ring to fixed-ring hides the ring dropdown

## Character Editor — Rings

- [x] Ring +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_ring_change`
- [x] Non-school ring minimum is 2 (- disabled) → `test_editor_controls.py::test_nonschool_ring_min_2`
- [x] Non-school ring maximum is 5 (+ disabled) → `test_editor_controls.py::test_nonschool_ring_max_5`
- [x] School ring minimum is 3 (- disabled) → `test_editor_controls.py::test_school_ring_min_3`
- [x] School ring maximum is 6 (+ disabled) → `test_editor_controls.py::test_school_ring_max_6`
- [x] XP overspend turns remaining XP red → `test_live_xp.py::test_remaining_goes_negative_on_overspend`

## Character Editor — Knacks

- [x] Knack +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_knack_change`
- [x] Knack - button disabled at rank 1 → `test_editor_controls.py::test_knack_min_1`
- [x] Knack + button disabled at rank 5 → `test_editor_controls.py::test_knack_max_5`

## Character Editor — Combat Skills

- [x] Attack +/- buttons update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry +/- buttons update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry cannot exceed attack + 1 → `test_combat_skills.py::test_parry_cannot_exceed_attack_plus_1`
- [x] Attack cannot go below parry - 1 → `test_combat_skills.py::test_attack_cannot_lower_below_parry_minus_1`
- [x] Combat skills persist through apply changes → `test_combat_skills.py::test_create_with_combat_skills_and_publish`
- [x] XP updates on combat skill change → `test_live_xp.py::test_xp_updates_on_combat_skill_change`
- [x] Attack minimum is 1 (- disabled) → `test_editor_controls.py::test_attack_min_1`
- [x] Attack maximum is 5 (+ disabled) → `test_editor_controls.py::test_attack_max_5`

## Character Editor — Skills

- [x] Skill +/- buttons update XP → `test_live_xp.py::test_xp_updates_on_skill_change`
- [x] Skill - button disabled at rank 0 → `test_editor_controls.py::test_skill_min_0`
- [x] Skill + button disabled at rank 5 → `test_editor_controls.py::test_skill_max_5`
- [ ] Basic skill XP cost matches expected formula
- [ ] Advanced skill XP cost is higher than basic skill at same rank

## Character Editor — Honor

- [x] Honor +/- updates XP → `test_live_xp.py::test_xp_honor_change`
- [x] Honor minimum 1.0 (- disabled) → `test_editor_controls.py::test_honor_min`
- [x] Honor maximum 5.0 (+ disabled) → `test_editor_controls.py::test_honor_max`

## Character Editor — Rank

- [x] Rank - button permanently disabled → `test_editor_controls.py::test_rank_locked_buttons_disabled`
- [x] Rank + button permanently disabled → `test_editor_controls.py::test_rank_locked_buttons_disabled`

## Character Editor — Recognition

- [x] Recognition minimum 7.5 (- disabled) → `test_editor_controls.py::test_recognition_min_7_5`
- [x] "Halve starting Recognition" sets recognition to 3.5 → `test_editor_controls.py::test_recognition_halve_sets_3_5`
- [x] "Halve starting Recognition" grants +3 XP → `test_editor_controls.py::test_recognition_halve_grants_3_xp`
- [x] Unchecking halve restores recognition to 7.5 → `test_editor_controls.py::test_recognition_unhalve_restores`
- [x] With halve checked, recognition minimum is 3.5 → `test_editor_controls.py::test_recognition_halved_min_3_5`
- [ ] Recognition maximum is rank * 1.5 = 11.25 (+ disabled)
- [ ] With halve checked, recognition can be raised above 3.5 (costs XP)

## Character Editor — Advantages & Disadvantages

- [x] Advantage checkbox toggles XP cost → `test_live_xp.py::test_xp_updates_on_advantage_toggle`
- [x] Disadvantage checkbox adds XP to budget → `test_live_xp.py::test_xp_updates_on_disadvantage_toggle`
- [x] Wealthy checkbox is disabled → `test_editor_controls.py::test_wealthy_disabled`
- [x] Poor disadvantage checkbox is disabled → `test_editor_controls.py::test_poor_disadvantage_disabled`
- [ ] Campaign advantage checkboxes toggle XP
- [ ] Campaign disadvantage checkboxes toggle XP

## Character Editor — Exclusive Pairs

- [x] Checking Vain disables Unkempt → `test_exclusive_pairs.py::test_vain_disables_unkempt`
- [x] Checking Unkempt disables Vain → `test_exclusive_pairs.py::test_unkempt_disables_vain`
- [x] Checking Lucky disables Unlucky → `test_exclusive_pairs.py::test_lucky_disables_unlucky`
- [x] Checking Unlucky disables Lucky → `test_exclusive_pairs.py::test_unlucky_disables_lucky`
- [x] Checking Imperial Favor disables Imperial Disdain → `test_exclusive_pairs.py::test_imperial_favor_disables_imperial_disdain`
- [x] Checking Imperial Disdain disables Imperial Favor → `test_exclusive_pairs.py::test_imperial_disdain_disables_imperial_favor`
- [x] Checking Quick Healer disables Slow Healer → `test_exclusive_pairs.py::test_quick_healer_disables_slow_healer`
- [x] Checking Slow Healer disables Quick Healer → `test_exclusive_pairs.py::test_slow_healer_disables_quick_healer`
- [x] Checking Virtue disables Unconventional → `test_exclusive_pairs.py::test_virtue_disables_unconventional`
- [x] Checking Unconventional disables Virtue → `test_exclusive_pairs.py::test_unconventional_disables_virtue`
- [x] Checking Family Reckoning: Righteous Sting disables Venomous Sting → `test_exclusive_pairs.py::test_righteous_disables_venomous`
- [x] Checking Family Reckoning: Venomous Sting disables Righteous Sting → `test_exclusive_pairs.py::test_venomous_disables_righteous`
- [x] Disabled exclusive pair shows "Cannot be taken with X" in tooltip → `test_exclusive_pairs.py::test_exclusive_tooltip_shows_reason`
- [x] Unchecking one of a pair re-enables the other → `test_exclusive_pairs.py::test_unchecking_reenables_pair`
- [ ] Checking Wealthy disables Poor (futureproofing, both currently disabled)
- [ ] Checking Poor disables Wealthy (futureproofing, both currently disabled)

## Character Editor — Advantage Detail Fields

- [x] Higher Purpose: text field appears when checked → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Higher Purpose: text persists after reload → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [ ] Higher Purpose: skill checkboxes appear when checked
- [ ] Higher Purpose: selected skills persist after reload
- [x] Virtue: text field appears when checked → `test_advantage_details.py::test_virtue_shows_text_field`
- [x] Virtue: text appears on character sheet after apply → `test_advantage_details.py::test_virtue_shows_text_field`
- [ ] Specialization: text field and single skill dropdown appear
- [ ] Dark Secret: text field and player dropdown appear
- [ ] Jealousy: text field appears
- [ ] Good Reputation: text field appears
- [ ] Bad Reputation: text field appears
- [ ] Unconventional: text field appears
- [ ] Detail fields hidden when advantage is unchecked

## Character Editor — Auto-save

- [x] Changes auto-save and persist across page reload → `test_edit_character.py::test_edit_auto_saves`
- [ ] Save status indicator shows "Saving..." then "Saved"
- [ ] Multiple rapid changes debounce into single save

## Character Editor — Apply Changes Modal

- [x] Apply Changes button opens modal → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] Modal requires description text → `test_apply_modal.py::test_apply_disabled_when_empty`
- [x] Modal pre-populates "Initial character creation" for first version → `test_apply_modal.py::test_first_version_prepopulates`
- [x] Modal description blank for subsequent versions → `test_apply_modal.py::test_subsequent_version_blank`
- [x] "Spending XP from the latest adventure" quick-fill works → `test_apply_modal.py::test_quickfill_adventure_xp`
- [x] "Spending some leftover XP mid-adventure" quick-fill works → `test_apply_modal.py::test_quickfill_mid_adventure`
- [x] Apply button disabled when description empty → `test_apply_modal.py::test_apply_disabled_when_empty`
- [x] Cancel button closes modal without applying → `test_apply_modal.py::test_cancel_closes_modal`
- [x] Successful apply redirects to view sheet → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] No draft banner shown after successful apply → `test_publish_revert.py::test_apply_then_no_draft_banner`

## Character Sheet — Header & Permissions

- [x] Edit button visible when viewer has edit permission → `test_permissions.py::test_edit_delete_visible_for_editor`
- [x] Delete button visible when viewer has edit permission → `test_permissions.py::test_edit_delete_visible_for_editor`
- [x] Edit button hidden when viewer lacks permission → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete button hidden when viewer lacks permission → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete button shows confirmation dialog → `test_permissions.py::test_delete_confirmation_dialog`
- [x] Draft name visible to all viewers → `test_edit_character.py::test_view_sheet_shows_published_name`

## Character Sheet — Draft Banners

- [x] "Draft" banner shown for never-applied characters → `test_banners.py::test_draft_banner_for_new_character`
- [x] "Draft changes" banner shown for modified characters → `test_banners.py::test_draft_changes_banner_after_edit`
- [x] No banner shown for cleanly applied characters → `test_banners.py::test_no_banner_after_apply`

## Character Sheet — Status Display

- [x] Honor value displayed → `test_sheet_display.py::test_honor_displayed`
- [x] Rank value displayed with "locked" label → `test_sheet_display.py::test_rank_displayed_with_locked`
- [x] Recognition value displayed → `test_sheet_display.py::test_recognition_displayed`
- [x] Stipend displayed with koku/year → `test_sheet_display.py::test_stipend_displayed`
- [ ] Stipend tooltip shows calculation breakdown
- [ ] Stipend changes with Household Wealth advantage
- [ ] Stipend changes with Merchant/Shosuro Actor school
- [ ] Rank tooltip shows modifiers (Good Reputation, Imperial Favor, Bad Reputation)
- [ ] Recognition tooltip shows modifiers

## Character Sheet — Tracking

- [x] Light wounds initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Serious wounds initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Void points initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Light wounds +/- and persist → `test_tracking.py::test_wound_tracking_persists`
- [x] Serious wounds +/- works → `test_tracking_advanced.py::test_serious_wounds_increment_decrement`
- [x] Serious wounds persist → `test_tracking_advanced.py::test_serious_wounds_persist`
- [x] Void points +/- works → `test_tracking.py::test_void_points_tracking`
- [x] Void points persist → `test_tracking_advanced.py::test_void_points_persist`
- [x] Void points + disabled at max → `test_tracking_advanced.py::test_void_points_max_enforced`
- [x] Wound - buttons disabled at 0 → `test_tracking_advanced.py::test_wound_minus_disabled_at_zero`
- [x] Per-adventure abilities render with JSON data → `test_tracking.py::test_tracking_renders_with_per_adventure_abilities`
- [x] Lucky toggle shown and works → `test_tracking_advanced.py::test_lucky_toggle_works`
- [x] Lucky toggle persists → `test_tracking_advanced.py::test_lucky_toggle_persists`
- [x] Reset Per-Adventure Abilities resets toggles → `test_tracking_advanced.py::test_reset_per_adventure`
- [ ] Unlucky toggle shown for characters with Unlucky
- [ ] Per-adventure counter +/- for 3rd Dan free raises
- [ ] Conviction/Worldliness/Otherworldliness knack counters
- [x] Tracking functional for non-editors → `test_permissions.py::test_tracking_functional_for_nonadmin`

## Character Sheet — Skills Display

- [x] Skills with rank > 0 show roll calculation → `test_sheet_display.py::test_skill_with_rank_shows_roll`
- [x] Charming bonus shown on roll → `test_sheet_display.py::test_charming_bonus_on_etiquette`
- [x] Fierce bonus shown on roll → `test_sheet_display.py::test_fierce_bonus_on_bragging`
- [x] Honor bonus shown on roll → `test_sheet_display.py::test_honor_bonus_on_bragging`
- [ ] Discerning bonus shown on Investigation/Interrogation
- [ ] Genealogist bonus shown on Heraldry
- [ ] Tactician bonus shown on Strategy/History
- [ ] Worldly bonus shown on Commerce/Underworld
- [ ] History synergy bonus shown on Culture/Law/Strategy
- [ ] Acting synergy bonus shown on Sincerity/Intimidation/Sneaking
- [ ] Recognition bonus shown on Bragging
- [ ] Transparent note shown on Sincerity
- [ ] Unkempt note shown on Culture
- [ ] Thoughtless note shown on Tact/Sincerity
- [ ] Higher Purpose conditional bonus shown on selected skills
- [ ] Specialization conditional bonus shown on selected skill

## Character Sheet — Advantages & Disadvantages Display

- [x] Advantages listed with names → `test_sheet_display.py::test_advantages_listed_on_sheet`
- [x] Advantage tooltip shows description → `test_sheet_display.py::test_advantage_tooltip_on_hover`
- [ ] Disadvantages listed with names and tooltips
- [ ] Advantage detail text shown inline (e.g., "Virtue — Courage")
- [ ] Dark Secret shows "known by [player name]"
- [ ] Campaign advantages shown in own section
- [ ] Campaign disadvantages shown in own section

## Character Sheet — XP Summary

- [x] XP breakdown shows all categories → `test_sheet_display.py::test_xp_breakdown_shown`
- [x] Budget shown → `test_sheet_display.py::test_xp_budget_includes_earned_and_disadvantages`
- [ ] Overspend shown in red
- [ ] Disadvantages shown as negative (green)

## Character Sheet — Version History

- [x] Version history collapsed by default → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Click header expands history → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Version entries show number, date, author, summary → `test_sheet_display.py::test_version_entry_shows_details`
- [ ] Summary editable inline (click to edit, enter to save)
- [ ] Inline edit: Escape cancels without saving
- [x] Revert button not shown on latest version → `test_sheet_display.py::test_revert_not_shown_on_latest`
- [x] Revert button opens modal with reason → `test_publish_revert.py::test_revert_with_reason`
- [x] Revert with reason reloads with old data → `test_publish_revert.py::test_revert_with_reason`

## Character Sheet — View as Non-Editor

- [x] Edit button hidden for non-editors → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Delete button hidden for non-editors → `test_permissions.py::test_edit_delete_hidden_for_nonadmin`
- [x] Version history hidden for non-editors → `test_permissions.py::test_version_history_hidden_for_nonadmin`
- [x] Tracking functional for non-editors → `test_permissions.py::test_tracking_functional_for_nonadmin`
- [x] Character data visible to non-editors → `test_permissions.py::test_character_visible_to_nonadmin`

---

## Coverage Summary

**Covered:** ~100 features across 111 test functions (14 test files)
**Uncovered:** ~45 features marked `[ ]`

**Remaining gaps (lower priority):**
- Login/logout/OAuth flows (hard to test without real Discord)
- Profile access grant/revoke (needs multi-user interaction)
- School ring dropdown for multi-ring schools
- Individual skill roll bonus display (Discerning, Genealogist, etc.)
- Per-adventure counters for 3rd Dan, Conviction, Worldliness, Otherworldliness
- Inline version summary editing
- Stipend tooltip breakdown
- Various display-only features (tooltips, red overspend, green disadvantages)
