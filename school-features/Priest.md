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

> Roll one extra die on precepts, any one skill, and any one type of combat roll.

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

> You and your allies get a free raise on all rolls for which you receive an Honor bonus (bragging, precepts, and open sincerity).

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because this is a group buff.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- "Honor bonus rolls" are: bragging (gets +2*Honor), precepts (gets +2*Honor), and open sincerity (non-contested sincerity, gets +2*Honor). Contested sincerity (lying, rolled vs interrogation) does NOT qualify.

**Implementation:** `app/game_data.py:2168` (`second_dan_free_raise: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement free raise on Honor bonus rolls (bragging, precepts, open sincerity) for the Priest and allies
- [ ] Determine how to handle the ally buff (display only vs mechanical)
- [ ] Unit test for Honor bonus roll identification and free raise
- [ ] Clicktest for Honor bonus roll free raise

---

## 3rd Dan

> Roll X dice at the beginning of combat, where X is equal to your precepts skill. You may swap any of these dice for any rolled die on any attack, parry, wound check, or damage roll. You may swap any of these dice for any lower die on any of those types of rolls made by any ally.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`. It involves pre-rolling a pool of dice at combat start and then swapping them in during the combat.

**Missing:**
- [ ] Implement pre-roll dice pool at combat start
- [ ] UI for managing the dice pool (showing available dice)
- [ ] UI for swapping dice during rolls
- [ ] Ally swap mechanic with the "lower dice" restriction

---

## 4th Dan

> Raise your current and maximum of your School's chosen Ring by 1. Raising that Ring now costs 5 fewer XP. You and your allies get a free raise on all contested rolls for which your opponent has an equal or higher skill rank.

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

> You may spend the points from your Conviction knack on your allies' rolls, and your Conviction points refresh after each conversation and combat round. You may also spend these points to lower action dice in order for you or an ally to counterattack or parry.

**Status:** NOT implemented. This allows spending Conviction knack points as a resource for allies, with combat-phase utility.

**Missing:**
- [ ] Implement Conviction point spending mechanic
- [ ] UI for spending Conviction on allies
- [ ] Action dice reduction mechanic
- [ ] Per-round refresh tracking
