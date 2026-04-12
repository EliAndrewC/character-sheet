# E2E Clicktest Feature Coverage

Every interactive UI feature should have at least one clicktest. This file tracks coverage.
When adding a feature, add lines here first (marked `[ ]`). After writing the clicktest, mark `[x]` with the test reference.

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

## Attack Modal

- [x] Attack opens attack modal (not dice roller) -> `test_attack_modal.py::test_attack_opens_attack_modal`
- [x] Feint does NOT open attack modal -> `test_attack_modal.py::test_feint_does_not_open_attack_modal`
- [x] Parry does NOT open attack modal -> `test_attack_modal.py::test_parry_does_not_open_attack_modal`
- [x] Probability table with Hit % column -> `test_attack_modal.py::test_attack_modal_shows_probability_table`
- [x] TN dropdown shows common values -> `test_attack_modal.py::test_attack_modal_tn_dropdown`
- [x] Attack roll shows HIT or MISSED -> `test_attack_modal.py::test_attack_roll_shows_hit_or_miss`
- [x] Hit shows Make Damage Roll button -> `test_attack_modal.py::test_attack_hit_shows_damage_roll_button`
- [x] Dice animation visible during attack roll -> `test_attack_modal.py::test_attack_dice_animation_visible`
- [x] Damage roll produces result after hit -> `test_attack_modal.py::test_attack_damage_roll_produces_result`

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

## School-Specific Abilities

- [x] Bayushi 3rd Dan feint damage button -> `test_school_abilities.py::test_bayushi_feint_damage_button`
- [x] Shiba 3rd Dan parry damage button -> `test_school_abilities.py::test_shiba_parry_damage_button`
- [x] Feint temp VP button (non-Akodo) -> `test_school_abilities.py::test_feint_temp_vp_button_for_bayushi`
- [x] Hida 3rd Dan reroll selection UI -> `test_school_abilities.py::test_hida_reroll_selection_appears`
- [x] Merchant post-roll VP buttons -> `test_school_abilities.py::test_merchant_post_roll_vp_buttons`
- [x] Mirumoto 3rd Dan round points counter -> `test_school_abilities.py::test_mirumoto_round_points_counter`
- [x] Daidoji 3rd Dan counterattack flag set -> `test_school_abilities.py::test_daidoji_counterattack_school_flag`
- [x] Akodo 1st Dan attack formula has extra rolled die -> `test_school_abilities.py::test_akodo_1st_dan_formula_display`
- [x] Matsu Bushi initiative always rolls 10 dice -> `test_school_abilities.py::test_matsu_initiative_10_dice`
- [x] Kakita Duelist initiative has phase-zero flag -> `test_school_abilities.py::test_kakita_initiative_phase_0`
- [x] Isawa Duelist attack damage ring is Water -> `test_school_abilities.py::test_isawa_duelist_damage_shows_water`
- [x] Matsu 2nd Dan +5 on iaijutsu -> `test_school_abilities.py::test_matsu_2nd_dan_iaijutsu_bonus`
- [x] Hiruma 2nd Dan +5 on parry -> `test_school_abilities.py::test_hiruma_2nd_dan_parry_bonus`
- [x] Shinjo 2nd Dan +5 on parry -> `test_school_abilities.py::test_shinjo_2nd_dan_parry_bonus`
- [x] Kitsuki 2nd Dan +5 on interrogation -> `test_school_abilities.py::test_kitsuki_2nd_dan_interrogation_bonus`
- [x] Merchant 2nd Dan +5 on interrogation -> `test_school_abilities.py::test_merchant_2nd_dan_interrogation_bonus`
- [x] Kuni 2nd Dan +5 on interrogation -> `test_school_abilities.py::test_kuni_2nd_dan_interrogation_bonus`
- [x] Yogo 2nd Dan +5 on wound check -> `test_school_abilities.py::test_yogo_2nd_dan_wound_check_bonus`
- [x] Otaku 2nd Dan +5 on wound check -> `test_school_abilities.py::test_otaku_2nd_dan_wound_check_bonus`
- [x] Isawa Duelist 2nd Dan +5 on wound check -> `test_school_abilities.py::test_isawa_duelist_2nd_dan_wound_check_bonus`
- [x] Brotherhood 3rd Dan spend raise on precepts -> `test_school_abilities.py::test_brotherhood_3rd_dan_precepts_raises`
- [x] Courtier 3rd Dan spend raise on tact -> `test_school_abilities.py::test_courtier_3rd_dan_tact_raises`
- [x] Doji 3rd Dan spend raise on culture -> `test_school_abilities.py::test_doji_3rd_dan_culture_raises`
- [x] Ikoma 3rd Dan spend raise on bragging -> `test_school_abilities.py::test_ikoma_3rd_dan_bragging_raises`
- [x] Kitsuki 3rd Dan spend raise on interrogation -> `test_school_abilities.py::test_kitsuki_3rd_dan_investigation_raises`
- [x] Kuni 3rd Dan spend raise on interrogation -> `test_school_abilities.py::test_kuni_3rd_dan_interrogation_raises`
- [x] Merchant 3rd Dan spend raise on sincerity -> `test_school_abilities.py::test_merchant_3rd_dan_sincerity_raises`
- [x] Shosuro 3rd Dan spend raise on sincerity -> `test_school_abilities.py::test_shosuro_3rd_dan_sincerity_raises`
- [x] Akodo feint roll adds temp VP -> `test_school_abilities.py::test_akodo_feint_temp_vp`
- [x] Akodo 2nd Dan wound check +5 bonus -> `test_school_abilities.py::test_akodo_2nd_dan_wound_check_bonus`
- [x] Akodo 3rd Dan wound check banks bonus for next attack -> `test_school_abilities.py::test_akodo_3rd_dan_wc_banks_bonus`
- [x] Bayushi VP spending for bonus damage dice -> `test_school_abilities.py::test_bayushi_vp_damage_on_attack`
- [x] Bayushi 1st Dan extra die on iaijutsu/double_attack/wound_check -> `test_school_abilities.py::test_bayushi_1st_dan_formula_extra_die`
- [x] Bayushi 2nd Dan +5 on double attack -> `test_school_abilities.py::test_bayushi_2nd_dan_double_attack_bonus`
- [x] Bayushi 3rd Dan feint shows damage output -> `test_school_abilities.py::test_bayushi_3rd_dan_feint_shows_damage`
- [x] Bayushi 4th Dan post-feint free raise -> `test_school_abilities.py::test_bayushi_4th_dan_post_feint_raise`
- [x] Bayushi 5th Dan reduced serious wounds on wound check failure -> `test_school_abilities.py::test_bayushi_5th_dan_reduced_serious_wounds`
- [x] Brotherhood 1st Dan +1k1 unarmed damage bonus -> `test_school_abilities.py::test_brotherhood_damage_unarmed_bonus`
- [x] Brotherhood 1st Dan extra die on attack/damage/wound_check -> `test_school_abilities.py::test_brotherhood_1st_dan_formula_extra_die`
- [x] Brotherhood 2nd Dan +5 on attack -> `test_school_abilities.py::test_brotherhood_2nd_dan_attack_bonus`
- [x] Courtier attack +Air flat bonus -> `test_school_abilities.py::test_courtier_attack_air_bonus`
- [x] Courtier damage +Air flat bonus -> `test_school_abilities.py::test_courtier_damage_air_bonus`
- [x] Courtier 1st Dan extra die on tact/manipulation/wound_check -> `test_school_abilities.py::test_courtier_1st_dan_formula_extra_die`
- [x] Courtier 2nd Dan +5 on manipulation -> `test_school_abilities.py::test_courtier_2nd_dan_manipulation_bonus`
- [x] Courtier 4th Dan temp VP after successful attack or manipulation -> `test_school_abilities.py::test_courtier_4th_dan_temp_vp`
- [x] Daidoji 1st Dan extra die on attack/counterattack/wound_check -> `test_school_abilities.py::test_daidoji_1st_dan_formula_extra_die`
- [x] Daidoji 2nd Dan +5 on counterattack -> `test_school_abilities.py::test_daidoji_2nd_dan_counterattack_bonus`
- [x] Daidoji 3rd Dan counterattack wound check raises note -> `test_school_abilities.py::test_daidoji_3rd_dan_counterattack_raises_note`
- [x] Daidoji 5th Dan wound check attacker TN reduction note -> `test_school_abilities.py::test_daidoji_5th_dan_wc_attacker_tn_note`
- [x] Doji 1st Dan extra die on counterattack/manipulation/wound_check -> `test_school_abilities.py::test_doji_1st_dan_formula_extra_die`
- [x] Doji 2nd Dan +5 on manipulation -> `test_school_abilities.py::test_doji_2nd_dan_manipulation_bonus`
- [x] Doji 5th Dan opponent bonus input appears -> `test_school_abilities.py::test_doji_5th_dan_opponent_bonus_input`
- [x] Hida 1st Dan extra die on attack/counterattack/wound_check -> `test_school_abilities.py::test_hida_1st_dan_formula_extra_die`
- [x] Hida 2nd Dan +5 on counterattack -> `test_school_abilities.py::test_hida_2nd_dan_counterattack_bonus`
- [x] Hida 3rd Dan reroll option on counterattack/attack -> `test_school_abilities.py::test_hida_3rd_dan_reroll_appears`
- [x] Hida 4th Dan button trades 2 SW for light wound reset -> `test_school_abilities.py::test_hida_4th_dan_trade_sw_button`
- [x] Hiruma 1st Dan extra die on initiative/parry/wound_check -> `test_school_abilities.py::test_hiruma_1st_dan_formula_extra_die`
- [x] Hiruma 4th Dan initiative shows action dice -2 -> `test_school_abilities.py::test_hiruma_initiative_action_dice_info`
- [x] Hiruma 3rd Dan post-parry bonus appears -> `test_school_abilities.py::test_hiruma_post_parry_bonus`
- [x] Hiruma 5th Dan parry note displayed -> `test_school_abilities.py::test_hiruma_5th_dan_parry_note`
- [x] Ide 1st Dan skill selection -> `test_school_abilities.py::test_ide_1st_dan_skill_selection`
- [x] Ide 2nd Dan skill selection -> `test_school_abilities.py::test_ide_2nd_dan_skill_selection`
- [x] Ide 4th Dan VP regen display -> `test_school_abilities.py::test_ide_vp_regen_display`
- [x] Ide 3rd Dan subtract-from-roll button and VP spending -> `test_school_abilities.py::test_ide_3rd_dan_subtract_button`
- [x] Ide feint banks -10 TN and applies on next attack -> `test_school_abilities.py::test_ide_feint_banks_tn_reduce`
- [x] Ikoma 1st Dan extra die on attack/bragging/wound_check -> `test_school_abilities.py::test_ikoma_1st_dan_formula_extra_die`
- [x] Ikoma 2nd Dan +5 on attack -> `test_school_abilities.py::test_ikoma_2nd_dan_attack_bonus`
- [x] Ikoma 4th Dan 10-dice floor on unparried damage -> `test_school_abilities.py::test_ikoma_4th_dan_10_dice_floor`
- [x] Isawa Duelist 1st Dan extra die on double_attack/lunge/wound_check -> `test_school_abilities.py::test_isawa_duelist_1st_dan_formula_extra_die`
- [x] Isawa Duelist 5th Dan banks wound check excess -> `test_school_abilities.py::test_isawa_duelist_5th_dan_banks_wc_excess`
- [x] Isawa Ishi 1st Dan skill selection -> `test_school_abilities.py::test_isawa_ishi_1st_dan_skill_selection`
- [x] Isawa Ishi 2nd Dan skill selection -> `test_school_abilities.py::test_isawa_ishi_2nd_dan_skill_selection`
- [x] Isawa Ishi VP max display -> `test_school_abilities.py::test_isawa_ishi_vp_max_display`
- [x] Isawa Ishi VP spend cap -> `test_school_abilities.py::test_isawa_ishi_vp_spend_cap`
- [x] Kakita 1st Dan extra die on double_attack/iaijutsu/initiative -> `test_school_abilities.py::test_kakita_1st_dan_formula_extra_die`
- [x] Kakita 4th Dan iaijutsu damage +5 bonus -> `test_school_abilities.py::test_kakita_4th_dan_iaijutsu_damage_bonus`
- [x] Kakita 2nd Dan +5 on iaijutsu -> `test_school_abilities.py::test_kakita_2nd_dan_iaijutsu_bonus`
- [x] Kitsuki 1st Dan extra die on investigation/interrogation/wound_check -> `test_school_abilities.py::test_kitsuki_1st_dan_formula_extra_die`
- [x] Kitsuki attack +2*Water bonus -> `test_school_abilities.py::test_kitsuki_attack_water_bonus`
- [x] Kitsuki interrogation uses Water ring -> `test_school_abilities.py::test_kitsuki_interrogation_uses_water`
- [x] Kitsuki 5th Dan ring reduction note -> `test_school_abilities.py::test_kitsuki_5th_dan_ring_reduction_note`
- [x] Kuni 1st Dan extra die on damage/interrogation/wound_check -> `test_school_abilities.py::test_kuni_1st_dan_formula_extra_die`
- [x] Kuni 5th Dan reflect damage UI -> `test_school_abilities.py::test_kuni_5th_dan_reflect_damage_ui`
- [x] Matsu 1st Dan extra die on double_attack/iaijutsu/wound_check -> `test_school_abilities.py::test_matsu_1st_dan_formula_extra_die`
- [x] Matsu 5th Dan LW reset to 15 after dealing serious wounds -> `test_school_abilities.py::test_matsu_5th_dan_lw_reset_15`
- [x] Matsu 4th Dan double attack near-miss -> `test_school_abilities.py::test_matsu_4th_dan_near_miss`
- [x] Matsu 3rd Dan VP wound check bonus option -> `test_school_abilities.py::test_matsu_3rd_dan_vp_wc_bonus`
- [x] Merchant 1st Dan extra die on interrogation/sincerity/wound_check -> `test_school_abilities.py::test_merchant_1st_dan_formula_extra_die`
- [x] Merchant post-roll VP spending -> `test_school_abilities.py::test_merchant_post_roll_vp_spending`
- [x] Mirumoto 1st Dan extra die on parry/double_attack/wound_check -> `test_school_abilities.py::test_mirumoto_1st_dan_formula_extra_die`
- [x] Mirumoto parry roll adds temp VP -> `test_school_abilities.py::test_mirumoto_parry_temp_vp`
- [x] Mirumoto 5th Dan VP spending +10 on combat rolls -> `test_school_abilities.py::test_mirumoto_5th_dan_vp_plus_10`
- [x] Mirumoto 4th Dan failed parry reduced bonus damage dice -> `test_school_abilities.py::test_mirumoto_4th_dan_reduced_damage_dice`
- [x] Mirumoto 2nd Dan +5 on parry -> `test_school_abilities.py::test_mirumoto_2nd_dan_parry_bonus`
- [x] Mirumoto round-start point display and spending -> `test_school_abilities.py::test_mirumoto_round_points_display`
- [x] Otaku 1st Dan extra die on iaijutsu/lunge/wound_check -> `test_school_abilities.py::test_otaku_1st_dan_formula_extra_die`
- [x] Otaku 5th Dan 10-dice-for-1-SW option -> `test_school_abilities.py::test_otaku_5th_dan_trade_dice_for_sw`
- [x] Otaku 4th Dan lunge extra die after failed parry -> `test_school_abilities.py::test_otaku_4th_dan_lunge_extra_die`
- [x] Priest 1st Dan skill selection -> `test_school_abilities.py::test_priest_1st_dan_skill_selection`
- [x] Priest 2nd Dan Honor bonus roll free raise -> `test_school_abilities.py::test_priest_2nd_dan_honor_bonus_raise`
- [x] Shiba 1st Dan extra die on double_attack/parry/wound_check -> `test_school_abilities.py::test_shiba_1st_dan_formula_extra_die`
- [x] Shiba 4th Dan wound check 3k1 bonus -> `test_school_abilities.py::test_shiba_4th_dan_wound_check_3k1_bonus`
- [x] Shiba 2nd Dan +5 on parry -> `test_school_abilities.py::test_shiba_2nd_dan_parry_bonus`
- [x] Shinjo 1st Dan extra die on initiative/double_attack/parry -> `test_school_abilities.py::test_shinjo_1st_dan_formula_extra_die`
- [x] Shinjo 4th Dan initiative highest die set to 1 -> `test_school_abilities.py::test_shinjo_4th_dan_initiative_highest_die_1`
- [x] Shinjo 5th Dan parry excess for wound check -> `test_school_abilities.py::test_shinjo_5th_dan_parry_excess_wc`
- [x] Shosuro 1st Dan extra die on attack/sincerity/wound_check -> `test_school_abilities.py::test_shosuro_1st_dan_formula_extra_die`
- [x] Shosuro Actor stipend display -> `test_school_abilities.py::test_shosuro_stipend_display`
- [x] Shosuro Actor acting skill bonus in roll formulas -> `test_school_abilities.py::test_shosuro_acting_skill_bonus`
- [x] Shosuro 2nd Dan +5 on sincerity -> `test_school_abilities.py::test_shosuro_2nd_dan_sincerity_bonus`
- [ ] Shugenja 1st Dan element selection (school disabled) -> `test_school_abilities.py::test_shugenja_1st_dan_element_selection` (skipped)
- [ ] Shugenja 2nd Dan element selection (school disabled) -> `test_school_abilities.py::test_shugenja_2nd_dan_element_selection` (skipped)
- [ ] Shugenja 3rd Dan applicable skills (school disabled) -> `test_school_abilities.py::test_shugenja_3rd_dan_applicable_skills` (skipped)
- [ ] Shugenja ring bonus display (school disabled) -> `test_school_abilities.py::test_shugenja_ring_bonus_display` (skipped)
- [x] Togashi 1st Dan extra die on attack/parry/athletics -> `test_school_abilities.py::test_togashi_1st_dan_formula_extra_die`
- [x] Togashi 4th Dan reroll button on contested rolls -> `test_school_abilities.py::test_togashi_4th_dan_reroll_contested`
- [x] Togashi 3rd Dan athletics raise spending button -> `test_school_abilities.py::test_togashi_3rd_dan_athletics_raises`
- [x] Togashi 2nd Dan +5 on athletics -> `test_school_abilities.py::test_togashi_2nd_dan_athletics_bonus`
- [x] Yogo 1st Dan extra die on attack/damage/wound_check -> `test_school_abilities.py::test_yogo_1st_dan_formula_extra_die`
- [x] Yogo 3rd Dan VP spending reduces light wounds -> `test_school_abilities.py::test_yogo_3rd_dan_vp_heals_lw`
- [x] Yogo Warden serious wound grants temp VP -> `test_school_abilities.py::test_yogo_temp_vp_on_sw`
- [x] Yogo 4th Dan wound check VP gives enhanced bonus -> `test_school_abilities.py::test_yogo_4th_dan_wc_vp_raise`
- [x] Account-level sharing allows edit access -> `test_permissions.py::test_granted_user_can_access_edit_page`

## JS Error Checks

- [x] No JS errors on sheet page (parametrized across 6 schools) → `test_sheet_js_errors.py::test_sheet_has_no_javascript_errors`

## Void Point Spending

- [x] Roll menu shows void options when VP available → `test_void_spending.py::test_roll_menu_shows_void_options`
- [x] Roll menu skipped when no VP available → `test_void_spending.py::test_roll_menu_skipped_without_void`
- [x] Spending void deducts from counter → `test_void_spending.py::test_spending_void_deducts_from_counter`
- [x] Temp void deducted before regular → `test_void_spending.py::test_temp_void_deducted_before_regular`

## Dice Rolling

- [x] Click a skill row opens the modal with the skill name → `test_rolls.py::test_click_skill_opens_modal_with_skill_name`
- [x] Click Attack opens attack modal → `test_rolls.py::test_click_attack_opens_attack_modal`
- [x] Click Parry opens modal with "Parry" title → `test_rolls.py::test_click_parry_opens_modal`
- [x] Click a Ring opens an Athletics roll modal → `test_rolls.py::test_click_ring_opens_athletics_modal`
- [x] Modal shows Total and dice after the animation phase → `test_rolls.py::test_modal_shows_total_and_dice_after_animation`
- [x] Modal close button hides the modal → `test_rolls.py::test_modal_close_button`
- [x] Impaired character's roll modal shows "10s not rerolled" note → `test_rolls.py::test_impaired_character_modal_shows_no_reroll_note`
- [x] Impaired indicator visible on the sheet when wounds ≥ Earth → `test_rolls.py::test_impaired_indicator_visible_on_sheet`
- [x] Impaired indicator absent when healthy → `test_rolls.py::test_impaired_indicator_absent_when_healthy`
- [x] Disabling animation in profile shows result panel immediately → `test_rolls.py::test_disable_animation_preference`
- [x] Die top angle is approximately 70 degrees → `test_rolls.py::test_die_top_angle_is_about_70_degrees`
- [x] Initiative roll shows action dice → `test_rolls.py::test_initiative_roll_shows_action_dice`
- [x] Initiative shows action dice (not Total) → `test_rolls.py::test_initiative_no_total_shown`
- [x] 3rd Dan spend raise button visible for applicable skill → `test_rolls.py::test_spend_raise_button_visible_for_applicable_skill`
- [x] 3rd Dan spend raise adds +5 to total → `test_rolls.py::test_spend_raise_adds_5_to_total`
- [x] 3rd Dan undo raise reverses spend → `test_rolls.py::test_undo_raise_reverses_spend`
- [x] 3rd Dan spend disabled at per-roll max → `test_rolls.py::test_spend_disabled_at_per_roll_max`
- [x] 3rd Dan undo disabled when none spent → `test_rolls.py::test_undo_disabled_when_none_spent`
- [x] No spend button for non-applicable skill → `test_rolls.py::test_no_spend_button_for_non_applicable_skill`
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
- [x] Reset modal lists abilities to restore → `test_tracking_advanced.py::test_reset_modal_lists_abilities_to_restore`
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

## Coverage Summary

**Covered:** ~280 test functions across 32 test files
**Uncovered:** 0

All interactive UI features are covered by at least one e2e clicktest.
