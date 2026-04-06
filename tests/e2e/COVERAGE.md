# E2E Clicktest Feature Coverage

Every interactive UI feature should have at least one clicktest. This file tracks coverage.
When adding a feature, add lines here first (marked `[ ]`). After writing the clicktest, mark `[x]` with the test reference.

---

## Navigation (base.html)

- [x] Homepage loads → `test_smoke.py::test_homepage_loads`
- [x] "New Character" button creates character and redirects to edit → `test_create_character.py::test_create_and_edit_character`
- [ ] Profile link navigates to /profile
- [ ] Logout link logs out and redirects
- [ ] Login link navigates to Discord OAuth
- [ ] Login via test-login secret URL creates session and redirects

## Homepage (index.html)

- [x] Character list displays characters → `test_create_character.py::test_create_and_edit_character`
- [ ] Draft badge shown for never-applied characters
- [ ] "Draft changes" badge shown for characters modified since last version
- [ ] No badge shown for characters matching their latest version
- [ ] Character card links to correct character sheet
- [ ] Empty state shows "Create Your First Character"

## Profile (profile.html)

- [ ] Profile page loads when logged in
- [ ] Profile redirects to login when not logged in
- [ ] Display name field shows current name
- [ ] Display name can be changed and persists after save
- [ ] Other users listed with grant checkboxes
- [ ] GM users shown with "GM" badge and disabled (always-checked) checkbox
- [ ] Granting access to a non-GM user persists after save
- [ ] Revoking access from a non-GM user persists after save
- [ ] GM access cannot be revoked (checkbox stays checked and disabled)

## Character Editor — Basics (edit.html)

- [x] Character name can be edited and auto-saves → `test_edit_character.py::test_edit_auto_saves`
- [ ] Owner dropdown visible only for GM users
- [ ] Owner dropdown hidden for non-GM users
- [ ] Owner dropdown reassigns character and updates player name
- [ ] Earned XP field updates XP calculations live
- [ ] Notes textarea saves via autosave

## Character Editor — School Selection

- [x] School dropdown loads school details via HTMX → `test_school_selection.py::test_school_selection_loads_details`
- [x] Switching schools updates details panel → `test_school_selection.py::test_switching_schools_updates_details`
- [x] School knack controls appear for selected school → `test_school_selection.py::test_school_knack_controls_appear`
- [x] School techniques displayed by Dan level → `test_school_selection.py::test_school_techniques_shown`
- [ ] School with fixed ring (e.g. Akodo Bushi/Water) auto-sets school ring
- [ ] School with "any non-Void" ring shows ring dropdown with Air/Fire/Earth/Water options
- [ ] School with "Air or Water" ring shows ring dropdown with those two options
- [ ] Selecting a ring from the dropdown updates school_ring_choice
- [ ] School ring enforces minimum of 3 (cannot be lowered below 3)
- [ ] School ring allows maximum of 6 (higher than normal ring max of 5)
- [ ] Non-school rings max at 5
- [ ] Changing school resets knacks to match new school's knacks
- [ ] Changing school from multi-ring to fixed-ring hides the ring dropdown

## Character Editor — Rings

- [x] Ring +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_ring_change`
- [ ] Non-school ring minimum is 2
- [ ] Non-school ring maximum is 5
- [ ] School ring minimum is 3
- [ ] School ring maximum is 6
- [ ] Non-school ring - button disabled at 2
- [ ] Non-school ring + button disabled at 5
- [ ] School ring - button disabled at 3
- [ ] School ring + button disabled at 6
- [x] XP overspend turns remaining XP red → `test_live_xp.py::test_remaining_goes_negative_on_overspend`

## Character Editor — Knacks

- [x] Knack +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_knack_change`
- [ ] Knack - button disabled at rank 1 (minimum, free from school)
- [ ] Knack + button disabled at rank 5 (maximum)
- [ ] Knack rank cannot go below 1
- [ ] Knack rank cannot go above 5

## Character Editor — Combat Skills

- [x] Attack +/- buttons update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry +/- buttons update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry cannot exceed attack + 1 → `test_combat_skills.py::test_parry_cannot_exceed_attack_plus_1`
- [x] Attack cannot go below parry - 1 → `test_combat_skills.py::test_attack_cannot_lower_below_parry_minus_1`
- [x] Combat skills persist through apply changes → `test_combat_skills.py::test_create_with_combat_skills_and_publish`
- [x] XP updates on combat skill change → `test_live_xp.py::test_xp_updates_on_combat_skill_change`
- [ ] Attack minimum is 1 (- button disabled)
- [ ] Attack maximum is 5 (+ button disabled)
- [ ] Parry minimum is 1 (- button disabled)
- [ ] Parry maximum is 5 (+ button disabled)

## Character Editor ��� Skills

- [x] Skill +/- buttons update XP → `test_live_xp.py::test_xp_updates_on_skill_change`
- [ ] Skill - button disabled at rank 0
- [ ] Skill + button disabled at rank 5
- [ ] Skill rank cannot go below 0
- [ ] Skill rank cannot go above 5
- [ ] Basic skill XP cost matches expected formula
- [ ] Advanced skill XP cost is higher than basic skill at same rank

## Character Editor — Honor

- [x] Honor +/- updates XP → `test_live_xp.py::test_xp_honor_change`
- [ ] Honor minimum is 1.0 (- button disabled)
- [ ] Honor maximum is 5.0 (+ button disabled)
- [ ] Honor increments/decrements by 0.5

## Character Editor ��� Rank

- [ ] Rank - button is permanently disabled
- [ ] Rank + button is permanently disabled
- [ ] Rank displays 7.5 (campaign default)
- [ ] Rank locked tooltip appears on hover

## Character Editor — Recognition

- [ ] Recognition + button raises by 0.5
- [ ] Recognition - button lowers by 0.5
- [ ] Recognition minimum is 7.5 (- button disabled at 7.5)
- [ ] Recognition maximum is rank * 1.5 = 11.25 (+ button disabled)
- [ ] "Halve starting Recognition" checkbox sets recognition to 3.5
- [ ] "Halve starting Recognition" grants +3 XP (visible in budget)
- [ ] Unchecking halve restores recognition to 7.5 (if it was below)
- [ ] With halve checked, recognition minimum is 3.5 (- button disabled)
- [ ] With halve checked, recognition can be raised above 3.5 (costs XP)

## Character Editor — Advantages (individual items)

- [x] Checking an advantage adds its XP cost → `test_live_xp.py::test_xp_updates_on_advantage_toggle`
- [x] Unchecking an advantage removes its XP cost → `test_live_xp.py::test_xp_updates_on_advantage_toggle`
- [ ] Wealthy checkbox is disabled (Wasp campaign)
- [ ] Poor advantage checkbox is disabled (Wasp campaign)

## Character Editor — Disadvantages (individual items)

- [x] Checking a disadvantage adds XP to budget → `test_live_xp.py::test_xp_updates_on_disadvantage_toggle`
- [ ] Poor disadvantage checkbox is disabled (Wasp campaign)

## Character Editor — Exclusive Pairs (each pair bidirectional)

- [ ] Checking Vain disables Unkempt
- [ ] Checking Unkempt disables Vain
- [ ] Checking Lucky disables Unlucky
- [ ] Checking Unlucky disables Lucky
- [ ] Checking Imperial Favor disables Imperial Disdain
- [ ] Checking Imperial Disdain disables Imperial Favor
- [ ] Checking Quick Healer disables Slow Healer
- [ ] Checking Slow Healer disables Quick Healer
- [ ] Checking Virtue disables Unconventional
- [ ] Checking Unconventional disables Virtue
- [ ] Checking Wealthy disables Poor (both already disabled, futureproofing)
- [ ] Checking Poor disables Wealthy (both already disabled, futureproofing)
- [ ] Checking Family Reckoning: Righteous Sting disables Family Reckoning: Venomous Sting
- [ ] Checking Family Reckoning: Venomous Sting disables Family Reckoning: Righteous Sting
- [ ] Disabled exclusive pair shows "Cannot be taken with X" in tooltip
- [ ] Unchecking one of a pair re-enables the other

## Character Editor �� Campaign Advantages & Disadvantages

- [ ] Campaign advantage checkbox toggles XP cost
- [ ] Campaign disadvantage checkbox adds XP to budget
- [ ] Campaign advantages appear in their own section
- [ ] Campaign disadvantages appear in their own section

## Character Editor — Advantage Detail Fields

- [x] Higher Purpose: text field appears when checked → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Higher Purpose: text persists after reload → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [ ] Higher Purpose: skill checkboxes appear when checked
- [ ] Higher Purpose: selected skills persist after reload
- [x] Virtue: text field appears when checked → `test_advantage_details.py::test_virtue_shows_text_field`
- [x] Virtue: text appears on character sheet after apply → `test_advantage_details.py::test_virtue_shows_text_field`
- [ ] Specialization: text field appears when checked
- [ ] Specialization: single skill dropdown appears when checked
- [ ] Specialization: selected skill persists after reload
- [ ] Dark Secret: text field appears when checked
- [ ] Dark Secret: player dropdown appears when checked
- [ ] Dark Secret: selected player persists after reload
- [ ] Jealousy: text field appears when checked
- [ ] Jealousy: text persists after reload
- [ ] Good Reputation: text field appears when checked
- [ ] Good Reputation: text persists after reload
- [ ] Bad Reputation: text field appears when checked
- [ ] Bad Reputation: text persists after reload
- [ ] Unconventional: text field appears when checked
- [ ] Unconventional: text persists after reload
- [ ] Detail fields hidden when advantage is unchecked

## Character Editor — Auto-save

- [x] Changes auto-save and persist across page reload → `test_edit_character.py::test_edit_auto_saves`
- [ ] Save status indicator shows "Saving..." then "Saved"
- [ ] Multiple rapid changes debounce into single save

## Character Editor — Apply Changes Modal

- [x] Apply Changes button opens modal → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] Modal requires description text → (implicit in apply_changes helper)
- [ ] Modal pre-populates "Initial character creation" for first version
- [ ] Modal description is blank for subsequent versions
- [ ] "Spending XP from the latest adventure" quick-fill button works
- [ ] "Spending some leftover XP mid-adventure" quick-fill button works
- [ ] Apply button disabled when description is empty
- [ ] Cancel button closes modal without applying
- [x] Successful apply redirects to view sheet → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] No draft banner shown after successful apply → `test_publish_revert.py::test_apply_then_no_draft_banner`

## Character Sheet — Header & Permissions

- [ ] Edit button visible when viewer has edit permission
- [ ] Delete button visible when viewer has edit permission
- [ ] Edit button hidden when viewer lacks edit permission
- [ ] Delete button hidden when viewer lacks edit permission
- [ ] Delete button shows confirmation dialog before deleting
- [ ] Delete removes character and redirects to homepage
- [x] Draft name visible to all viewers → `test_edit_character.py::test_view_sheet_shows_published_name`

## Character Sheet — Draft Banners

- [ ] "Draft" banner shown for never-applied characters
- [ ] "Draft changes" banner shown for characters with changes since last version
- [ ] No banner shown for characters matching their latest version

## Character Sheet — Status Display

- [ ] Honor value displayed correctly
- [ ] Rank value displayed with "locked" label
- [ ] Recognition value displayed correctly
- [ ] Stipend value displayed correctly
- [ ] Stipend tooltip shows calculation breakdown
- [ ] Stipend changes with Household Wealth advantage
- [ ] Stipend changes with Merchant/Shosuro Actor school
- [ ] Rank tooltip shows Good Reputation modifier (+2.0)
- [ ] Rank tooltip shows Imperial Favor modifier (+3.0/+1.0)
- [ ] Rank tooltip shows Bad Reputation modifier (-1.5)
- [ ] Recognition tooltip shows Good Reputation modifier (+1.0)
- [ ] Recognition tooltip shows Imperial Favor modifier (+3.0/+1.0)

## Character Sheet — Tracking

- [x] Light wounds initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Serious wounds initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Void points initial value shows 0 → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Light wounds + increments count → `test_tracking.py::test_wound_tracking_persists`
- [x] Light wounds - decrements count → (implicit in test_wound_tracking_persists)
- [ ] Serious wounds + increments count
- [ ] Serious wounds - decrements count
- [x] Light wounds persist across page reload → `test_tracking.py::test_wound_tracking_persists`
- [ ] Serious wounds persist across page reload
- [x] Void points + increments count → `test_tracking.py::test_void_points_tracking`
- [x] Void points - decrements count → `test_tracking.py::test_void_points_tracking`
- [ ] Void points persist across page reload
- [ ] Void points + button disabled at max (lowest ring value)
- [ ] Void points - button disabled at 0
- [ ] Light wounds - button disabled at 0
- [ ] Serious wounds - button disabled at 0
- [x] Per-adventure section renders with JSON data (Lucky advantage) → `test_tracking.py::test_tracking_renders_with_per_adventure_abilities`
- [x] Lucky toggle shown for characters with Lucky → `test_tracking.py::test_tracking_renders_with_per_adventure_abilities`
- [ ] Unlucky toggle shown for characters with Unlucky
- [ ] Lucky toggle: checking marks as "Used", persists
- [ ] Unlucky toggle: checking marks as "Used", persists
- [ ] Per-adventure counter: - button spends one use
- [ ] Per-adventure counter: + button restores one use
- [ ] Per-adventure counter: shows "remaining / max"
- [ ] Per-adventure counter: - disabled at 0 remaining
- [ ] Per-adventure counter: + disabled at max
- [ ] Per-adventure counter persists across reload
- [ ] "Reset Per-Adventure Abilities" button shows confirmation
- [ ] "Reset Per-Adventure Abilities" resets all counters to max
- [ ] "Reset Per-Adventure Abilities" resets all toggles to unchecked
- [ ] Conviction knack counter shown for characters with Conviction knack
- [ ] Worldliness knack counter shown for characters with Worldliness knack
- [ ] Otherworldliness knack counter shown for characters with Otherworldliness knack
- [ ] 3rd Dan free raises counter shown for eligible schools at Dan 3+

## Character Sheet — Skills Display

- [ ] Skills with rank > 0 show roll calculation (e.g., "4k2 + 5")
- [ ] Skills with rank 0 do not show roll calculation
- [ ] Charming bonus (+5) shown on Etiquette roll
- [ ] Charming bonus (+5) shown on Culture roll
- [ ] Fierce bonus (+5) shown on Bragging roll
- [ ] Fierce bonus (+5) shown on Intimidation roll
- [ ] Discerning bonus (+5) shown on Interrogation roll
- [ ] Discerning bonus (+10) shown on Investigation roll
- [ ] Genealogist bonus (+10) shown on Heraldry roll
- [ ] Tactician bonus (+5) shown on Strategy roll
- [ ] Tactician bonus (+5) shown on History roll
- [ ] Worldly bonus (+5) shown on Commerce roll
- [ ] Worldly bonus (+5) shown on Underworld roll
- [ ] History synergy bonus shown on Culture/Law/Strategy rolls
- [ ] Acting synergy bonus shown on Sincerity/Intimidation/Sneaking rolls
- [ ] Honor bonus shown on Bragging roll
- [ ] Honor bonus shown on Precepts roll
- [ ] Honor bonus shown on Sincerity roll
- [ ] Recognition bonus shown on Bragging roll
- [ ] Transparent note shown on Sincerity roll
- [ ] Unkempt note shown on Culture roll
- [ ] Thoughtless note shown on Tact roll
- [ ] Thoughtless note shown on Sincerity roll
- [ ] Higher Purpose conditional bonus shown on selected skills
- [ ] Specialization conditional bonus shown on selected skill

## Character Sheet — Advantages & Disadvantages Display

- [ ] Each selected advantage listed with name
- [ ] Advantage tooltip shows full description on hover
- [ ] Advantage detail text shown inline (e.g., "Virtue — Courage")
- [ ] Each selected disadvantage listed with name
- [ ] Disadvantage tooltip shows full description on hover
- [ ] Disadvantage detail text shown inline
- [ ] Dark Secret shows "known by [player name]"
- [ ] Campaign advantages shown in their own section
- [ ] Campaign disadvantages shown in their own section

## Character Sheet �� XP Summary

- [ ] Rings XP shown correctly
- [ ] Skills XP shown correctly
- [ ] Knacks XP shown correctly
- [ ] Combat Skills XP shown correctly
- [ ] Honor XP shown correctly
- [ ] Rank XP shown as 0 (locked)
- [ ] Recognition XP shown correctly
- [ ] Advantages XP shown correctly
- [ ] Disadvantages XP shown as negative (green)
- [ ] Total Spent matches sum of all categories
- [ ] Budget shows starting + earned + disadvantage bonus
- [ ] Unspent XP shown in green when >= 0
- [ ] Unspent XP shown in red when < 0

## Character Sheet — Version History

- [x] Version history section collapsed by default → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Clicking header expands version list → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [ ] Version count shown in header
- [ ] Each version shows version number
- [ ] Each version shows timestamp
- [ ] Each version shows author name
- [ ] Each version shows summary text
- [ ] Clicking summary text opens inline edit
- [ ] Inline edit: typing and pressing Enter saves new summary
- [ ] Inline edit: pressing Escape cancels without saving
- [ ] Inline edit: Save button saves new summary
- [ ] Inline edit: Cancel button cancels without saving
- [ ] Revert button shown on all versions except the latest
- [ ] Revert button NOT shown on latest version
- [x] Revert button opens modal with reason input → `test_publish_revert.py::test_revert_with_reason`
- [ ] Revert modal pre-fills "Reverting to version X because"
- [ ] Revert modal requires reason text (button disabled when empty)
- [x] Revert with reason reloads page with reverted data → `test_publish_revert.py::test_revert_with_reason`

## Character Sheet — View as Non-Editor

- [ ] Edit button hidden for non-editor viewers
- [ ] Delete button hidden for non-editor viewers
- [ ] Version history section hidden for non-editor viewers
- [ ] Tracking section still functional for non-editor viewers
- [ ] Character data still visible to non-editor viewers

---

## Coverage Summary

**Covered:** ~35 features across 25 test functions
**Uncovered:** ~155 features identified above marked `[ ]`

**Priority gaps (features that have caused production bugs):**
- Tracking +/- button display (caused blank numbers bug)
- Per-adventure JSON rendering (caused Alpine.js initialization failure)
- Draft status banners (false positive "unpublished changes")

**High-value uncovered areas:**
- Profile page (0 tests)
- Permission-based visibility — edit/delete buttons, version history (0 tests)
- All exclusive pairs (0 tests, 14 directional pairs + tooltip + re-enable)
- Recognition halving behavior (0 tests)
- School ring interactions — fixed vs multi-ring, min/max, dropdown (0 tests)
- Skill roll display with all bonus types (0 tests, ~25 individual bonuses)
- Per-adventure counter/toggle persistence and reset (0 tests)
- XP summary correctness on character sheet (0 tests)
- Version history inline editing (0 tests)
