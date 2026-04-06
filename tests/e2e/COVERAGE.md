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
- [ ] Login via test-login secret URL

## Homepage (index.html)

- [x] Character list displays published characters → `test_create_character.py::test_create_and_edit_character`
- [ ] Draft badge shown for unpublished characters
- [ ] "Draft changes" badge shown for modified characters
- [ ] Character card links to character sheet
- [ ] Empty state shows "Create Your First Character"

## Profile (profile.html)

- [ ] Display name field loads current name
- [ ] Display name can be changed and saved
- [ ] Other users listed with grant checkboxes
- [ ] GM users shown with badge and disabled checkbox
- [ ] Granting access persists after save
- [ ] Revoking access persists after save
- [ ] Profile requires login (redirects)

## Character Editor — Basics (edit.html)

- [x] Character name can be edited and auto-saves → `test_edit_character.py::test_edit_auto_saves`
- [ ] Owner dropdown (GM only) reassigns character
- [ ] Earned XP field updates XP calculations
- [ ] Notes textarea saves

## Character Editor — School Selection

- [x] School dropdown loads school details via HTMX → `test_school_selection.py::test_school_selection_loads_details`
- [x] Switching schools updates details → `test_school_selection.py::test_switching_schools_updates_details`
- [x] School knack controls appear for selected school → `test_school_selection.py::test_school_knack_controls_appear`
- [x] School techniques displayed by Dan level → `test_school_selection.py::test_school_techniques_shown`
- [ ] School ring auto-set when school has a fixed ring
- [ ] School ring dropdown appears for schools with multiple ring options
- [ ] School ring minimum enforced (min 3)
- [ ] Changing school resets knacks
- [ ] School ring raised to 4th Dan affects ring max (6 instead of 5)

## Character Editor — Rings

- [x] Ring +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_ring_change`
- [ ] Ring minimum enforced (2 for non-school, 3 for school ring)
- [ ] Ring maximum enforced (5 for non-school, 6 for school ring)
- [ ] Ring +/- buttons disabled at min/max
- [x] XP overspend shows red → `test_live_xp.py::test_remaining_goes_negative_on_overspend`

## Character Editor — Knacks

- [x] Knack +/- buttons change value and update XP → `test_live_xp.py::test_xp_updates_on_knack_change`
- [ ] Knack minimum is 1 (free from school)
- [ ] Knack maximum is 5
- [ ] Knack +/- disabled at min/max

## Character Editor — Combat Skills

- [x] Attack/parry +/- buttons update XP → `test_combat_skills.py::test_combat_skill_xp_live_calculation`
- [x] Parry cannot exceed attack + 1 → `test_combat_skills.py::test_parry_cannot_exceed_attack_plus_1`
- [x] Attack cannot go below parry - 1 → `test_combat_skills.py::test_attack_cannot_lower_below_parry_minus_1`
- [x] Combat skills persist through apply changes → `test_combat_skills.py::test_create_with_combat_skills_and_publish`
- [x] XP updates on combat skill change → `test_live_xp.py::test_xp_updates_on_combat_skill_change`

## Character Editor — Skills

- [x] Skill +/- buttons update XP → `test_live_xp.py::test_xp_updates_on_skill_change`
- [ ] Skill minimum is 0
- [ ] Skill maximum is 5
- [ ] Skill +/- disabled at min/max
- [ ] Advanced skills cost more than basic skills

## Character Editor — Honor / Rank / Recognition

- [x] Honor +/- updates XP → `test_live_xp.py::test_xp_honor_change`
- [ ] Honor minimum 1.0, maximum 5.0
- [ ] Honor +/- disabled at min/max
- [ ] Rank is locked (buttons disabled, cannot be changed)
- [ ] Recognition +/- within bounds (min 7.5, max rank*1.5)
- [ ] "Halve starting Recognition" checkbox sets recognition to 3.5 and grants +3 XP
- [ ] Unchecking halve restores recognition to at least 7.5

## Character Editor — Advantages & Disadvantages

- [x] Advantage checkbox toggles XP cost → `test_live_xp.py::test_xp_updates_on_advantage_toggle`
- [x] Disadvantage checkbox adds XP to budget → `test_live_xp.py::test_xp_updates_on_disadvantage_toggle`
- [ ] Wealthy checkbox is disabled (Wasp campaign)
- [ ] Poor checkbox is disabled (Wasp campaign)
- [ ] Exclusive pairs disable each other (e.g., Vain disables Unkempt)
- [ ] Exclusive pair tooltip shows reason when disabled
- [ ] Campaign advantage checkboxes toggle XP
- [ ] Campaign disadvantage checkboxes toggle XP

## Character Editor — Advantage Detail Fields

- [x] Higher Purpose shows text field and skill checkboxes → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Higher Purpose text persists after reload → `test_advantage_details.py::test_higher_purpose_shows_detail_fields`
- [x] Virtue shows text field → `test_advantage_details.py::test_virtue_shows_text_field`
- [x] Virtue text appears on character sheet → `test_advantage_details.py::test_virtue_shows_text_field`
- [ ] Specialization shows text field and single skill dropdown
- [ ] Dark Secret shows text field and player dropdown
- [ ] Jealousy shows text field
- [ ] Good Reputation shows text field
- [ ] Bad Reputation shows text field
- [ ] Unconventional shows text field
- [ ] Detail fields hidden when advantage unchecked

## Character Editor — Auto-save

- [x] Changes auto-save and persist across reload → `test_edit_character.py::test_edit_auto_saves`
- [ ] Save status shows "Saving..." then "Saved"
- [ ] Multiple rapid changes debounce into single save

## Character Editor — Apply Changes (formerly Publish)

- [x] Apply Changes button opens modal → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] Modal requires description text → (implicit in apply_changes helper)
- [ ] Modal pre-populates "Initial character creation" for first version
- [ ] Quick-fill buttons populate description
- [ ] Apply disabled when description empty
- [x] Apply redirects to view sheet → `test_publish_revert.py::test_apply_redirects_to_view_sheet`
- [x] No draft banner after apply → `test_publish_revert.py::test_apply_then_no_draft_banner`

## Character Sheet — Header

- [ ] Edit button visible when viewer has edit permission
- [ ] Delete button visible when viewer has edit permission
- [ ] Edit button hidden when viewer lacks permission
- [ ] Delete button hidden when viewer lacks permission
- [ ] Delete button shows confirmation dialog

## Character Sheet — Draft Banners

- [ ] "Draft" banner shown for never-applied characters
- [ ] "Draft changes" banner shown for characters with changes since last version
- [ ] No banner shown for characters matching their latest version

## Character Sheet — Status Display

- [ ] Honor value displayed
- [ ] Rank value displayed with "locked" label
- [ ] Recognition value displayed
- [ ] Stipend displayed with tooltip showing calculation
- [ ] Rank tooltip shows modifiers (when applicable)
- [ ] Recognition tooltip shows modifiers (when applicable)

## Character Sheet — Tracking

- [x] Light wounds +/- shows count → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Serious wounds +/- shows count → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Void points +/- shows count → `test_tracking.py::test_tracking_shows_initial_values`
- [x] Wound tracking persists across reload → `test_tracking.py::test_wound_tracking_persists`
- [x] Void points increment and decrement → `test_tracking.py::test_void_points_tracking`
- [ ] Void points capped at max (lowest ring)
- [ ] Void points cannot go below 0
- [x] Per-adventure abilities render with JSON data → `test_tracking.py::test_tracking_renders_with_per_adventure_abilities`
- [ ] Per-adventure counter +/- works and persists
- [ ] Per-adventure toggle works and persists
- [ ] "Reset Per-Adventure Abilities" resets all counters and toggles
- [ ] Lucky toggle shown for characters with Lucky advantage
- [ ] Unlucky toggle shown for characters with Unlucky disadvantage

## Character Sheet — Skills Display

- [ ] Skills listed with ranks and roll calculations
- [ ] Roll calculations include advantage bonuses
- [ ] Roll calculations include school technique bonuses
- [ ] Roll calculations include skill synergy bonuses
- [ ] Transparent note on Sincerity roll
- [ ] Unkempt note on Culture roll
- [ ] Thoughtless note on Tact/Sincerity roll
- [ ] Higher Purpose conditional bonus shown on selected skills
- [ ] Specialization conditional bonus shown on selected skill

## Character Sheet — Advantages & Disadvantages Display

- [ ] Advantages listed with full descriptions on hover
- [ ] Disadvantages listed with full descriptions on hover
- [ ] Advantage detail text shown (e.g., "Virtue — Courage")
- [ ] Dark Secret shows "known by [player]"

## Character Sheet — XP Summary

- [ ] XP breakdown shows all categories
- [ ] Total spent matches sum of categories
- [ ] Budget includes earned XP and disadvantage bonuses
- [ ] Overspend shown in red

## Character Sheet — Version History

- [x] Version history collapsed by default → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [x] Click header expands history → `test_publish_revert.py::test_version_history_collapsed_by_default`
- [ ] Version entries show number, date, author, summary
- [ ] Summary editable inline (click to edit, enter to save)
- [x] Revert button opens modal with reason field → `test_publish_revert.py::test_revert_with_reason`
- [x] Revert with reason reloads page with old data → `test_publish_revert.py::test_revert_with_reason`
- [ ] Revert button not shown on latest version

## Character Sheet — View as Non-Editor

- [ ] Edit/Delete buttons hidden for non-editors
- [ ] Version history hidden for non-editors
- [ ] Tracking section still functional for non-editors

---

## Coverage Summary

**Covered:** ~35 features across 25 test functions
**Uncovered:** ~75 features identified above marked `[ ]`
**Priority gaps:**
- Profile page (0 tests)
- Permission-based visibility (0 tests)
- Draft status banners (0 tests)
- Advantage exclusive pairs UI (0 tests)
- Recognition halving behavior (0 tests)
- School ring interactions (0 tests)
- Skill roll display with bonuses (0 tests)
- Per-adventure counter/toggle persistence (0 tests)
