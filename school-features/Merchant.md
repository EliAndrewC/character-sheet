# Merchant

**School ID:** `merchant`
**Category:** Court
**School Ring:** Water - Confirmed correct.
**School Knacks:** discern_honor, oppose_knowledge, worldliness - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> Spend void points after your initial roll.

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

> Roll an extra die on interrogation, sincerity, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["interrogation", "sincerity", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

**Unit tests:** None specific to Merchant 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for interrogation/sincerity/wound_check

---

## 2nd Dan

> Free raise on interrogation rolls.

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

> Gain 2X free raises per adventure (X = sincerity skill); apply to commerce, heraldry, interrogation, sincerity, attack, wound checks; max X per roll.

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

> +1 Water; Water ring costs 5 fewer XP to raise; Rank considered 5.0 higher for stipend.

**Status:** Fully implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Stipend +5 rank is implemented in `status.py:63-69` (see Stipend Bonus section above).
- Note: The stipend bonus is currently applied unconditionally regardless of Dan level.

**Unit tests:**
- `test_effective_status.py:185` - tests stipend with Merchant school

**Clicktests:**
- `test_sheet_advanced.py:34` - tests stipend display with Merchant school

**Questions:**
- Should the stipend +5 be gated behind 4th Dan? Currently it applies at all Dan levels.

**Missing:**
- [ ] Verify whether stipend bonus should be Dan-gated; if so, add Dan check to `status.py`

---

## 5th Dan

> After any non-initiative roll, reroll dice totaling 5*(X-1) where X is the number rerolled; spend void before or after.

**Status:** NOT implemented. This is a complex reroll mechanic that interacts with the VP spending special ability.

**Questions:**
- Does "dice totaling 5*(X-1)" mean the sum of the dice being rerolled must equal 5*(X-1)?
- "Spend void before or after" - does this stack with the special ability to spend VP after rolling?
- How many dice can be rerolled per roll?

**Missing:**
- [ ] Implement the reroll mechanic
- [ ] UI for selecting dice to reroll based on the value constraint
- [ ] Integration with post-roll VP spending
