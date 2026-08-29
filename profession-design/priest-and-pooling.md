# Professions, part 2: one Profession type, and the Priest rituals

Status: **implemented and deployed, 2026-08-29.** Every checkbox below is done.

Every rules question raised during planning was answered by the GM and is
recorded in section 1. There is no open-questions section.

Two notes from the build:

1. **`GET /characters/api/profession-info/{id}` became `/api/profession-info`**
   with no id, as Phase 3 left open. There is one character type, so a
   per-profession partial had nothing to say.
2. **A test written for coverage caught a real bug**: `profession_xp_summary`
   formatted its per-row labels straight off the stored counts and crashed on
   a non-integer left by an older release. Counts are coerced once up front
   now.
Created 2026-08-29. Follows `profession-design/design.md` (the Wave Man build,
now shipped). Source rules: `rules/09-professions.md`.

Two changes:

1. **Restructure.** A character's type becomes plain **Profession**, not "Wave
   Man" or "Worker". A profession character may then take abilities from any
   available profession and mix them freely - a wave man who moves to a city
   and picks up work, or who prays at a temple often enough that the monks
   teach him a ritual.
2. **Turn on the Priest rituals** as the first test of that mixing.

---

## 1. Rulings

Everything in the Wave Man build (`design.md` D1-D22) carries over unchanged
unless contradicted here.

| # | Ruling |
|---|---|
| P1 | **One character type: "Profession"**, not one type per profession. Abilities are grouped under "Wave Man", "Priest" etc. headings. |
| P2 | **Abilities pool across every available profession** and may be mixed freely. No cap on how many come from one profession beyond that profession's own supply. |
| P3 | **All ten Priest rituals are takeable.** Only the three with existing mechanics (R7, R8, R9) get sheet features; the other seven are narrative - they show as taken and nothing else happens. |
| P4 | **R7 and R8 are separately takeable.** They are two abilities, so taking one grants only its button. |
| P5 | **The sick-or-impaired ritual (R9) may target the priest themselves or an ally.** |
| P6 | **Worker and Merchant abilities are shown greyed out**, as existing but not yet available. **Ninja abilities are not shown at all** - they are special, need to be unlocked, and are out of scope for this effort. |
| P7 | The per-ability limit is unchanged: twice for most professions, **once for Priest rituals**, because a ritual is a thing you have learned. So one profession supplies at most 20 picks; a character who reaches 450 total XP has 21 picks and must branch out into a second profession. |
| P8 | Unlock cadence unchanged: one pick at 150 total XP, one more every 15 after (D2/D3). |
| P9 | **R9's self-targeting applies to Priest *school* characters too**, not only to profession characters. It is one ritual; a 5th Dan priest explicitly "has all 10". This supersedes shipped behaviour - see section 2. |
| P10 | **The editor shows every ability; the View Sheet shows only the ones taken**, grouped by profession. |

---

## 2. Where the Priest rituals actually stand

The Priest school's Special Ability is "You have all 10 rituals listed under
the Priest profession", but **only three of the ten have machinery**;
`school-features/Priest.md` has recorded this since the school was built. Under
P3 that is fine - the other seven become takeable narrative entries - but it
means "the Priest school already implements these" is only a third true, and
the three that exist need rewiring rather than reuse.

Ritual numbering follows `rules/09-professions.md`.

| # | ritual | today | under this plan |
|---|---|---|---|
| R1 | Extra void point on a night the target starts with 0 VP | narrative | narrative |
| R2 | Heal an extra serious wound on an off-night | narrative | narrative |
| R3 | Once per combat phase, pick attack/parry/damage/wound checks: you and all allies round those rolls up to the nearest 5 | narrative | narrative |
| R4 | Once per conversation, pick a skill; your side rounds it up, chosen after seeing a result | narrative | narrative |
| R5 | Spend a void point to roll **precepts** as a commune for nearby supernatural influence | narrative | narrative |
| R6 | Two free raises to resist disease | narrative | narrative |
| R7 | Bless a conversation topic: target rolls 2k1 extra on their first contested roll on it | **implemented** | rewired, split from R8 |
| R8 | Bless research: target rolls 2k1 extra | **implemented** | rewired, split from R7 |
| R9 | Target ignores sickness/impaired penalties in the next conversation or fight | **implemented** | rewired, plus self-targeting |

Two things about the three that exist:

- **They are gated on being a Priest *school* character, not on holding the ritual.** `priest_bless_rituals` in `app/routes/pages.py` is `character.school == "priest"`, and it is **one flag that turns on both** the R7 and R8 buttons. `party_priests` - which puts the R9 button on a sheet - filters `p.school == "priest"`.
- **`visible_party_members` excludes the character themselves** (`Character.id != character.id` in `app/services/party.py`), so today's R9 button appears only on an *ally's* sheet. Under P5 and P9 the ritual may target the priest themselves, for school and profession characters alike. This is the one place the plan **supersedes working, tested behaviour** rather than adding to it; the tests that pin the old rule are named in Phase 5.

**R5's "commune" is not a coincidence of naming.** It is deliberately the same
name as the `commune` school knack because it is the weaker version of it:
rolled with **precepts** rather than with the knack, same void-point cost, and
limited to detecting supernatural influence that is currently present or nearby
(type, strength, proximity) where the knack questions the kami about events
they witnessed. It stays narrative here, but the relationship is now recorded
in `school-features/Priest.md` and beside the knack's void-point cost in
`app/services/dice.py`, so nobody later "fixes" one into the other.

---

## 3. Working method

Same as the Wave Man build, for the same reasons: **unit tests are TDD and live
in the phase that owns the code**, tagged `TDD:` below and written failing
before the implementation bullets in their group. Clicktests are the deliberate
exception and all sit in the last phase.

The restructure touches shipped, tested code, so **every phase must leave the
existing 3592 unit tests, 150 JS tests and 29 profession clicktests green**,
not just its own.

---

## 4. Phase 1 - the data model becomes a pool

- [x] `TDD:` tests for the pooled accessors, the three-state availability, and the migrated character type.
- [x] `Profession.selectable` becomes **`availability`** with three states, because P6 needs three: `"available"` (abilities are takeable - Wave Man, Priest), `"preview"` (shown greyed out, not takeable - Worker, Merchant), `"hidden"` (absent from the UI entirely - Ninja). A boolean cannot express this.
- [x] `PROFESSION_CHARACTER_TYPE = "profession"` sentinel; `Character.profession` stores that rather than a profession id. Column and migration entry are unchanged.
- [x] **Data migration** for existing rows: any `profession` holding a profession id becomes the sentinel. `profession_abilities` needs no change - ability ids are globally unique and carry their own provenance via `PROFESSION_BY_ABILITY`. Goes beside `_migrate_legacy_specializations` in `database.py` as a data migration, not an `ALTER TABLE`, and gets a **real test** rather than a pragma: unlike the ALTER branches it is reachable on a fresh DB.
- [x] `PROFESSION_ABILITY_POOL` - every ability from every `available` profession, in profession order then ordinal.
- [x] `split_school_or_profession()` accepts the bare value `"profession"`. Keep accepting the old `profession:<id>` form for one release and map it to the sentinel: a stale editor tab open across the deploy will send it, and silently resolving to "no profession" would wipe a character's abilities.
- [x] `sanitize_profession_abilities()` loses its `profession_id` argument. It accepts any ability whose profession is `available`, and clamps each to **that ability's own profession's** `max_per_ability` - so a Wave Man ability caps at 2 and a Priest ritual at 1 **in the same character**. Abilities from `preview` and `hidden` professions are dropped.
- [x] `ability_count()` drops its "belongs to this character's profession" check: it becomes "this is a profession character, and this ability's profession is available".
- [x] `ability_counts_for_display()` returns grouped rows - `[{profession_id, name, rules_anchor, availability, rows: [...]}, ...]` - and takes a flag for whether to include untaken abilities, since the editor wants all of them and the sheet wants only the taken ones (P10).
- [x] `TDD:` a character holding both a Wave Man ability and a Priest ritual round-trips through save, snapshot, revert and the diff summary.
- [x] `TDD:` a crafted POST naming a Ninja or Worker ability is dropped on write.

## 5. Phase 2 - allowance and validation

- [x] `TDD:` boundary tests for the pooled ceiling and the mixed per-ability limits.
- [x] `profession_ability_allowance()` loses its `profession_id` argument; the ceiling becomes the **sum of `max_total_picks` over `available` professions** - 20 (Wave Man) + 10 (Priest rituals) = **30 picks, reached at 585 XP**. `preview` professions do not count. The unlock cadence is untouched.
- [x] The ceiling clamp matters for more than tidiness: it is what stops a 600-XP character being nagged forever by the soft "unclaimed picks" warning about picks the pool cannot supply.
- [x] Pin P7's worked example as a test: **at 450 total XP a character has 21 picks and Wave Man alone supplies 20**, so the 21st must come from another profession.
- [x] `_validate_profession()` updates: "not a Wave Man ability" becomes "not an ability of any available profession"; the per-ability limit reads the owning profession's max; the unimplemented-profession error now fires on an ability from a `preview`/`hidden` profession rather than on the character's type.
- [x] XP breakdown and `editor_xp_view` rows relabel to "Profession abilities" and group their `rows` by profession.
- [x] `TDD:` one test per changed error path, plus a mixed-profession character that validates clean.

## 6. Phase 3 - editor

- [x] The dropdown's "Professions (no school)" optgroup collapses to **one option, "Profession"**. The individual professions stop being character types.
- [x] The abilities section renders **one block per profession**, each with a heading and a link to that profession's rules anchor. Wave Man and Priest are interactive; **Worker and Merchant render greyed out with their steppers disabled** and a short "not yet available" note; **Ninja is absent** (P6).
- [x] The allowance counter is pool-wide; each ability's + still disables at its own profession's max, so a Priest ritual stops at 1 beside a Wave Man ability that goes to 2.
- [x] Priest rituals need a visible marker that they are **once-only**, since every other ability on the page goes to 2 and an unexplained disabled + reads as a bug.
- [x] `GET /characters/api/profession-info/{id}` becomes `/api/profession-info` with no id, describing the character type rather than one profession.
- [x] Alpine: `isProfession()` compares against the sentinel; `PROFESSIONS_DATA` carries `availability` and the grouping; `professionName()` becomes the type label.
- [x] `TDD:` editor route tests for the single option, all four visible groups, Ninja's absence, the disabled preview steppers, and the pooled counter.
- [x] Rerun `scripts/build-css.sh`.

## 7. Phase 4 - sheet and other surfaces

- [x] The sheet's profession panel headers as "Profession" and shows **only the abilities the character has actually taken**, grouped by source profession (P10). A character with three Wave Man abilities and one ritual sees four entries under two headings, not thirty rows at 40% opacity.
- [x] Keep the x2 chip and the reference-only "tell your GM" note. The seven narrative rituals get that same note, since taking one is a real choice the GM needs to know about even though the sheet does nothing with it.
- [x] Google Sheets export, group summary and `GET /api/characters` relabel; the API keeps sending the ability map unchanged, which already carries provenance.
- [x] `TDD:` render tests for a mixed character on each surface, including that untaken abilities do **not** appear on the sheet.

## 8. Phase 5 - the Priest rituals

- [x] Mark `priest` as `available`, putting all ten rituals in the pool.
- [x] **Split `priest_bless_rituals` into two flags**, one for R7 and one for R8 (P4). Each becomes `character.school == "priest" or holds(that ritual)`. A priest-school character keeps both, as today.
- [x] Widen `party_priests` in `pages.py` to include profession characters holding **R9**, so the "blessed for 10 rerolls" button appears on an ally's sheet for them too.
- [x] **Self-targeting for R9** (P5, P9), for school and profession characters alike: the blesser list must be able to include the viewing character.
- [x] **Do not change `visible_party_members` to do it.** It excludes self by design and is shared with Priest 5th Dan conviction, Priest 3rd Dan precepts sharing, Daidoji 3rd Dan and the party-effect layer generally; a self entry leaking into those would be a subtle, hard-to-spot bug. Build the self entry alongside the party list inside the `party_priests` block in `pages.py`, where the blast radius is one feature.
- [x] The self entry needs its own label - the existing button reads "<priest name> priest blessed for 10 rerolls", which is wrong when the priest is you.
- [x] `TDD:` **invert `tests/test_routes.py::TestPartyPriests::test_priest_does_not_appear_in_their_own_party_priests`.** It asserts today's rule in its name and its docstring, so rename it rather than editing the assertion in place, and say in the docstring that P9 changed the rule. This is the clearest signal in the diff that shipped behaviour moved on purpose.
- [x] Priest *school* characters are otherwise unaffected: 5th Dan still grants all ten, and a school character cannot take profession abilities at all, so there is no double-dipping path to guard.
- [x] The seven narrative rituals need **no mechanics** (P3) - they are list entries with reference text.
- [x] `TDD:` the R7 button appears for a profession character holding R7 and not for one holding only R8, and vice versa; a priest-school character still gets both; a profession character holding R9 appears in an ally's `party_priests`; a character holding R9 can bless themselves.

## 9. Phase 6 - clicktests, coverage and docs

Nothing here is a unit test; those are done by now, phase by phase.

- [x] Update the existing 29 `test_professions.py` clicktests for the new dropdown value and grouped ability list. Most need only the helper changed.
- [x] `select_profession()` in `tests/e2e/helpers.py` loses its argument.
- [x] New clicktest: a character takes Wave Man abilities **and** a Priest ritual, publishes, and both render under their own headings on the sheet.
- [x] New clicktest: the per-ability ceiling differs within one character - a Wave Man ability reaches 2, a Priest ritual stops at 1.
- [x] New clicktest: Worker and Merchant blocks render greyed out with disabled steppers; no Ninja block appears anywhere.
- [x] New clicktest: a profession character with R7 gets that bless button and not R8's.
- [x] New clicktest: a lone priest in a group can bless themselves - the counterpart to the inverted unit test, and the case that had no coverage at all before because it could not happen. The existing ally-blessing clicktest around `tests/e2e/test_school_abilities.py:8132` should keep passing untouched.
- [x] New clicktest: the sheet lists only taken abilities.
- [x] Update the `profession:wave_man` case in `test_sheet_js_errors.py` to the new value, and add a mixed-profession character to the sweep.
- [x] Coverage back to 100%.
- [x] Docs: `COVERAGE.md`; `school-features/WaveMan.md` (its acquisition section describes per-profession character types and is now wrong); the Priest ritual story in `school-features/Priest.md`; and the Professions section of `CLAUDE.md`.
- [x] Deploy.
