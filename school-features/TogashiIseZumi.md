# Togashi Ise Zumi

**School ID:** `togashi_ise_zumi`
**Category:** Monk
**School Ring:** Void - Confirmed correct.
**School Knacks:** athletics, conviction, dragon_tattoo - Athletics is rollable (varies by ring used). Conviction is rollable (Water). Dragon_tattoo has special rules.

---

## Special Ability

> Roll either 1 or 3 extra action dice at the beginning of each combat round. If you roll 1 die, it may only be spent on athletics actions; if you roll 3 dice, all of your action dice may only be spent on athletics actions.

**Status:** NOT implemented beyond generic mechanics. This requires combat-round tracking and a choice mechanism for 1 vs 3 extra dice.

**Implementation:** `app/game_data.py:1254-1255` (definition only).

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Implement extra action dice choice (1 or 3) at combat round start
- [ ] UI for selecting 1 or 3 extra action dice
- [ ] Unit tests for action dice mechanic
- [ ] Clicktest for action dice selection

---

## 1st Dan

> Roll one extra die on attack, parry, and athletics rolls.

**Status:** Fully implemented via `SCHOOL_TECHNIQUE_BONUSES`.
- `first_dan_extra_die: ["attack", "parry", "athletics"]`
- Applied in `app/services/dice.py:_apply_school_technique_bonus()`.

**Unit tests:** None specific to Togashi 1st Dan.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest verifying the extra die appears in the roll formula display for attack/parry/athletics

---

## 2nd Dan

> You get a free raise on athletics rolls.

**Status:** Fully implemented.
- `second_dan_free_raise: "athletics"`
- Applied as +5 flat bonus on athletics rolls via `_apply_school_technique_bonus()`.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Unit test: Togashi at 2nd Dan gets +5 flat on athletics formula
- [ ] Clicktest: athletics roll shows the +5 bonus from 2nd Dan

---

## 3rd Dan

> Each day you get 4X free raises which may be applied to athletics rolls, where X is your precepts skill. You may not spend more than X of these free raises on a single roll.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `togashi_daily_athletics_raises: true`, `togashi_daily_raises_max: 4*precepts`, and `togashi_daily_raises_per_roll: precepts`. Client: shows "Spend Athletics Raise (+5)" button after athletics rolls with per-roll cap of X.

**Questions (ANSWERED):**
- "Each day" is the frequency, as stated in the rules text.
- Yes, these raises only apply to athletics rolls.

**Missing:**
- [ ] Unit test: Togashi 3rd Dan daily athletics raises tracking
- [ ] Clicktest: athletics roll at 3rd Dan shows raise spending button

---

## 4th Dan

> Raise the current and maximum rank of any Ring by 1. Raising that Ring now costs 5 fewer XP. You may reroll any contested roll once after seeing the result.

**Status:** Fully implemented.
- Ring raise (+1 Void, cost discount, max increase to 7) is fully implemented via `enforceFourthDanRing()` in the editor and `calculate_ring_xp()` server-side.
- Reroll is now implemented.
  - Server: `app/routes/pages.py` passes `togashi_reroll_contested: true` in school_abilities.
  - Client: shows "Reroll (Togashi 4th Dan)" button after any roll result. Uses the same reroll mechanism as Lucky (saves previous result, compares).

**Questions (ANSWERED):**
- Despite the rules text saying "any Ring", the Togashi should always use Void for their 4th Dan raise (same as their school ring). The standard 4th Dan behavior is correct for this school.

**Unit tests:** None.
**Clicktests:** None.

**Missing:**
- [ ] Clicktest: Togashi 4th Dan reroll button appears after contested rolls

---

## 5th Dan

> At any time, you may spend 1 void point to heal 2 serious wounds.

**Status:** Fully implemented.
- Server: `app/routes/pages.py` passes `togashi_heal_sw: true` in school_abilities config when togashi_ise_zumi and dan >= 5.
- Client: `app/templates/character/sheet.html` shows a "Spend 1 VP to heal 2 SW" button in the tracking section.

