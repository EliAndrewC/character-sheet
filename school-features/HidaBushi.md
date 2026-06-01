# Hida Bushi

**School ID:** `hida_bushi`
**Category:** Bushi
**School Ring:** Water - Confirmed correct.
**School Knacks:** counterattack, iaijutsu, lunge - All present and rollable.

---

## Special Ability

> You may counterattack as an interrupt action by spending only one action die, but if you do so then the attacker gets a free raise on their attack roll.

**Status:** Out of scope - requires combat-phase tracking (interrupt counterattack costing 1 action die).

**Implementation:** `app/game_data.py` (definition only). No corresponding logic in `dice.py` or templates.

---

## 1st Dan

> Roll one extra die on attack, counterattack, and wound checks.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "counterattack", "wound_check"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()` and `build_wound_check_formula()`.
- Reflected in roll formulas on the View Sheet.

---

## 2nd Dan

> You get a free raise on counterattack rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "counterattack"`
- Applied as +5 flat bonus on counterattack rolls via `_apply_school_technique_bonus()`.

---

## 3rd Dan

> You may re-roll 2X dice on each counterattack roll or X dice on any other type of attack roll, where X is your attack skill.  When impaired, your number of extra dice on these rolls is divided in half (rounded up), but you reroll 10s on these rolls despite being impaired.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `hida_reroll: true` and `hida_reroll_x: attack_skill`. Client: after attack rolls, shows dice selection UI pre-selecting lowest dice <=7. User can toggle selections before confirming reroll. For counterattack: 2X dice. For other attacks: X dice. When impaired: count halved (round up) but 10s rerolled on these dice.

**Questions (ANSWERED):**
- X is the attack skill rank (as with all bushi 3rd Dan techniques).
- "Re-roll dice" means rerolling that many dice and taking the better result.
- "When impaired, divided in half (round up), but reroll 10s despite being impaired" - the impaired state halves the reroll count but restores 10-rerolling on these specific rolls.

---

## 4th Dan

> Raise your current and maximum Water by 1.  Raising your Water now costs 5 fewer XP.  Instead of making a wound check, you may choose to take 2 serious wounds to reduce your light wounds to 0.  You may not do this during the iaijutsu phase of a duel.

**Status:** Fully implemented.
- Ring raise (+1 Water, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- "Trade 2 serious wounds to reset light wounds to 0" is implemented:
  - Server: `app/routes/pages.py` passes `hida_trade_sw: true` in school_abilities.
  - Client: `app/templates/character/sheet.html` shows a "Trade 2 SW to reset LW to 0" button in tracking section.

---

## 5th Dan

> When you counterattack successfully, note the quantity X by which the counterattack roll exceeded its TN.  Add X to your wound check on the damage from the attack you counterattacked.  You may choose to counterattack after seeing the attacker's damage roll, but that roll goes through even if your counterattack impairs or kills the attacker.

**Status:** Partially implemented. The first sentence (banking counterattack excess for wound check bonus) is fully implemented. The second sentence (reactive counterattack after seeing damage) is out of scope - requires combat-phase tracking.

**Implementation:**
- Server: `app/routes/pages.py` passes `hida_counterattack_wc_bonus: true` in school_abilities when dan >= 5.
- Client: `app/templates/character/sheet.html`:
  - `hidaBankedWcBonus` state in both trackingData and diceRoller components.
  - After a successful counterattack roll, the excess over TN is banked automatically.
  - In rollWoundCheck, the banked bonus is applied to formula.flat before rolling (auto-applied, not discretionary).
  - Tracking section shows "Banked Counterattack Bonus" with a Clear button.
  - Persisted via adventureState/saveBankedBonuses; cleared on resetAdventure.

**Not implemented:**
- "You may choose to counterattack after seeing an opponent's damage roll" - requires combat-phase tracking.

---

## Test References

