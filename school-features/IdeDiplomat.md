# Ide Diplomat

**School ID:** `ide_diplomat`
**Category:** Court
**School Ring:** "any non-Void" - Player chooses from Air, Fire, Earth, or Water. Confirmed in `SCHOOL_RING_OPTIONS`.
**School Knacks:** double_attack, feint, worldliness - Double_attack is rollable (Fire). Feint is rollable (Air). Worldliness is non-rollable (passive knack, ring=None). Feint knack means school is in `SCHOOLS_WITH_TEMP_VOID`.

---

## Special Ability

> After a feint which met its TN, lower the TN of the target by 10 the next time they are attacked, even if the feint was parried.

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

> Roll one extra die on precepts and any two rolls of your choice.

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

> You get a free raise on any type of roll of your choice.

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

> After seeing the result of any TN or contested skill roll, you may spend a void point to subtract Xk1 from the roll, where X is equal to your tact skill. You know the result of all TN and contested rolls except sincerity and interrogation.

**Status:** NOT implemented. This is a non-standard 3rd Dan that is not encoded in the `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.

**Questions (ANSWERED):**
- X is the tact skill rank (as stated in the rules text).
- "Subtract Xk1 from the roll" means roll Xk1 and subtract that amount from the roll result.
- "You know the result of all TN and contested rolls except sincerity and interrogation" is an information display mechanic.

**Missing:**
- [ ] Implement VP-powered result subtraction mechanic
- [ ] Implement contested result visibility (all except sincerity/interrogation)
- [ ] UI for spending VP to subtract from rolls
- [ ] UI for displaying known contested results

---

## 4th Dan

> Raise your current and maximum in any non-Void Ring by 1. Raising that Ring now costs 5 fewer XP. You regain an extra void point every night.

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

> Gain a temporary void point whenever you spend a void point that was not gained from this technique.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `ide_temp_vp_on_spend: true` in school_abilities.
- Client: `app/templates/character/sheet.html` hooks into `deductVoidPoints()` to auto-grant temp VP when non-temp VP is spent.

**Questions (ANSWERED):**
- "Not gained from this technique" means VP gained from the 5th Dan itself cannot trigger more temp VP. This prevents the infinite loop.
- Normal VP and temp VP from other sources can trigger this.

