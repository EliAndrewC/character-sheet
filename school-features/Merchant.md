# Merchant

**School ID:** `merchant`
**Category:** Court
**School Ring:** Water - Confirmed correct.
**School Knacks:** discern_honor, oppose_knowledge, worldliness - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> You may spend void points after you see the results of your initial roll.

**Status:** NOT implemented. Normally, void points must be declared before rolling. This ability allows the Merchant to see the roll result first and then decide to spend VP. This would require modifying the roll UI to add a post-roll VP spending step.

**Implementation:** `app/game_data.py:1448` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement post-roll VP spending option for Merchant
- [ ] Modify the dice roller UI to allow VP spending after seeing results
- [ ] Unit test for post-roll VP mechanic
- [ ] Clicktest: Merchant can spend VP after seeing roll results

---

## Stipend Bonus

> Rank considered 5.0 higher for stipend (4th Dan technique mentions this).

**Status:** Fully implemented.
- `app/services/status.py:63-69` adds +5 to stipend rank when school is "merchant" or "shosuro_actor".
- The bonus is unconditional (not gated by Dan level in the current implementation).

**Implementation:** `app/services/status.py:63-69`.

**Unit tests:**
- `test_effective_status.py:185` - `test_merchant_school_stipend` verifies stipend calculation
- `test_effective_status.py:169` - `test_household_wealth_with_merchant` verifies interaction with Household Wealth
- `test_effective_status.py:210` - additional stipend test with Merchant

**Clicktests:**
- `test_sheet_advanced.py:34` - `test_stipend_with_merchant_school` e2e test

---

## 1st Dan

> Roll one extra die on interrogation, sincerity, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["interrogation", "sincerity", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Merchant 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for interrogation/sincerity/wound_check

---

## 2nd Dan

> You get a free raise on interrogation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "interrogation"`
- Applied as +5 flat bonus on interrogation rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Merchant at 2nd Dan gets +5 flat on interrogation formula
- [ ] Clicktest: interrogation roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your sincerity skill, which may be applied to the following rolls: commerce, heraldry, interrogation, sincerity, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "sincerity"`
- `applicable_to: ["commerce", "heraldry", "interrogation", "sincerity", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py:2121-2129` (third_dan dict).

**Unit tests:** None specific to Merchant 3rd Dan. The mechanism is identical to other standard 3rd Dan schools.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest for Merchant-specific 3rd Dan applicable skills

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. Your Rank is considered 5.0 higher for the purpose of calculating your stipend.

**Status:** Fully implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Stipend +5 rank is implemented in `status.py:63-69` (see Stipend Bonus section above).
- Note: The stipend bonus is currently applied unconditionally regardless of Dan level.

**Unit tests:**
- `test_effective_status.py:185` - tests stipend with Merchant school

**Clicktests:**
- `test_sheet_advanced.py:34` - tests stipend display with Merchant school

**Questions (ANSWERED):**
- Should the stipend +5 be gated behind 4th Dan? **YES.** The stipend bonus is a 4th Dan technique and should only apply at 4th Dan+. The current implementation is a bug.

**Missing:**
- [ ] **BUG:** Gate the stipend +5 behind 4th Dan (dan >= 4 check in `status.py`)

---

## 5th Dan

> After making any non-initiative roll, you may reroll some of the dice so long as the dice being rerolled add up to at least 5*(X-1) where X is the number of dice being rerolled. You may only do this once per roll. As per your Special Ability, you may spend Void Points before and/or after you make this reroll.

**Status:** NOT implemented. This is a complex reroll mechanic that interacts with the VP spending special ability.

**Missing:**
- [ ] Implement the reroll mechanic
- [ ] UI for selecting dice to reroll based on the value constraint
- [ ] Integration with post-roll VP spending
