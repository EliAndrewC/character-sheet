# Wave Man abilities

**Profession ID:** `wave_man`
**Rules:** `rules/09-professions.md#wave-man-abilities`
**Design + implementation checklists:** `profession-design/design.md` (the
original build), then `profession-design/priest-and-pooling.md` (which made
"Profession" the character type and pooled the abilities).

Not a school. A **Profession** character is a ronin who takes a profession
*instead of* a school, which makes them the only character shape in this app
with no school at all - no School Ring, no school knacks, and Dan 0. They draw
abilities from every available profession and mix them freely, so "Wave Man"
below names a *group of abilities*, not a kind of character.

Wave Man and Priest abilities are available. Worker and Merchant are carried
as data and shown greyed out so players can see what is coming; Ninja
abilities are hidden entirely until the separate unlock feature exists.

Everything here that is not in the upstream rules file is a GM ruling recorded
during design; the rules text itself says only what the ten abilities do.

---

## How a Wave Man is built

**Selection.** A character's type is plain **Profession** - not "Wave Man".
Since 2026-08-29 a profession character draws abilities from *every available
profession* and mixes them freely (see `profession-design/priest-and-pooling.md`),
so "Wave Man" now names a group of abilities rather than a kind of character.
The dropdown value is `profession`, split by `split_school_or_profession` in
`app/services/professions.py`, which is also the allow-list.

**Abilities cost nothing.** They unlock on the **total XP the character
holds** - `starting_xp + earned_xp`, whether or not it has been spent. The
first arrives at 150 XP and one more every 15 XP after that. The allowance is
pooled across every available profession; the Wave Man list alone supplies 20
picks (ten abilities, each takeable twice) and runs out at 435 XP, so a
character who reaches 450 has a pick they can only spend by branching out.

**Each Wave Man ability may be taken twice**, and a second copy applies its
effect a second time. This is why `Character.profession_abilities` is an
id-to-count map rather than a list of ids, and why the editor uses steppers
rather than checkboxes. The limit follows the ability's *own* profession, so a
twice-taken Wave Man ability can sit beside a once-only Priest ritual in the
same character.

**No School Ring, no school knacks, no Dan.** All five rings start at 2 and
cap at 5. **Foreign school knacks stay available**, though: with no school of
their own, every knack in the game is "foreign" to a Wave Man, and they buy
them under the ordinary 10-XP-for-0-to-1 rule. That matters more than it
sounds - it is how a Wave Man reaches counterattack, double attack, lunge and
iaijutsu, which in turn is why W1's scope question below has teeth.

**Over-allowance is an error, not a silent truncation.** The write-path
sanitizer clamps per-ability counts and drops foreign ids, but it does *not*
enforce the XP allowance. A player who somehow loses XP sees a validation
error explaining it rather than finding picks quietly deleted. Under-spending
is a soft warning that never blocks publishing.

---

## The ten abilities

Numbered W1-W10 in rules order; that numbering is used in code comments, test
names and the design doc. **W3's text was reworded upstream on 2026-08-29**
from "less than 4k2 damage" to "rolls fewer than 4 damage dice" - the
implementation keys on dice rolled and ignores dice kept.

| id | ability | status |
|---|---|---|
| W1 | Raise a missing attack roll by 5 | Implemented (clause 2 is reference text) |
| W2 | Raise the parry TN against your attacks by 5 | Reference text |
| W3 | Extra weapon damage die below 4 rolled dice | Implemented; armor clause deferred |
| W4 | Round damage up to the next multiple of 5 | Implemented |
| W5 | Reroll 10s on a single die while impaired | Implemented |
| W6 | One extra unkept initiative die | Implemented |
| W7 | Two extra unkept wound-check dice | Implemented |
| W8 | Subtract 5 from damage keeping an extra die | Reference text |
| W9 | Recover 2 damage dice a failed parry removed | Implemented |
| W10 | Raise the wound-check TN from your damage by 5 | Reference text |

### Why four of them are reference text

W2, W8, W10 and W1's second clause all change what an **opponent** rolls, and
this app models one character's own rolls. Rather than invent an opponent
model, the sheet renders them as rules text with the numbers filled in for the
copy count held, so the player can tell the GM. W8 sits closest to the line -
it reduces the Wave Man's own light wounds - and was still left as reference
text by GM decision rather than becoming a wound-check toggle.

### W1: the scope question

"An attack roll" here means **every attack type including the iaijutsu
strike**. That is deliberately wider than `ATTACK_TYPE_KEYS` in
`services/dice.py`, which excludes iaijutsu so that a duel's strike keeps its
own rules for every school. Widening that set would have changed behaviour for
every school, so the Wave Man gets its own predicate,
`is_wave_man_attack_key`. If you touch attack scoping, note that these two
sets disagree **on purpose**.

Two clauses that are easy to get backwards:

- **Raises stop as soon as the roll lands.** A character with two copies whose
  roll missed by 3 spends one raise, not two.
- **The raise earns no damage dice.** Extra damage dice for exceeding the TN
  are computed from the *unraised* total, so an attack that only hit because
  of a raise yields none. An attack that hit on its own is unaffected.

And the second clause, which is reference text: the defender's parry
automatically succeeds, **but is still rolled**. That distinction matters -
the Shiba Bushi 5th Dan technique keys off the size of a successful parry
roll, so skipping the roll would quietly break it.

### W5: the trap, and why there is no picker

Impaired suppresses the 10s reroll; W5 frees **one die per copy** from that
suppression. It does *not* clear the suppression the way Hida Bushi's 3rd Dan
technique does - the roll's other 10s stay put.

The freed die is **selected automatically**. Every 10 is interchangeable at
reroll time, so there is nothing for a player to choose, which is why no
dice-picker UI exists here even though the Hida 3rd Dan flow needs one. The
freed die still **chains**: a rerolled 10 rerolls again. That is exactly why
the rule frees a *die* rather than a *ten*.

Scope follows the PCP rule's exclusions: anywhere 10s could ever reroll, so
not initiative and not the iaijutsu strike. The implementation gets this for
free by keying on `no_reroll_reason == "impaired"` rather than on
`reroll_tens` - which also means it cannot resurrect a reroll blocked for some
other reason, such as an unskilled roll. There is a regression test for
exactly that. W5 and a PCP's impaired reroll may both apply to one roll.

**The bot applies W5 too**, which is a deliberate departure from the original
plan. The plan had assumed W5 was an interactive choice a slash command could
not make; the GM's later ruling that the die is auto-selected removed the
interaction. Skipping it would have made the same roll come out differently on
the sheet than through `/etiquette`, which is the exact failure mode the
shared-formula rule exists to prevent.

### W4: ordering

Rounding is applied **last**, after the extra dice for exceeding the TN, after
W3 and after W9. Rounding an intermediate value gives a different and higher
answer. Note the edge that looks like a bug and is not: 15 becomes 18, not 20,
because a total already on a multiple of 5 rises by 3.

---

## Deferred and out of scope

- **W3's armor clause** ("subtract 2 from your armor damage reduction
  penalty") is not implemented, because **there are no armor rules anywhere in
  `rules/`** - the only occurrence of the word "armor" in the whole rules
  directory is inside this ability. Blocked on upstream rules, not on effort.
- **The other four professions.** Their ability text is carried in
  `PROFESSIONS` so the editor can list them honestly, and adding one is a data
  change plus its mechanics rather than a refactor. They are `selectable=False`
  until then, and validation rejects them if one is forced through a POST.
