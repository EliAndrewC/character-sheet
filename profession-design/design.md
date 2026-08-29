# Professions: Wave Man implementation plan

Status: **implemented and deployed, 2026-08-29.** Every checkbox below is
done except W3's armor clause, which is blocked on upstream rules (D15) and
deliberately left unchecked.

Two things came out differently from the plan as written, both flagged in the
commits and in `school-features/WaveMan.md`:

1. **The Discord bot DOES apply W5.** The plan (Phase 6) said it must not,
   on the grounds that W5 is a "you may" interactive choice. The GM's later
   ruling that the freed die is selected automatically (D13) removed the
   interaction, so there was nothing left for a slash command to skip - and
   not applying it would have made the same roll come out differently on the
   sheet than through `/etiquette`.
2. **W1's clicktest coverage is at the formula layer for iaijutsu**, not
   through the duel modal: the test asserts that `knack:iaijutsu` carries the
   annotation while `parry` and `initiative` do not, which is the part that
   could plausibly regress.
Created 2026-08-29. Source rules: `rules/09-professions.md` in the GM's `l7r` repo
(bind-mounted at `/host-l7r-repo` in this container).

This is the implementation-tracking checklist, in the spirit of
`import-design/design.md`. Rules intent and rationale that outlive the build
should end up in `school-features/WaveMan.md` (Phase 8), not here.

All rules questions raised during planning have been answered by the GM and are
recorded as decisions in section 1. There is no open-questions section.

---

## 1. Rulings

The upstream rules file lists the ten abilities and nothing else - no cost, no
acquisition text, no stacking rule. Everything below is a campaign ruling from
the GM, recorded here as the authority for the code.

| # | Question | Ruling |
|---|---|---|
| D1 | How are abilities acquired? | **A profession replaces the school.** "Wave Man" is picked in place of a school. |
| D2 | XP cost? | **Zero.** Abilities are free, unlocked by total XP: **1 at 150 XP, plus 1 more per 15 XP beyond.** |
| D3 | Which XP number? | **Total XP the character has** (`starting_xp + earned_xp`), regardless of how much has been spent. Banking XP still unlocks abilities. |
| D4 | Repeat purchases? | **Each ability may be taken up to twice.** True for Wave Man, Worker, Merchant and Ninja; **Priest rituals may be taken only once.** So a Wave Man's ceiling is 20 picks, reached at 435 XP. |
| D5 | How does a second copy scale? | **Uniformly - N copies apply the effect N times.** The two edge cases resolve as: W4 chains (damage 14 -> 15 -> 18 with two copies), and W5 frees a second, separate die. |
| D6 | Are picks locked once made? | **No.** Freely re-choosable in the editor, like advantages. |
| D7 | School Ring / school knacks / Dan? | **None.** All five rings start at 2 and cap at 5. No school knacks, no Dan. |
| D8 | Foreign school knacks? | **Yes, the full list.** A Wave Man buys non-supernatural knacks from any school under the existing 10-XP-for-0->1 rule. Having no school of their own means every knack in the game is "foreign". |
| D9 | What is "an attack roll" for W1/W2? | **Every attack type including the iaijutsu strike.** Note this is a deliberate departure from `ATTACK_TYPE_KEYS`, which excludes iaijutsu (see Phase 5). |
| D10 | W1 with two copies - how many +5s? | **The minimum needed to hit.** Apply raises one at a time and stop as soon as the roll lands; a spare copy goes unused that roll. |
| D11 | Does W1's raise earn extra damage dice? | **No.** The raise gets you to the TN and no further; extra damage dice for exceeding the TN are computed as if the raise had not happened. |
| D12 | W5's scope? | **Same exclusions as the PCP rule** - anywhere 10s could ever reroll, so not initiative and not the iaijutsu strike. Note this cuts the other way from D9: W1 reaches the iaijutsu strike, W5 does not. |
| D13 | W5 - which die, and does it chain? | **Automatically selected, and it chains.** A further 10 on that die rerolls again. This is why the rule says one *die* rather than one *ten*. **No dice-picker UI is needed.** |
| D14 | W8 | **Reference text only**, alongside W2 and W10. |
| D15 | W3's armor clause | **Deferred.** There are no armor rules anywhere in `rules/` - the only match for "armor" in the whole rules directory is inside this ability. Implement the weapon half; leave the armor half unchecked and blocked on upstream rules. |
| D16 | Opponent-facing abilities generally | **Reference text.** Rendered on the sheet so the player can tell the GM; no attempt to model an opponent's rolls. |
| D17 | Build scope | **Generic profession framework now, Wave Man mechanics only.** All five profession lists go into `game_data.py` as data; the other four stay greyed out in the editor until each is implemented. |
| D18 | Advantages/disadvantages that assume a school | **None exist.** The GM confirms this interaction does not arise; skip the sweep. |
| D19 | Attack and Parry for a Wave Man | Start at 1 as for everyone, and Parry <= Attack + 1 still holds. |
| D20 | Rank and Recognition defaults | Leave the app's campaign defaults as they are. |
| D21 | NPC schools (`rules/11-non_pc_schools.md`) | No overlap with professions, now or ever. Not a consideration. |
| D22 | W5 alongside a PCP | **Both may apply to the same roll.** The PCP already lets an impaired character reroll every 10; W5's freed die stacks on top. |

Derived from D2 and D4: allowance is `0` below 150 XP, otherwise
`min(2 * ability_count, 1 + (total_xp - 150) // 15)`. Unlock thresholds run
150 / 165 / 180 / ... / 435 XP for picks 1 through 20.

---

## 2. The ten abilities

Numbered W1-W10 in rules order. Use this numbering in code comments and test
names. Text is verbatim from `rules/09-professions.md`; **W3's wording was
revised upstream on 2026-08-29** to key on dice rolled rather than on `4k2`, so
re-pull the file rather than trusting any older copy.

| id | rules text | per-copy effect (D5) | shape |
|---|---|---|---|
| **W1** | When you make an attack roll that would miss, raise it by 5.  Any parry attempt against an attack that receives a free raise in this manner automatically succeeds. | one +5, applied only while the roll still misses (D10) | own attack roll; clause 2 is reference text |
| **W2** | Raise the TN of someone trying to parry one of your attacks by 5. | +5 each | reference text |
| **W3** | When using a weapon that rolls fewer than 4 damage dice, add an extra rolled damage die to the weapon's base damage, to a maximum of 4 rolled damage dice.  Also, subtract 2 from your armor damage reduction penalty. | +1 rolled die each, hard cap at 4 rolled | own damage; armor clause deferred (D15) |
| **W4** | Round your damage rolls up to the nearest multiple of 5.  If the roll is already a multiple of 5, then raise it by 3. | one rounding step each, chained | own damage total |
| **W5** | You may reroll 10s on a single die when impaired. | one more die freed each | own rolls, automatic (D13) |
| **W6** | Roll one extra unkept die on initiative. | +1 rolled die each | formula layer |
| **W7** | Roll two extra unkept dice on wound checks. | +2 rolled dice each | formula layer |
| **W8** | When someone is keeping at least one extra die of damage from exceeding their attack roll TN, subtract 5 from the damage. | -5 each | reference text (D14) |
| **W9** | When someone unsuccessfully tries to parry an attack, you may roll 2 of the extra damage dice that you would have rolled had they not attempted to parry. | 2 dice each, capped by the defender's parry skill | own damage, reuses existing modal inputs |
| **W10** | Raise the TN of someone making a wound check from damage you dealt to them by 5.  If they fail they take serious wounds as if the TN had not been raised. | +5 each | reference text |

**Implemented with math:** W1, W3, W4, W5, W6, W7, W9.
**Reference text only:** W2, W8, W10, and W1's second clause.

Worked examples to turn into test cases:

- W3 on a 2k2 knife with two copies -> 4k2. On 0k2 unarmed with two copies -> 2k2. On a 3k2 spear with two copies -> 4k2, the second copy wasted against the cap.
- W4 on a damage total of 14: one copy -> 15, two copies -> 18. On 15: one copy -> 18, two copies -> 20.
- W1 on a roll missing by 8: one copy -> still a miss, two copies -> a hit at exactly the TN, with **no** extra damage dice (D11).
- W9 against a defender with parry skill 3 and two copies: `min(4, 3)` = 3 dice recovered.

Two useful facts from the code survey: `modal_attack.html` already carries
`atkTN`, `atkFailedParry` and `atkParrySkill`, which are exactly the inputs W1
and W9 need, and `atkWeaponRolled` / `atkWeaponKept` are already modal inputs, so
W3 has somewhere to land. No new modal fields for any of the three.

One thing that does **not** exist: any "round up to the nearest 5" helper. The
Priest rituals that use the same mechanic are unimplemented reference text. W4 is
new math and belongs in `roll_math.js` per the CLAUDE.md rule about roll
arithmetic.

---

## 3. Working method

Per the development workflow in `CLAUDE.md`, **unit tests are TDD and belong in
the same phase as the code they cover, not at the end.** Every bullet tagged
`TDD:` is written and failing *before* the implementation bullets in its group
are done. That includes the `tests/js/` Node tests, which run in ~0.2s and are
unit tests in every sense that matters here.

**Clicktests are the deliberate exception.** They are slow and are only worth
writing against an implementation that already works, so every one of them lives
in Phase 7 - including the two that would otherwise sit naturally beside the
attack-modal and read-only work. Nothing else is deferred: by the time Phase 7
starts, the unit and JS suites should already be green, and Phase 7 adds browser
coverage and the coverage audit on top.

---

## 4. Phase 1 - Data model and game data

- [x] `Profession` dataclass in `app/game_data.py`: `id`, `name`, `abilities: List[ProfessionAbility]`, `rules_anchor` (the `09-professions.md#...` fragment), `selectable: bool`, `max_per_ability: int` (2 everywhere, 1 for Priest - D4).
- [x] `ProfessionAbility` dataclass: `id` (e.g. `wave_man_miss_raise`), `ordinal` (1-10), `name` (short UI label), `text` (verbatim rules text), `implemented: bool`, `reference_only: bool`, `money_bonus: Optional[str]` (Worker/Merchant carry these), `ritual_time: Optional[str]` (Priest carries these).
- [x] `PROFESSIONS: Dict[str, Profession]` populated with all five lists, text copied verbatim from the **current** `rules/09-professions.md` (W3 was revised on 2026-08-29).
- [x] Only `wave_man` gets `selectable=True`; the other four are present as data with `selectable=False` so the editor can list them greyed out (D17).
- [x] `PROFESSION_ABILITY_BONUSES: Dict[str, dict]` - the profession analogue of `SCHOOL_TECHNIQUE_BONUSES`, keyed by ability id, carrying declarative per-copy hooks (`extra_rolled_die: 1` on `initiative` for W6, `2` on `wound_check` for W7, and so on).
- [x] Import-time guard (the "import-time guards" pragma category in the coverage policy): assert ability ids are unique across all professions and that every `PROFESSION_ABILITY_BONUSES` key names a real ability. `# pragma: no cover` with a one-line why.
- [x] Named constants `PROFESSION_ABILITY_UNLOCK_BASE = 150` and `PROFESSION_ABILITY_UNLOCK_STEP = 15`, so D2 is a one-line change.
- [x] TDD: unit tests (`tests/test_professions.py`) - all five professions load, each has 10 abilities, ids unique, bonuses reference real abilities, `max_per_ability` is 1 for Priest and 2 for the rest.

### Character model

- [x] `Character.profession: Mapped[str] = mapped_column(String, default="")`.
- [x] `Character.profession_abilities: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, default=dict)` - **an id-to-count map, not a list**, because abilities can be taken twice (D4). Same shape as `knacks` / `skills`.
- [x] **Migration entry in `_migrate_add_columns()` in `app/database.py` for both columns.** Non-optional: prod SQLite persists across deploys and `create_all` will not add them. (CLAUDE.md, "New model columns require a migration entry".)
- [x] Both fields flow through `Character.to_dict()` and whatever builds `character_data`.
- [x] Both fields included in `_snapshot_state()` so they are version-significant, and restored by `_restore_character_from_state()` (Discard / Revert / version diff).
- [x] Version-diff rendering (`partials/version_diff.html`) shows profession and ability changes readably, including a count going 1 -> 2, not raw ids.
- [x] TDD: round-trip a profession character through publish -> snapshot -> revert; assert a changed ability count flips `has_unpublished_changes`.

### Mutual exclusion with schools

- [x] Setting `profession` clears `school`, `school_ring_choice`, `knacks` and `technique_choices`. **`foreign_knacks` is preserved** - a Wave Man keeps buying those (D8). Enforced server-side in the save path, not only in Alpine.
- [x] Setting `school` clears `profession` and `profession_abilities`.
- [x] TDD: unit tests for both directions, including a crafted POST that sends both.

---

## 5. Phase 2 - Allowance and XP engine

- [x] `profession_ability_allowance(total_xp: int, profession_id: str) -> int` in `app/services/xp.py`, implementing D2/D3/D4 and clamping to `max_per_ability * len(abilities)`.
- [x] Total XP is `starting_xp + earned_xp` (D3).
- [x] TDD: boundary tests - 149 -> 0, 150 -> 1, 164 -> 1, 165 -> 2, 435 -> 20, 1000 -> 20 (capped), plus a negative/`None` guard.
- [x] TDD: abilities contribute **0** to XP spend - assert that adding abilities does not move `spent` or `remaining`.
- [x] XP breakdown gains an informational row: "Wave Man abilities: 5 of 5 picks used - 0 XP". In `calculate_xp_breakdown()` (published sheet) and `editor_xp_view()` (live editor).
- [x] `editor_xp_view()` payload carries `profession_allowance` so the editor's counter rides the existing ~250ms debounce rather than being recomputed in Alpine (per the "XP lives only in services/xp.py" architectural decision).

### Validation (`validate_character`)

- [x] Error: total picks (sum of counts) exceed the allowance.
- [x] Error: any single ability's count exceeds `max_per_ability`, or is below 1 when the key is present.
- [x] Error: an ability id not in the selected profession's list.
- [x] Error: `school` and `profession` both set.
- [x] Error: `profession` set to an id not in `PROFESSIONS`, or to a `selectable=False` profession.
- [x] Error: `profession` set but native `knacks` non-empty, or `school_ring_choice` non-empty (D7). `foreign_knacks` is explicitly allowed.
- [x] Warning (soft, never blocks publish, like the Dark Secret warnings): "You have N unclaimed Wave Man picks."
- [x] TDD: regression test that the ring min/max block gives every ring min 2 / max 5 when `school_ring == ""`, rather than trusting that it does.
- [x] TDD: regression test that `compute_dan({})` returns 0 and that nothing downstream (formula builders, sheet, XP) breaks at Dan 0. Run a Wave Man end to end through `build_all_roll_formulas`.
- [x] TDD: regression test that `merged_knacks()` behaves for a character whose knacks are entirely foreign.
- [x] TDD: one unit test per error and warning above (the coverage policy forbids pragmas on validation paths).

---

## 6. Phase 3 - Editor UI

- [x] The school `<select>` in `edit.html` gains a "Professions" optgroup below the school groups: Wave Man selectable, the other four `disabled` and labelled "not yet implemented".
- [x] Alpine `school` state generalized to carry a profession value, or a parallel `profession` model - decide once and stay consistent. The `x-show` conditions around `edit.html` lines 621-900 (school-ring picker, knacks section, the Mantis/Kitsune/Isawa/Priest technique pickers, the flexible 2nd Dan picker) must all stay hidden for a profession.
- [x] Switching from a school to a profession shows a confirm dialog: knacks and technique choices will be cleared. It should say foreign knacks are kept.
- [x] The foreign-knack picker stays visible for a profession character, and its "exclude my own school's knacks" filter degrades to excluding nothing when there is no school (D8). Check this explicitly - it is the sort of filter that throws on a missing school object.
- [x] New "Wave Man Abilities" section listing all ten in W1-W10 order with full rules text.
- [x] Each ability gets a **0/1/2 stepper**, not a checkbox (D4). Reuse the `.btn-pip` square +/- stepper from the button system rather than inventing a control.
- [x] Counter line: "5 of 5 picks used. First pick at 150 XP, one more every 15 XP. Next at 240 XP."
- [x] `+` disables when the allowance is exhausted or the ability is at `max_per_ability`; `-` disables at 0. Tooltips say which limit was hit.
- [x] Reference-only abilities (W2, W8, W10) and the partially-implemented ones (W1's clause 2, W3's armor clause) carry a badge saying what the sheet does and does not compute, so nobody is surprised mid-session.
- [x] `profession` and `profession_abilities` added to the autosave POST payload and the Alpine initial state (`tojson` with single-quote attribute delimiters, per the house style rule).
- [x] Hidden inputs / state sync so a full non-AJAX form POST carries them too.
- [x] `scripts/build-css.sh` rerun after the template edits so the committed CSS covers any new classes.
- [x] TDD: unit tests on the edit route - the profession section renders, all ten abilities appear, the allowance line reflects XP, steppers disable at the right boundaries.

---

## 7. Phase 4 - View sheet and other render surfaces

- [x] `partials/sheet/school.html` renders a **profession panel** when `character.profession` is set: name in the header, no Dan chip, no School Ring line. Chosen abilities emphasised (with a "x2" marker where taken twice), unchosen ones at 40% opacity - mirroring how techniques above and below Dan already render.
- [x] Link to `https://github.com/EliAndrewC/l7r/blob/master/rules/09-professions.md#wave-man-abilities`, following the existing Priest-rituals link pattern in `app/main.py`.
- [x] Reference-text callout for W2, W8, W10 and W1's second clause: "Tell your GM - the sheet cannot apply this for you." W1's clause-2 wording must say the parry **is still rolled** and merely auto-succeeds, since a defender can still key bonuses off the roll's magnitude (the Shiba Bushi 5th Dan technique does exactly this).
- [x] The "No school selected yet" empty state must not fire for a profession character.
- [x] Group summary page shows "Wave Man" wherever a school name is shown.
- [x] `app/services/sheets.py` Google Sheets export: profession name and chosen abilities with counts on the Character Sheet tab; the informational row on the XP Breakdown tab.
- [x] `app/routes/gm_api.py` `GET /api/characters`: include `profession` and `profession_abilities` (the GM's REPL scores contested rolls off this data).
- [x] TDD: unit tests per render surface, plus a JSON-shape test for the API addition.

---

## 8. Phase 5 - Dice and roll math, one ability at a time

House rule from CLAUDE.md: **the arithmetic goes in `app/static/js/roll_math.js`
with a `tests/js/` test; the Alpine layer owns only the interaction.** Anything
that is a pure formula change goes in `app/services/dice.py` and is picked up by
the sheet, the Discord bot and `roll_engine.py` for free.

Every helper below takes the **copy count** (0, 1 or 2) as an argument, not a
boolean.

### W6 - one extra unkept die on initiative per copy (do this first; it is the smallest)

- [x] `build_initiative_formula()` adds `1 * copies` rolled dice, not kept. Mind initiative's own shape: `(Void+1)` dice, keep all but the highest, no 10s reroll.
- [x] Bonus source string so the sheet shows "+2 rolled dice from Wave Man".
- [x] TDD: unit test in `tests/test_dice.py` at 0, 1 and 2 copies.
- [x] Confirm it flows through `roll_engine.py` unchanged (it is a formula-layer change, so it should).

### W7 - two extra unkept dice on wound checks per copy

- [x] `build_wound_check_formula()` adds `2 * copies` rolled dice.
- [x] Interaction with `apply_dice_caps()` (the 10k10 cap): a high-Water Wave Man with two copies adds 4 dice and can push past it. Test the boundary.
- [x] TDD: unit test at 0, 1 and 2 copies.

### W3 - weapon damage floor (clause 1 only; clause 2 deferred per D15)

- [x] `waveManWeaponFloor(rolled, copies)` in `roll_math.js`: add 1 rolled die per copy while below 4, hard-capped at 4. **Keyed on dice rolled only** - the revised rules text says nothing about dice kept.
- [x] TDD: `tests/js/` test for the worked examples in section 2, plus 4k2 katana unchanged at any copy count.
- [x] Applied to `atkWeaponRolled` in `modal_attack.html` and `duelWeaponRolled` in `modal_duel.html` as a **displayed adjustment**, not a silent mutation of the input, so the player can see where the die came from.
- [x] The damage formula preview on the sheet reflects it.
- [x] **Not** applied in `modal_kakita5.html` - a Wave Man cannot be a Kakita Duelist.
- [ ] Armor half: leave unchecked, blocked on upstream rules (D15).

### W4 - round damage up to the nearest 5, +3 if already a multiple

- [x] `waveManRoundDamage(total, copies)` in `roll_math.js`, applying the step `copies` times. Note the sharp edge: 15 -> 18, not 20.
- [x] TDD: `tests/js/` test at 0, 1 and 2 copies over 0, 1, 3, 4, 5, 14, 15, 16, 20 and a large value.
- [x] Applied to the final damage total in the attack and duel modal results, **after everything else** - after the extra dice for exceeding the TN, after W3 and after W9 (D5 ordering).
- [x] The result panel shows the raw roll and the rounded value, not just the rounded one.

### W5 - reroll 10s on one die per copy while impaired

- [x] **No dice-picker UI** (D13). The die is selected automatically; all 10s are interchangeable at reroll time, so any choice is equivalent. This is a large simplification over the Hida 3rd Dan flow, which does need a picker.
- [x] The selected die chains: a further 10 rerolls again, indefinitely.
- [x] `L7RRollMath.impairedSuppressesReroll()` and its server twin (the `impaired` no-reroll reason in `_reroll_fields` / `build_all_roll_formulas`) must learn that a Wave Man's suppression is **partial**, not cleared. Careful: the Hida 3rd Dan work left a trap here - the "am I impaired?" check must read character state, not `!formula.reroll_tens`.
- [x] Scope per D12: everywhere 10s could ever reroll, so not initiative and not the iaijutsu strike. Cross-check against commit `c80bf87` - Impaired now also suppresses ring and athletics rolls, so W5 reaches those; wound checks and damage already keep their 10s while Impaired, so W5 adds nothing there.
- [x] Stacks with the PCP impaired-reroll (D22): a player may use both on one roll. Test that combination.
- [x] TDD: `tests/js/` tests for the predicate, `tests/test_dice.py` for the formula annotation, at 0, 1 and 2 copies.

### W1 - raise a missing attack roll by 5 per copy

- [x] `waveManMissRaise(total, tn, copies)` in `roll_math.js`, returning the adjusted total and how many raises were consumed. Applies raises one at a time and **stops as soon as the roll hits** (D10); a spare copy goes unused.
- [x] Uses the existing `atkTN` modal input.
- [x] **The raised total must not generate extra damage dice** (D11). Assert this directly: a roll raised to exactly the TN, and one raised past it, must both yield zero excess dice.
- [x] Result panel shows "missed by 8, raised by 10 from Wave Man - hits" plus the clause-2 warning that the defender's parry auto-succeeds (while still being rolled).
- [x] **Scope includes the iaijutsu strike (D9).** This is the one place the plan departs from existing structure: `ATTACK_TYPE_KEYS` in `dice.py` is `{"attack", "double_attack", "counterattack", "lunge"}` and iaijutsu is deliberately outside it (there is a comment saying so). Define a separate `WAVE_MAN_ATTACK_KEYS = ATTACK_TYPE_KEYS | {"iaijutsu"}` rather than widening `ATTACK_TYPE_KEYS`, which would change behaviour for every school. The duel modal path needs W1 wired in separately from the attack modal path.
- [x] This matters more than it looks because of D8: a Wave Man can buy `counterattack`, `double_attack`, `lunge` and `iaijutsu` as foreign knacks, so all five attack shapes are genuinely reachable. Test each.
- [x] TDD: `tests/js/` test for `waveManMissRaise` at 0, 1 and 2 copies, including the raised-to-exactly-the-TN case from D11. (The matching clicktest is in Phase 7.)

### W9 - recover damage dice the failed parry took away

- [x] Reuses `atkFailedParry` and `atkParrySkill`, already present in `modal_attack.html`.
- [x] Base rule (`rules/03-combat.md`): the extra damage dice from exceeding the TN are reduced by the defender's parry skill when they attempted and failed to parry. W9 gives back `min(2 * copies, parrySkill)` - you can never recover more than the parry removed.
- [x] TDD: `tests/js/` test for the helper, including the worked example in section 2, then the `roll_math.js` helper itself.
- [x] Optional ("you may"), so it needs a toggle in the modal rather than automatic application.

### W2, W8, W10, W1-clause-2 - reference text only

- [x] Rendered in the sheet's profession panel, and as a reminder line in the attack result panel where contextually relevant ("Opponent's parry TN and any wound check from this damage are each +10 - tell your GM"). The line must reflect the copy count. Static text, no new inputs, no computation.

---

## 9. Phase 6 - Bot, API and read-only mode

- [x] `app/services/roll_engine.py` kept in step with the `roll_math.js` changes, per the standing rule. W6 and W7 ride the formula layer for free; W1/W3/W4/W9 are attack-and-damage display math the slash commands never reach (they only roll skills), so document that rather than duplicating it.
- [x] W5 is a "you may" interactive choice, so the bot's unconditional roll must **not** apply it. Add a comment saying so, plus a `tests/test_roll_engine.py` case asserting an impaired Wave Man's slash-command roll does not reroll 10s.
- [x] TDD: `tests/test_roll_engine.py` mirrors the new `tests/js/roll_math.test.js` cases, as the existing pairs do.
- [x] **Read-only Roll Mode audit** for every new mutation: the W9 toggle and any banked state must be wrapped `if (t.canEdit)`. Apply the standing test - "if a non-editor clicks this five times, does the sheet's displayed state change?" W5 needs no gate, since it is automatic and touches no persisted field.

---

## 10. Phase 7 - Clicktests, coverage audit and the e2e gate

By this point the unit and `tests/js/` suites are already green - they were
written phase by phase, ahead of the code (see "Working method"). Nothing in this
phase is a unit test. What is left is the browser coverage, which is deliberately
last because clicktests are slow and only worth writing against an
implementation that already works.

- [x] New `professions` mark in `pytest.ini`, documented in `tests/e2e/COVERAGE.md` for classification. **The pre-merge gate is a `-k` filter naming the tests, not the mark** (CLAUDE.md, "Gate on a `-k` filter, not on a whole mark").
- [x] `tests/e2e/test_professions.py`: pick Wave Man in the editor, step abilities to 2, hit the allowance ceiling, publish, view the sheet panel.
- [x] Clicktest the W1 attack flow: an attack that misses, raised to a hit, showing the clause-2 parry warning and yielding no extra damage dice (D11).
- [x] Clicktest W1 on the **iaijutsu strike** via the duel modal (D9) - the departure from `ATTACK_TYPE_KEYS`, so the one most likely to be wired up in only one of the two paths.
- [x] Clicktest the W3 + W4 damage path end to end, confirming the rounding lands last.
- [x] Clicktest: a non-editor walks the whole Wave Man attack flow and the sheet's counters do not move (moved here from the read-only audit in Phase 6, which stays a code-review item).
- [x] Add a Wave Man character to the parametrized JS-error test in `tests/e2e/test_sheet_js_errors.py`. It sweeps schools, and a school-less profession character is a new shape - exactly what trips Alpine null access. Use `?.` on anything school-derived.
- [x] Responsive sanity check in `tests/e2e/test_responsive.py`: the ten-ability stepper list at phone width, no horizontal overflow, no zero-width labels.
- [x] **Add every new e2e test to `tests/e2e/COVERAGE.md`.** The checklist lines for each new interactive behaviour go in *before* the code, at the start of Phase 3 (step 4 of the development workflow); this bullet is marking them `[x]` with test references.
- [x] Coverage audit back to 100%, with pragmas only where the policy allows.

---

## 11. Phase 8 - Documentation and deploy

- [x] `school-features/WaveMan.md` in the house format: rules text per ability, status, rationale, scope decisions. Carry the section-1 rulings across, since that is exactly the "design intent not derivable from the code" the directory exists for. Note in `school-features/CLAUDE.md` that the directory now also holds professions (or create `profession-features/` and say so there).
- [x] New "Professions" section in the root `CLAUDE.md`: the data model, the allowance rule, the two-copy limit, mutual exclusion with schools, foreign knacks remaining available, and the D14/D15/D16 scope limits.
- [x] `scripts/build-css.sh` rerun and the rebuilt `app/static/css/app.css` committed.
- [x] Pre-deploy gate: `node --test tests/js/*.test.js`, the unit suite, and a `-k` clicktest selection covering the profession editor, the sheet panel, and the attack/duel/wound-check flows this touched.
- [x] Deploy - this changes the frontend, so the standing rule applies.
