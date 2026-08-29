# Professions: Wave Man implementation plan

Status: **planning complete, no code written.**
Created 2026-08-29. Source rules: `rules/09-professions.md` in the GM's `l7r` repo
(bind-mounted at `/host-l7r-repo` in this container).

This is the implementation-tracking checklist, in the spirit of
`import-design/design.md`. Rules intent and rationale that outlive the build
should end up in `school-features/WaveMan.md` (Phase 8), not here.

---

## 1. Decisions already made

These were settled with the GM before planning and are **not** open questions.
The upstream rules file says nothing about any of them, so they are campaign
rulings recorded here as the authority for the code.

| # | Question | Ruling |
|---|---|---|
| D1 | How are Wave Man abilities acquired? | **A profession replaces the school.** "Wave Man" is picked in place of a school. |
| D2 | XP cost per ability? | **Zero.** Abilities are free and unlocked by total XP: **1 ability at 150 XP, plus 1 more per 15 XP beyond that.** Cap is 10 (the whole list). |
| D3 | School Ring / knacks / Dan for a Wave Man? | **None of them.** All five rings start at 2 and cap at 5. No school knacks, no Dan. |
| D4 | Build scope | **Generic profession framework now, Wave Man mechanics only.** All five profession lists (Wave Man, Worker, Merchant, Priest, Ninja) go into `game_data.py` as data; only Wave Man gets dice logic. |
| D5 | The four opponent-facing abilities | **Reference text only.** Rendered on the sheet so the player can tell the GM; no attempt to model an opponent's rolls. |
| D6 | W3's "subtract 2 from your armor damage reduction penalty" | **Deferred.** There are no armor rules anywhere in `rules/` - the only match for "armor" in the whole rules directory is inside this ability. Implement the weapon half; leave the armor half unchecked and blocked on upstream rules. |

Derived from D2: allowance is `0` below 150 XP, otherwise
`min(10, 1 + (total_xp - 150) // 15)`. Unlock thresholds land at
150 / 165 / 180 / 195 / 210 / 225 / 240 / 255 / 270 / 285 XP.

---

## 2. The ten abilities

Numbered W1-W10 in rules order. This numbering is used throughout the plan and
should be used in code comments and test names.

| id | rules text (verbatim) | shape |
|---|---|---|
| **W1** | When you make an attack roll that would miss, raise it by 5. Any parry attempt against an attack that receives a free raise in this manner automatically succeeds. | own attack roll (clause 1) + reference text (clause 2) |
| **W2** | Raise the TN of someone trying to parry one of your attacks by 5. | reference text |
| **W3** | When using a weapon that deals less than 4k2 damage, add an extra rolled damage die to the weapon's base damage, to a maximum of 4k2 base damage. Also, subtract 2 from your armor damage reduction penalty. | own damage (clause 1); clause 2 deferred per D6 |
| **W4** | Round your damage rolls up to the nearest multiple of 5. If the roll is already a multiple of 5, then raise it by 3. | own damage total |
| **W5** | You may reroll 10s on a single die when impaired. | own rolls, interactive |
| **W6** | Roll one extra unkept die on initiative. | formula layer |
| **W7** | Roll two extra unkept dice on wound checks. | formula layer |
| **W8** | When someone is keeping at least one extra die of damage from exceeding their attack roll TN, subtract 5 from the damage. | incoming damage, wound-check modal |
| **W9** | When someone unsuccessfully tries to parry an attack, you may roll 2 of the extra damage dice that you would have rolled had they not attempted to parry. | own damage, reuses existing modal inputs |
| **W10** | Raise the TN of someone making a wound check from damage you dealt to them by 5. If they fail they take serious wounds as if the TN had not been raised. | reference text |

Good news from the survey: the attack modal already carries `atkTN`,
`atkFailedParry` and `atkParrySkill` (`modal_attack.html`), which are exactly the
inputs W1 and W9 need. `atkWeaponRolled` / `atkWeaponKept` are already modal
inputs too, so W3 has somewhere to land.

Bad news: there is **no existing "round up to the nearest 5" helper anywhere** -
the Priest rituals that use the same mechanic are unimplemented reference text.
W4 is new math and belongs in `roll_math.js` per the CLAUDE.md rule about roll
arithmetic.

---

## 3. Phase 1 - Data model and game data

- [ ] `Profession` dataclass in `app/game_data.py`: `id`, `name`, `abilities: List[ProfessionAbility]`, `rules_anchor` (the `09-professions.md#...` fragment), `selectable: bool`.
- [ ] `ProfessionAbility` dataclass: `id` (e.g. `wave_man_miss_raise`), `ordinal` (1-10), `name` (short UI label), `text` (verbatim rules text), `implemented: bool`, `reference_only: bool`, `money_bonus: Optional[str]` (Worker/Merchant lists carry these).
- [ ] `PROFESSIONS: Dict[str, Profession]` populated with all five lists, text copied verbatim from `rules/09-professions.md`.
- [ ] Only `wave_man` gets `selectable=True` for v1; the other four are present as data with `selectable=False` so the editor can list them greyed out. (See Q14 - flip this if the GM wants them pickable as pure reference text.)
- [ ] `PROFESSION_ABILITY_BONUSES: Dict[str, dict]` - the profession analogue of `SCHOOL_TECHNIQUE_BONUSES`. Keyed by ability id; carries the declarative hooks (`extra_rolled_die: ["initiative"]` for W6, `["wound_check", "wound_check"]` or a count for W7, etc.).
- [ ] Import-time guard (per the coverage policy's "import-time guards" pragma category): assert every ability id is unique across all professions and that every key in `PROFESSION_ABILITY_BONUSES` names a real ability. `# pragma: no cover` with a one-line why.
- [ ] `PROFESSION_ABILITY_UNLOCK_BASE = 150` and `PROFESSION_ABILITY_UNLOCK_STEP = 15` as named constants, so D2 is a one-line change.
- [ ] Unit tests: `tests/test_professions.py` - all five professions load, ability counts match the rules file (10 each), ids unique, bonuses reference real abilities.

### Character model

- [ ] `Character.profession: Mapped[str] = mapped_column(String, default="")`.
- [ ] `Character.profession_abilities: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)`.
- [ ] **Migration entry in `_migrate_add_columns()` in `app/database.py` for both columns.** Non-optional: prod SQLite persists across deploys and `create_all` will not add them. (CLAUDE.md, "New model columns require a migration entry".)
- [ ] Both fields flow through `Character.to_dict()` / whatever builds `character_data`.
- [ ] Both fields included in `_snapshot_state()` so they are version-significant, and restored by `_restore_character_from_state()` (Discard / Revert / version diff).
- [ ] Version-diff rendering (`partials/version_diff.html`) shows profession and ability changes in readable form, not raw ids.
- [ ] Unit tests: round-trip a profession character through publish -> snapshot -> revert; assert a changed ability list flips `has_unpublished_changes`.

### Mutual exclusion with schools

- [ ] Setting `profession` clears `school`, `school_ring_choice`, `knacks`, `foreign_knacks`(?) and `technique_choices`; setting `school` clears `profession` and `profession_abilities`. Enforced server-side in the autosave/save path, not only in Alpine.
- [ ] Unit tests for both directions, including a crafted POST that sends both.

---

## 4. Phase 2 - Allowance and XP engine

- [ ] `profession_ability_allowance(total_xp: int, profession_id: str) -> int` in `app/services/xp.py`, implementing D2 and clamping to the profession's ability count.
- [ ] Wire it to total XP = `starting_xp + earned_xp` (see Q1 - flag if the GM meant spent XP).
- [ ] Unit tests for the boundaries: 149 -> 0, 150 -> 1, 164 -> 1, 165 -> 2, 285 -> 10, 400 -> 10 (capped), and a below-zero/`None` guard.
- [ ] Abilities contribute **0** to XP spend. Confirm with a test that adding abilities does not move `spent` / `remaining`.
- [ ] XP breakdown gains an informational row: "Wave Man abilities: 3 of 3 unlocked - 0 XP". Appears in `calculate_xp_breakdown()` (published sheet) and `editor_xp_view()` (live editor).
- [ ] `editor_xp_view()` payload carries `profession_allowance` so the editor's counter updates on the same ~250ms debounce as everything else, rather than being recomputed in Alpine (per the "XP lives only in services/xp.py" architectural decision).

### Validation (`validate_character`)

- [ ] Error: more abilities selected than the allowance.
- [ ] Error: an ability id that is not in the selected profession's list.
- [ ] Error: `school` and `profession` both set.
- [ ] Error: `profession` set to an id not in `PROFESSIONS`, or to a `selectable=False` profession.
- [ ] Error: `profession` set but `knacks` non-empty, or `school_ring_choice` non-empty (D3).
- [ ] Warning (soft, never blocks publish, like the Dark Secret warnings): "You have N unclaimed Wave Man abilities."
- [ ] Confirm the ring min/max block already does the right thing when `school_ring == ""` - every ring should get min 2 / max 5. Add an explicit regression test rather than trusting it.
- [ ] Confirm `compute_dan({})` returns 0 and nothing downstream (formula builders, sheet, XP) divides by or indexes on Dan in a way that breaks at 0. Test a Wave Man through `build_all_roll_formulas` end to end.
- [ ] One unit test per error/warning above (coverage policy: no pragmas for validation paths).

---

## 5. Phase 3 - Editor UI

- [ ] The school `<select>` in `edit.html` gains a "Professions" optgroup below the school groups, listing Wave Man (and the other four, `disabled`, labelled "not yet implemented").
- [ ] Alpine `school` state generalized to handle a profession value, or a parallel `profession` model - decide once and keep it consistent. The x-show conditions at `edit.html` around lines 621-900 (school-ring picker, knacks section, Mantis/Kitsune/Isawa/Priest technique pickers, flexible 2nd Dan picker) must all stay hidden for a profession.
- [ ] Switching away from a school to a profession shows a confirm dialog: knacks and technique choices will be cleared.
- [ ] New "Wave Man Abilities" section: the 10 abilities as checkboxes with full rules text, ordered W1-W10.
- [ ] Counter line: "3 of 3 chosen. Unlocked at 150 XP, plus one every 15 XP. Next at 195 XP."
- [ ] Checkboxes disable once the allowance is spent; already-checked ones stay uncheckable-in-reverse (i.e. always uncheckable, so a player can swap).
- [ ] Abilities that are reference-text-only (W2, W10) and partially implemented (W1, W3) carry a small badge explaining what the sheet does and does not compute, so the player is not surprised.
- [ ] `profession` and `profession_abilities` added to the autosave POST payload and to the Alpine initial state (`tojson`, single-quote delimiters per the house style rule).
- [ ] Hidden input / state sync so a full form POST (non-AJAX path) carries them too.
- [ ] `scripts/build-css.sh` rerun after the template edits (any new utility classes).
- [ ] Unit tests on the edit route: the profession section renders, the abilities list is present, the allowance line reflects XP.

---

## 6. Phase 4 - View sheet and other render surfaces

- [ ] `partials/sheet/school.html` renders a **profession panel** when `character.profession` is set: name in the header, no Dan chip, no School Ring line, and the ability list with chosen ones emphasised and unchosen ones at 40% opacity (mirroring how techniques above/below Dan already render).
- [ ] Link to `https://github.com/EliAndrewC/l7r/blob/master/rules/09-professions.md#wave-man-abilities`, following the existing Priest-rituals link pattern in `app/main.py`.
- [ ] Reference-text callout box for W2, W10, and W1's second clause: "Tell your GM - the sheet cannot apply this for you."
- [ ] The "No school selected yet" empty state must not fire for a profession character.
- [ ] Group summary page: show "Wave Man" wherever a school name is shown.
- [ ] `app/services/sheets.py` Google Sheets export: profession name and chosen abilities on the Character Sheet tab; XP Breakdown tab gains the informational row.
- [ ] `app/routes/gm_api.py` `GET /api/characters`: include `profession` and `profession_abilities` (the GM's REPL scores contested rolls off this data).
- [ ] Unit tests for each render surface; a JSON-shape test for the API addition.

---

## 7. Phase 5 - Dice and roll math, one ability at a time

House rule from CLAUDE.md: **the arithmetic goes in `app/static/js/roll_math.js`
with a `tests/js/` test; the Alpine layer only owns the interaction.** Anything
that is a pure formula change goes in `app/services/dice.py` and is automatically
picked up by the sheet, the Discord bot and `roll_engine.py`.

### W6 - one extra unkept die on initiative (easiest; do this first)

- [ ] `build_initiative_formula()` adds 1 rolled die (not kept) when the ability is held. Note initiative's own shape: `(Void+1)` dice, keep all but the highest, no 10s reroll.
- [ ] Bonus source string so the sheet shows "+1 rolled die from Wave Man".
- [ ] Unit test in `tests/test_dice.py`.
- [ ] Verify it flows through `roll_engine.py` unchanged (formula-layer change, so it should).

### W7 - two extra unkept dice on wound checks

- [ ] `build_wound_check_formula()` adds 2 rolled dice.
- [ ] Interaction check with `apply_dice_caps()` (the 10k10 cap) - a high-Water Wave Man can push past it.
- [ ] Unit test, including the cap boundary.

### W3 - weapon damage floor (clause 1 only; clause 2 deferred per D6)

- [ ] `waveManWeaponFloor(rolled, kept)` in `roll_math.js`: if the weapon is below 4k2, add 1 rolled die, capped at 4 rolled.
- [ ] `tests/js/` test covering 0k2 unarmed -> 1k2, 2k2 knife -> 3k2, 3k2 spear -> 4k2, 4k2 katana -> unchanged (no gain), and whatever Q5 resolves for odd shapes like 3k3.
- [ ] Applied to `atkWeaponRolled` in `modal_attack.html` and `duelWeaponRolled` in `modal_duel.html`, as a displayed adjustment rather than a silent mutation of the input, so the player can see where the die came from.
- [ ] The damage formula preview on the sheet reflects it.
- [ ] **Not** applied in `modal_kakita5.html` - a Wave Man cannot be a Kakita Duelist.
- [ ] Armor half: leave unchecked, blocked on upstream rules (D6).

### W4 - round damage up to the nearest 5, +3 if already a multiple

- [ ] `waveManRoundDamage(total)` in `roll_math.js`. Note the sharp edge: 15 -> 18, not 20; 16 -> 20.
- [ ] `tests/js/` test: 0, 1, 3, 4, 5, 14, 15, 16, 20, and a large value.
- [ ] Applied to the final damage total in the attack modal result and the duel modal result, after the extra-dice-for-excess additions (see Q6).
- [ ] Result panel shows the raw roll and the rounded value, not just the rounded one.
- [ ] Interaction with W9 (which adds dice) and W3 (which adds a die): rounding must be last.

### W5 - reroll 10s on a single die while impaired

- [ ] Decide the interaction shape: after an impaired roll, if any kept die shows 10, offer "Wave Man: reroll one 10" with the player picking which die. Closest existing precedent is the Hida 3rd Dan dice-selection UI in the attack flow.
- [ ] `L7RRollMath.impairedSuppressesReroll()` (and its server twin, the `impaired` no-reroll reason in `_reroll_fields` / `build_all_roll_formulas`) must learn that a Wave Man's suppression is **partial**, not cleared. Careful: the Hida 3rd Dan work landed a trap here - the "am I impaired?" check must read character state, not `!formula.reroll_tens`.
- [ ] The chosen die chains normally (a rerolled 10 that rolls another 10 keeps going) - see Q7.
- [ ] `tests/js/` tests for the predicate, `tests/test_dice.py` for the formula annotation.
- [ ] Interaction with the PCP rule (`rules/10-player_character_points.md` already lets an impaired character spend a PCP to reroll all 10s) - see Q8.
- [ ] Which roll types? The PCP rule excludes initiative and the iaijutsu strike; W5 presumably inherits those exclusions. Also cross-check the recent ruling in `impaired-reroll-scope` (wound checks and damage already keep their 10s while Impaired, so W5 adds nothing there).

### W1 - raise a missing attack roll by 5

- [ ] `waveManMissRaise(total, tn)` in `roll_math.js`, returning the adjusted total and whether the raise fired.
- [ ] Uses the existing `atkTN` modal input. Applies once, not repeatedly (Q3).
- [ ] Result panel shows "missed by 3, raised by 5 from Wave Man - hits" and, when the raise fires, the W1-clause-2 warning that the defender's parry auto-succeeds.
- [ ] Must run before the excess-dice damage calculation, and the raised total must **not** generate extra damage dice for exceeding the TN (it only reaches the TN). Assert this in a test.
- [ ] `tests/js/` test plus a modal clicktest.

### W9 - roll 2 of the damage dice the failed parry took away

- [ ] Reuses `atkFailedParry` and `atkParrySkill`, already in `modal_attack.html`.
- [ ] Base rule (`rules/03-combat.md`): extra damage dice from exceeding the TN are reduced by the defender's parry skill when they attempted and failed to parry. W9 gives back up to 2 of those - so `min(2, parrySkill)` (Q10).
- [ ] `roll_math.js` helper plus test.
- [ ] Optional ("you may"), so it needs a toggle in the modal, not an automatic application.

### W8 - subtract 5 from incoming damage that kept an extra die

- [ ] A toggle in `modal_wound_check.html` (and wherever light wounds are entered): "attacker kept extra damage dice" -> subtract 5 from the damage figure before it becomes light wounds.
- [ ] Under D5 this is the one incoming-damage ability worth wiring up, because it changes the Wave Man's **own** LW total rather than an opponent's roll. Confirm the GM agrees (Q9).
- [ ] Must respect the read-only Roll Mode rule: a non-editor toggling this sees the modal math change but `lightWounds` never moves.

### W2, W10, W1-clause-2 - reference text only

- [ ] Rendered in the sheet's profession panel and, where they are contextually relevant, as a reminder line in the attack result panel ("Opponent's parry TN and any wound check they make from this damage are each +5 - tell your GM"). Static text, no new inputs, no computation.

---

## 8. Phase 6 - Bot, API and read-only mode

- [ ] `app/services/roll_engine.py` kept in step with the `roll_math.js` changes, per the standing rule. W6 and W7 ride the formula layer for free; W1/W3/W4/W9 are attack-and-damage display math the slash commands never reach (they only roll skills), so document that rather than duplicating it.
- [ ] W5 is a "you may" interactive choice, so the bot's unconditional roll should **not** apply it. Add a comment saying so, and a `tests/test_roll_engine.py` case asserting an impaired Wave Man's slash-command roll does not reroll 10s.
- [ ] `tests/test_roll_engine.py` mirrors the new `tests/js/roll_math.test.js` cases, as the existing pairs do.
- [ ] **Read-only Roll Mode audit** for every new mutation: the W5 die pick, the W9 toggle, the W8 toggle, and any banked state must be wrapped `if (t.canEdit)`. Apply the standing test: "if a non-editor clicks this five times, does the sheet's displayed state change?"
- [ ] Clicktest: a non-editor walks the whole Wave Man attack flow and the sheet's counters do not move.

---

## 9. Phase 7 - Test suite and coverage

- [ ] `tests/test_professions.py` - new file, data + allowance + validation.
- [ ] New cases in `tests/test_dice.py` (W5, W6, W7), `tests/test_xp.py` (allowance, breakdown row, zero cost), `tests/test_routes.py` (editor and sheet rendering, mutual exclusion via crafted POST).
- [ ] New cases in `tests/js/roll_math.test.js` (or a dedicated `tests/js/wave_man.test.js`) for W1, W3, W4, W5's predicate, W9. Run with `node --test tests/js/*.test.js` (the glob form - the directory form is broken on newer Node).
- [ ] New `professions` mark in `pytest.ini`.
- [ ] `tests/e2e/test_professions.py` - pick Wave Man in the editor, check abilities, hit the allowance ceiling, publish, view the sheet panel, run an attack with W1/W3/W4 firing.
- [ ] Add a Wave Man character to the parametrized JS-error test in `tests/e2e/test_sheet_js_errors.py` (it sweeps schools; a school-less profession character is a new shape and exactly the kind of thing that trips Alpine null access - use `?.` everywhere).
- [ ] Responsive sanity check in `tests/e2e/test_responsive.py`: the 10-ability checkbox list at phone width, no horizontal overflow, no zero-width labels.
- [ ] **Add every new e2e test to `tests/e2e/COVERAGE.md`** with its mark, and add the checklist lines for each new interactive behaviour *before* writing the code (step 4 of the development workflow).
- [ ] Coverage back to 100%, with pragmas only where the policy allows.

---

## 10. Phase 8 - Documentation and deploy

- [ ] `school-features/WaveMan.md` following the house format: rules text per ability, status, rationale, scope decisions, open questions. Note in `school-features/CLAUDE.md` that the directory now also holds professions (or create `profession-features/` and say so).
- [ ] New "Professions" section in the root `CLAUDE.md`: the data model, the allowance rule, the mutual exclusion with schools, and the D5/D6 scope limits.
- [ ] `scripts/build-css.sh` rerun and the rebuilt `app/static/css/app.css` committed.
- [ ] Pre-deploy gate: `node --test tests/js/*.test.js`, the unit suite, and the `professions` + `attack` + `wound_check` e2e marks.
- [ ] Deploy (this is a frontend change, so the standing rule applies).

---

## 11. Open questions for the GM

Nothing here blocks starting Phase 1; each is flagged at the point it first bites.

1. **Q1 - "150 XP" means which number?** Assumed `starting_xp + earned_xp` (total XP the character has), not XP spent. A character who banks XP still unlocks abilities under that reading.

Answer: Correct: total XP the character has, regardless of whether it has been spent.

2. **Q2 - are ability picks locked once made?** Assumed freely re-choosable in the editor, like advantages. If they should lock on publish, that is a different UI and an extra validation rule.

Answer: correct, they are freely re-chooseable in the editor

3. **Q3 - W1: once or repeatedly?** Assumed the +5 applies once, so a roll that misses by 8 still misses.
4. **Q4 - W1 clause 2:** does the defender's parry auto-succeed only against that attack, or does it also skip their parry roll entirely (relevant for anything keyed on their roll result)? Reference text either way, but the wording on the sheet should be right.
5. **Q5 - W3: what counts as "less than 4k2"?** Assumed `rolled < 4` with `kept <= 2`. Unclear how a hypothetical 3k3 or 5k1 weapon compares. The app's weapon list is only katana 4k2 / spear 3k2 / wakizashi 3k2 / knife 2k2 / unarmed 0k2, so this may never come up in practice - but the modal lets a player type any numbers.
6. **Q6 - W4: rounded when?** Assumed the final damage total, after the extra dice for exceeding the TN and after W3 and W9. Rounding an intermediate value would give a different (higher) result.
7. **Q7 - W5: which die, and does it chain?** Assumed the player picks any one die showing a 10, and that die then explodes normally (a second 10 rerolls again). The alternative reading is a single reroll with no chain.
8. **Q8 - W5 vs PCPs.** `rules/10-player_character_points.md` already lets an impaired character spend a PCP to ignore impaired and reroll *all* 10s. Can a Wave Man do both on one roll? Does W5 apply to the same roll types (the PCP rule excludes initiative and the iaijutsu strike)?
9. **Q9 - W8: is a modal toggle the right call?** It is the one "opponent" ability that changes the Wave Man's own light wounds, so under D5 it sits on the boundary. Wiring it up means one checkbox in the wound-check modal; leaving it as reference text means the player does the subtraction by hand.
10. **Q10 - W9: capped at 2, or at the defender's parry skill?** Assumed `min(2, parry skill)` - you cannot get back more dice than the failed parry took away.
11. **Q11 - do any advantages, disadvantages or campaign items assume the character has a school?** Worth a sweep before Phase 3; a Wave Man is the first character shape with no school at all.
12. **Q12 - Attack and Parry** still start at 1 like everyone else for a Wave Man, and the Parry <= Attack + 1 rule still holds? Assumed yes.
13. **Q13 - Rank and Recognition defaults.** The app defaults both to 7.5 (campaign-specific). A ronin arguably should not. Leave as is unless you say otherwise.
14. **Q14 - should Worker / Merchant / Priest / Ninja be selectable now** as pure reference text with no mechanics, or stay greyed out until each is implemented? Plan assumes greyed out, to avoid shipping half-working characters.
15. **Q15 - `rules/11-non_pc_schools.md`** - any overlap or precedence between NPC schools and professions worth modelling? Not read as part of this plan.
