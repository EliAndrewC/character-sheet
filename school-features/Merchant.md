# Merchant

**School ID:** `merchant`
**Category:** Court
**School Ring:** Water - Confirmed correct.
**School Knacks:** discern_honor, oppose_knowledge, worldliness - Discern_honor is rollable (Air). Oppose_knowledge is rollable (Air). Worldliness is non-rollable (passive knack, ring=None).

---

## Special Ability

> You may spend void points after you see the results of your initial roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `merchant_post_roll_vp: true`. Client: after any non-initiative roll, shows VP spending buttons. Each VP adds +1k1 and the roll is re-executed with the additional dice.

**Implementation:** `app/game_data.py` (definition), `app/routes/pages.py` (merchant_post_roll_vp flag), `app/templates/character/sheet.html` (post-roll VP buttons).

---

## Stipend Bonus

> Rank considered 5.0 higher for stipend (4th Dan technique mentions this).

**Status:** BUG FIXED. Now gated behind 4th Dan (dan >= 4) in `status.py`.
- `app/services/status.py` adds +5 to stipend rank when school is "merchant" or "shosuro_actor".
- The bonus is now correctly gated behind 4th Dan (dan >= 4).

**Implementation:** `app/services/status.py`.

---

## 1st Dan

> Roll one extra die on interrogation, sincerity, and wound check rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["interrogation", "sincerity", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.

---

## 2nd Dan

> You get a free raise on interrogation rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "interrogation"`
- Applied as +5 flat bonus on interrogation rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> Each adventure you get 2X free raises, where X is equal to your sincerity skill, which may be applied to the following rolls: commerce, heraldry, interrogation, sincerity, attack, and wound checks. You may not spend more than X of these free raises on a single roll.

**Status:** STANDARD 3rd Dan - Fully implemented via `third_dan` dict in `SCHOOL_TECHNIQUE_BONUSES`.
- `source_skill: "sincerity"`
- `applicable_to: ["commerce", "heraldry", "interrogation", "sincerity", "attack", "wound_check"]`
- `formula: "2X"`, `max_per_roll: "X"`

**Implementation:** `app/game_data.py` (third_dan dict).

---

## 4th Dan

> Raise your current and maximum Water by 1. Raising your Water now costs 5 fewer XP. Your Rank is considered 5.0 higher for the purpose of calculating your stipend.

**Status:** Fully implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Stipend +5 rank is implemented in `status.py` (see Stipend Bonus section above).
- The stipend bonus is now correctly gated behind 4th Dan (dan >= 4).

**Questions (ANSWERED):**
- Should the stipend +5 be gated behind 4th Dan? **YES.** The stipend bonus is a 4th Dan technique and should only apply at 4th Dan+. This has been fixed.

---

## 5th Dan

> After making any non-initiative roll, you may reroll some of the dice so long as the dice being rerolled add up to at least 5*(X-1) where X is the number of dice being rerolled. You may only do this once per roll. As per your Special Ability, you may spend Void Points before and/or after you make this reroll.

**Status:** Implemented.
- Server gating: `merchant_5th_dan_reroll` flag in `app/routes/pages.py` when `school == "merchant"` and `dan >= 5`.
- Client: `merchant5thStart` / `merchant5thToggle` / `merchant5thConfirm` on the dice roller in `app/templates/character/sheet.html`. Users select dice via the post-roll selection UI; the confirm button is disabled until the selected-sum constraint is satisfied. Delta is displayed as a bullet ("+N from Merchant 5th Dan reroll").
- Interacts with the Merchant Special (post-roll VP spending) in any order; both operate on the same pool and share the `merchant_5th_dan_used` flag for once-per-roll enforcement.
