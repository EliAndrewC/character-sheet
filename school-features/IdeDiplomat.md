# Ide Diplomat

**School ID:** `ide_diplomat`
**Category:** Court
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** double_attack, feint, worldliness - Double_attack is rollable (Fire). Feint is rollable (Air). Worldliness is non-rollable (passive knack, ring=None). Feint knack means school is in `SCHOOLS_WITH_TEMP_VOID`.

---

## Special Ability

> After a feint which met its TN, lower the TN of the target by 10 the next time they are attacked.

**Status:** NOT implemented beyond generic mechanics. This requires tracking the feint result and applying a TN debuff to the target for the next attack.

**Implementation:** `app/game_data.py:1421-1423` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement post-feint TN reduction (-10) on target
- [ ] Track the debuff state until next attack against that target
- [ ] UI for displaying active TN debuff

---

## 1st Dan

> Roll an extra die on precepts and two chosen roll types.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the two roll types are player-chosen.
- `first_dan_extra_die: None` in `SCHOOL_TECHNIQUE_BONUSES`.
- The "chosen roll types" would need to be stored on the character and applied dynamically.

**Implementation:** `app/game_data.py:2114` (`first_dan_extra_die: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement UI for selecting two roll types for 1st Dan extra die
- [ ] Store chosen roll types on the character model
- [ ] Apply chosen extra die in roll formula computation
- [ ] Unit test for flexible 1st Dan with chosen skills
- [ ] Clicktest for 1st Dan skill selection

---

## 2nd Dan

> Free raise on any chosen roll type.

**Status:** NOT implementable via generic `SCHOOL_TECHNIQUE_BONUSES` because the roll type is player-chosen.
- `second_dan_free_raise: None` in `SCHOOL_TECHNIQUE_BONUSES`.

**Implementation:** `app/game_data.py:2115` (`second_dan_free_raise: None`).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement UI for selecting roll type for 2nd Dan free raise
- [ ] Store chosen roll type on the character model
- [ ] Apply chosen free raise in roll formula computation
- [ ] Unit test for flexible 2nd Dan with chosen skill
- [ ] Clicktest for 2nd Dan skill selection

---

## 3rd Dan

> After any roll, spend a void point to subtract Xk1; know all contested results except sincerity/interrogation.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions:**
- What is X here? Presumably a skill rank.
- "Subtract Xk1" means roll Xk1 and subtract from the opponent's result?
- "Know all contested results except sincerity/interrogation" - is this an information-display mechanic?

**Missing:**
- [ ] Implement VP-powered result subtraction mechanic
- [ ] Implement contested result visibility (all except sincerity/interrogation)
- [ ] UI for spending VP to subtract from rolls
- [ ] UI for displaying known contested results

---

## 4th Dan

> +1 to a non-Void ring; that ring costs 5 fewer XP to raise; regain an extra void point nightly.

**Status:** Partially implemented.
- Ring raise (+1 to the chosen non-Void ring, cost discount, max increase to 7) is fully implemented. Since the school ring is "any non-Void", the 4th Dan ring raise applies to the chosen school ring.
- "Regain an extra void point nightly" is NOT implemented. This would modify the VP regeneration display on the character sheet.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement +1 VP nightly regeneration display
- [ ] Unit test for extra VP regen at 4th Dan
- [ ] Clicktest for VP regen display

---

## 5th Dan

> Gain a temporary void point whenever spending non-technique void points.

**Status:** NOT implemented. This reactive ability grants temp VP whenever the Ide spends normal VP (not technique-specific VP). The school is in `SCHOOLS_WITH_TEMP_VOID` (via the "temporary void" text in the technique).

**Questions:**
- Does "non-technique" mean VP spent on generic +1k1 bonuses, as opposed to VP spent via school techniques?
- Does this create an infinite loop concern (spend VP -> gain temp VP -> spend temp VP -> gain temp VP)?

**Missing:**
- [ ] Implement auto-grant temp VP when spending non-technique VP
- [ ] Clarify the loop prevention rule
- [ ] UI for temp VP auto-grant
