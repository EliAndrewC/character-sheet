# Worker and Merchant abilities

**Profession IDs:** `worker`, `merchant`
**Rules:** `rules/09-professions.md#worker-abilities`, `#merchant-abilities`
**Design + implementation checklist:** `profession-design/worker-and-merchant.md`

Two ability sets a **Profession** character can draw on, alongside Wave Man
and Priest. A profession character mixes freely across all four - a wave man
who settles in a city picks up a worker's habits, and a merchant who prays at
the temple learns a ritual - so these are groups of abilities, not kinds of
character. See `school-features/WaveMan.md` for how a Profession character is
built.

Numbered **Wk1-Wk10** and **M1-M10**, matching the order in the rules file.

---

## The shape of these two lists

Almost all of them are **conditional free raises**, and that is the whole
design: the condition ("relating to your business", "for feats of strength",
"when making purchases") is something only the player can judge, so the bonus
becomes an **"Alternative totals" row** rather than an unconditional flat
bonus. The label is the entire gate - the sheet never tries to decide whether
a roll relates to your business, exactly as it never decides whether the
Streetwise advantage's condition applies.

A character who takes many of these will see a lot of alternative rows on
their rolls. That is the intended shape of the feature, not a symptom.

Two abilities do not fit that mould, for a reason worth remembering: **an
alternative total is arithmetic on a roll that has already happened**, so it
can add a number but never dice, and it can only ever offer one number per
row. Hence M10 is a pre-roll choice and M4 emits two rows.

---

## Worker

| # | ability | status |
|---|---|---|
| Wk1 | Regain a VP with 4 fewer hours of sleep | Narrative - the app has a Night's Rest but does not model hours slept |
| Wk2 | Sickness penalties halved | Narrative - no sickness mechanics |
| Wk3 | Ignore one day's fatigue | Narrative - no fatigue mechanics |
| Wk4 | 3 free raises on etiquette with a social superior | Alternative row |
| Wk5 | Buy advanced-but-normally-basic skills as basic | **Not selectable** |
| Wk6 | 3 free raises on commerce when purchasing | Alternative row |
| Wk7 | 4 free raises on bragging and precepts about your ethics | Alternative row |
| Wk8 | 2 free raises on **Water athletics** for feats of strength | Alternative row |
| Wk9 | 2 free raises on **Earth athletics** for feats of endurance | Alternative row |
| Wk10 | 5 free raises on **open** sincerity and tact vs authority | Alternative row, open rolls only |

**Wk5 is the only ability in any profession held back individually.** It is
campaign-specific, as its own parenthetical says, so it renders greyed out
inside an otherwise-live Worker block rather than vanishing - a player should
be able to see that it exists. This is what `ProfessionAbility.available` is
for; profession-level availability could not express it.

**Wk8 and Wk9 forced a second exception to an existing rule.** The
`athletics:<Ring>` roll keys are normally only emitted for characters with the
athletics knack, because without it the roll is identical to the bare
`ring:<Ring>` roll and the ring tile's picker drops the redundant row. A
Worker bonus makes the athletics roll genuinely different, so the key has to
stay reachable - the same reasoning the Kitsune Warden 4th Dan exception
already documents beside it. Miss this and the ability is simply unreachable
for anyone without the knack.

These two were also reworded upstream on 2026-08-29: they used to say
"strength rolls" and "endurance rolls", which named a roll type this app does
not have and the rules did not define.

---

## Merchant

| # | ability | status |
|---|---|---|
| M1 | 2 free raises on sincerity re your business | Alternative row |
| M2 | 2 free raises on interrogation re your business | Alternative row |
| M3 | 4 free raises on investigation re your business | Alternative row |
| M4 | 3 free raises on bragging and precepts re your business experience, 4 if contested | **Two** alternative rows |
| M5 | 2 free raises on contested commerce when your commerce skill matches your opponent's | Alternative row |
| M6 | 4 free raises on culture for purchasing gifts | Alternative row |
| M7 | 5 free raises on heraldry for knowing your customers | Alternative row |
| M8 | 3 free raises on law re your business | Alternative row |
| M9 | Spend a void point to reroll any roll re your business | **Reroll button** |
| M10 | 4 extra dice on open commerce re your business | **Pre-roll variant** |

**M4 needs two rows because a row states one number.** "3 free raises, and an
extra one if contested" cannot be a single row that says both, and the sheet
cannot know which kind of roll the player is making.

**M5's condition names the opponent's commerce skill**, which the sheet has no
way to know. It is label text, like every other conditional bonus's condition.

**M10 is chosen before the roll, not after.** The commerce tile offers "Roll
Commerce" and "Open commerce relating to your business" as separate rows, each
with its own void-spend submenu - the same shape a Ring tile uses to offer a
ring roll and its athletics variant. Once chosen there is no conditionality
left to resolve, which is exactly why it works where an alternative row could
not. `PROFESSION_ROLL_VARIANTS` is generic, so the next ability of this shape
is a data change.

Slash commands stay on the plain roll: `/commerce` has nobody to ask which
kind of roll it is, and guessing would make the same command mean two things.

**M9 is a reroll, and shares the one-reroll lock** with the Lucky advantage
and the PCP reroll in both directions - none of the three may follow another
on one roll. It resolves the way they do (the higher of the two stands) and
spends one void point through `deductVoidPoints`, which already early-returns
for a non-editor, so a viewer can walk the reroll without paying for it. It is
offered on **all 18 skill rolls**, being the one Merchant ability that names
no skill. Whether "any roll" should also reach rings, athletics and combat is
not something the rules text settles; every other Merchant ability is a skill
ability, so it is scoped to skills and widening it is a later data change.

---

## Money bonuses

Most of these abilities carry one. They **accumulate into a single percentage
that multiplies the stipend**, applied **after every other stipend modifier** -
applying it before Household Wealth would multiply the wrong base. It appears
as its own `stipend_modifiers` entry, so the existing Money tooltip explains
where it came from, and as a figure on the profession panel.

Two entries contribute nothing: Wk10's money bonus is the literal word "none",
and Wk5 cannot be taken at all.

The rules head the Worker list with "Money bonuses may or may not apply
depending on the campaign". In this campaign they do.
