# E2E Clicktest Feature Coverage

Every interactive UI feature should have at least one clicktest. This file tracks coverage.
When adding a feature, add lines here first (marked `[ ]`). After writing the clicktest, mark `[x]` with the test reference.

---

## Navigation (base.html)

- [x] Homepage loads → `test_smoke.py::test_homepage_loads`
- [x] "New Character" button creates character and redirects to edit → `test_create_character.py::test_create_and_edit_character`
- [x] Profile link navigates to /profile → `test_profile_e2e.py::test_profile_loads`
- [x] Logout link visible and points to /auth/logout → `test_navigation.py::test_logout_link_exists`
- [x] Login link visible when anonymous → `test_navigation.py::test_login_link_visible_when_anonymous`
- [x] Test-login URL returns 403 without valid token → `test_navigation.py::test_test_login_creates_session`

## Dice Rolling

- [x] Click a skill row opens the modal with the skill name → `test_rolls.py::test_click_skill_opens_modal_with_skill_name`
- [x] Click Attack opens modal with "Attack" title → `test_rolls.py::test_click_attack_opens_modal_with_attack_title`
- [x] Click Parry opens modal with "Parry" title → `test_rolls.py::test_click_parry_opens_modal`
- [x] Click a Ring opens an Athletics roll modal → `test_rolls.py::test_click_ring_opens_athletics_modal`
- [x] Modal shows Total and dice after the animation phase → `test_rolls.py::test_modal_shows_total_and_dice_after_animation`
- [x] Modal close button hides the modal → `test_rolls.py::test_modal_close_button`
- [x] Impaired character's roll modal shows "10s not rerolled" note → `test_rolls.py::test_impaired_character_modal_shows_no_reroll_note`
- [x] Impaired indicator visible on the sheet when wounds ≥ Earth → `test_rolls.py::test_impaired_indicator_visible_on_sheet`
- [x] Impaired indicator absent when healthy → `test_rolls.py::test_impaired_indicator_absent_when_healthy`
- [x] Disabling animation in profile shows result panel immediately → `test_rolls.py::test_disable_animation_preference`
- [x] Athletics roll modal title includes the ring name → `test_rolls.py::test_athletics_label_in_modal`

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

## Gaming Groups

- [x] Set group via editor dropdown persists → `test_groups.py::test_set_group_via_editor_persists`
- [x] Setting group does not create a "modified" badge → `test_groups.py::test_set_group_does_not_create_modified_badge`
- [x] Homepage clusters characters by group with section headings → `test_groups.py::test_homepage_clusters_characters_by_group`
- [x] Party member's Thoughtless adds inline +10 note on other character's Tact → `test_groups.py::test_party_thoughtless_inline_on_other_tact`
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

## Character Editor — Basics (edit.html)

- [x] Character name can be edited and auto-saves → `test_edit_character.py::test_edit_auto_saves`
- [x] Owner dropdown visible only for GM users → `test_permissions.py::test_owner_dropdown_visible_for_admin`
- [x] Owner dropdown hidden for non-GM users → `test_permissions.py::test_owner_dropdown_hidden_for_nonadmin`
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
- [x] Lucky disables Unlucky → `test_exclusive_pairs.py::test_lucky_disables_unlucky`
- [x] Unlucky disables Lucky → `test_exclusive_pairs.py::test_unlucky_disables_lucky`
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
- [x] Cancel closes modal → `test_apply_modal.py::test_cancel_closes_modal`
- [x] Apply redirects to sheet → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] No draft banner after apply → `test_publish_revert.py::test_apply_then_no_draft_banner`

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
| `honor_rank_recognition` | Honor/Rank/Recognition controls | `test_live_xp.py`, `test_editor_controls.py` |
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

Marks are defined in `pytest.ini`. When adding a new test file, tag it with `pytestmark` at module level and add it to this table.

---

## Coverage Summary

**Covered:** ~180 features across 170 test functions (17 test files)
**Uncovered:** 0

All interactive UI features are covered by at least one e2e clicktest.
