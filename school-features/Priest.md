# Priest

**School ID:** `priest`
**Category:** Spellcaster
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** conviction, otherworldliness, pontificate - Conviction is rollable (Water). Otherworldliness is non-rollable (passive knack, ring=None). Pontificate is rollable (Water).

---

## Special Ability

> You have all 10 rituals listed under the Priest profession.

**Status:** NOT implemented beyond generic mechanics. This is a narrative/reference ability that grants access to a set of rituals. The rituals themselves are not encoded in `game_data.py`.

**Implementation:** `app/game_data.py:1564` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Encode the 10 Priest rituals in game data (if needed for the character sheet)
- [ ] Display rituals on the character sheet
- [ ] Determine if rituals need mechanical implementation or are purely narrative

---

## 1st Dan

> Roll an extra die on precepts, one chosen skill, and one combat roll type.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the skill and combat roll type are player-chosen.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- The "chosen skill" and "combat roll type" would need to be stored on the character and applied dynamically.

**Implementation:** `app/game_data.py:2167` (`first_dan_extra_die: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement UI for selecting one skill and one combat roll type for 1st Dan extra die
- [ ] Store chosen selections on the character model
- [ ] Apply precepts + chosen extra dice in roll formula computation
- [ ] Unit test for flexible 1st Dan with chosen skill + combat type
- [ ] Clicktest for 1st Dan selection

---

## 2nd Dan

> Free raise on all Honor bonus rolls (bragging, precepts, open sincerity) for self and allies.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because this is a group buff.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- This affects "Honor bonus rolls" which is a specific category of rolls.

**Implementation:** `app/game_data.py:2168` (`second_dan_free_raise: None`).

**Unit tests:** None.
**Clicktests:** None.

**Questions:**
- What exactly are "Honor bonus rolls"? Are they rolls where Honor provides a bonus (bragging, precepts, open sincerity)?
- Does "for self and allies" mean all characters in the party benefit?
- How does this interact with the sheet - does the Priest's sheet show the bonus, or do allies' sheets also need to reflect it?

**Missing:**
- [ ] Define which rolls count as "Honor bonus rolls"
- [ ] Implement free raise on Honor bonus rolls for the Priest
- [ ] Determine how to handle the ally buff (display only vs mechanical)
- [ ] Unit test for Honor bonus roll identification and free raise
- [ ] Clicktest for Honor bonus roll free raise

---

## 3rd Dan

> Roll X dice (X = precepts skill) at combat start; swap for any rolled die on attack/parry/wound/damage; swap lower dice for allies.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`. It involves pre-rolling a pool of dice at combat start and then swapping them in during the combat.

**Questions:**
- Are the pre-rolled dice visible to the Priest before combat?
- "Swap for any rolled die" means replace one die in a roll with one from the pool?
- "Swap lower dice for allies" means allies can only receive swaps where the pool die is lower than the die being replaced?

**Missing:**
- [ ] Implement pre-roll dice pool at combat start
- [ ] UI for managing the dice pool (showing available dice)
- [ ] UI for swapping dice during rolls
- [ ] Ally swap mechanic with the "lower dice" restriction

---

## 4th Dan

> +1 School Ring; that ring costs 5 fewer XP to raise; free raise for self and allies on contested rolls vs equal or higher skills.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Free raise for self and allies on contested rolls vs equal or higher skills" is NOT implemented. This is a group combat buff.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement contested roll free raise for self and allies
- [ ] Determine how to check "equal or higher skills" condition
- [ ] UI indicator for the group buff

---

## 5th Dan

> Spend Conviction points on allies' rolls; refresh per round; spend to lower action dice for counterattack/parry.

**Status:** NOT implemented. This allows spending Conviction knack points as a resource for allies, with combat-phase utility.

**Questions:**
- Does "Conviction points" refer to the knack rank or a separate resource pool?
- "Refresh per round" means the Conviction points reset each combat round?
- "Lower action dice for counterattack/parry" means the Priest can spend Conviction to reduce an ally's next action die phase?

**Missing:**
- [ ] Implement Conviction point spending mechanic
- [ ] UI for spending Conviction on allies
- [ ] Action dice reduction mechanic
- [ ] Per-round refresh tracking
