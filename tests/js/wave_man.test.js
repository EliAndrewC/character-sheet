/**
 * Wave Man profession roll math (profession-design/design.md, Phase 5).
 *
 * Abilities are numbered W1-W10 in rules order. Every helper takes a COPY
 * COUNT (0, 1 or 2), because an ability may be taken twice and a second
 * copy applies the effect a second time (D4/D5).
 */
const test = require("node:test");
const assert = require("node:assert");
const M = require("../../app/static/js/roll_math.js");

// ---------------------------------------------------------------------------
// W3 - extra weapon damage die below 4 rolled dice
// ---------------------------------------------------------------------------

test("W3: no copies leaves the weapon alone", () => {
  assert.strictEqual(M.waveManWeaponFloor(2, 0), 2);
});

test("W3: a knife (2 dice) gains one die per copy, up to 4", () => {
  assert.strictEqual(M.waveManWeaponFloor(2, 1), 3);
  assert.strictEqual(M.waveManWeaponFloor(2, 2), 4);
});

test("W3: unarmed (0 dice) with two copies reaches only 2", () => {
  assert.strictEqual(M.waveManWeaponFloor(0, 1), 1);
  assert.strictEqual(M.waveManWeaponFloor(0, 2), 2);
});

test("W3: a spear (3 dice) caps at 4, wasting the second copy", () => {
  assert.strictEqual(M.waveManWeaponFloor(3, 1), 4);
  assert.strictEqual(M.waveManWeaponFloor(3, 2), 4);
});

test("W3: a katana (4 dice) gains nothing at any copy count", () => {
  assert.strictEqual(M.waveManWeaponFloor(4, 1), 4);
  assert.strictEqual(M.waveManWeaponFloor(4, 2), 4);
});

test("W3: a weapon already above 4 dice is never reduced", () => {
  assert.strictEqual(M.waveManWeaponFloor(6, 2), 6);
});

test("W3: keys on dice ROLLED only - kept dice are irrelevant", () => {
  // The rules were reworded on 2026-08-29 from "less than 4k2" to
  // "rolls fewer than 4 damage dice", so there is no kept-dice argument.
  assert.strictEqual(M.waveManWeaponFloor.length, 2);
});

test("W3: junk input degrades to no change", () => {
  assert.strictEqual(M.waveManWeaponFloor(null, 1), 1);
  assert.strictEqual(M.waveManWeaponFloor(2, null), 2);
});

// ---------------------------------------------------------------------------
// W4 - round damage up to the nearest multiple of 5 (+3 if already a multiple)
// ---------------------------------------------------------------------------

test("W4: no copies leaves the total alone", () => {
  assert.strictEqual(M.waveManRoundDamage(14, 0), 14);
});

test("W4: rounds up to the next multiple of 5", () => {
  assert.strictEqual(M.waveManRoundDamage(1, 1), 5);
  assert.strictEqual(M.waveManRoundDamage(3, 1), 5);
  assert.strictEqual(M.waveManRoundDamage(4, 1), 5);
  assert.strictEqual(M.waveManRoundDamage(14, 1), 15);
  assert.strictEqual(M.waveManRoundDamage(16, 1), 20);
});

test("W4: a total already on a multiple of 5 rises by 3, not to the next 5", () => {
  assert.strictEqual(M.waveManRoundDamage(5, 1), 8);
  assert.strictEqual(M.waveManRoundDamage(15, 1), 18);
  assert.strictEqual(M.waveManRoundDamage(20, 1), 23);
  assert.strictEqual(M.waveManRoundDamage(0, 1), 3);
});

test("W4: two copies chain the step", () => {
  // 14 -> 15 -> 18, NOT 14 -> 20.
  assert.strictEqual(M.waveManRoundDamage(14, 2), 18);
  // 15 -> 18 -> 20.
  assert.strictEqual(M.waveManRoundDamage(15, 2), 20);
  assert.strictEqual(M.waveManRoundDamage(3, 2), 8);
});

test("W4: large totals round the same way", () => {
  assert.strictEqual(M.waveManRoundDamage(97, 1), 100);
  assert.strictEqual(M.waveManRoundDamage(100, 2), 105);
});

test("W4: junk input degrades safely", () => {
  assert.strictEqual(M.waveManRoundDamage(null, 1), 3);
  assert.strictEqual(M.waveManRoundDamage(12, null), 12);
});

// ---------------------------------------------------------------------------
// W1 - raise a missing attack roll by 5 per copy
// ---------------------------------------------------------------------------

test("W1: a roll that already hits consumes no raises", () => {
  const r = M.waveManMissRaise(30, 25, 2);
  assert.strictEqual(r.total, 30);
  assert.strictEqual(r.raisesUsed, 0);
  assert.strictEqual(r.hit, true);
});

test("W1: one copy raises a near miss into a hit", () => {
  const r = M.waveManMissRaise(22, 25, 1);
  assert.strictEqual(r.total, 27);
  assert.strictEqual(r.raisesUsed, 1);
  assert.strictEqual(r.hit, true);
});

test("W1: one copy is not enough for a miss by 8", () => {
  const r = M.waveManMissRaise(17, 25, 1);
  assert.strictEqual(r.total, 22);
  assert.strictEqual(r.raisesUsed, 1);
  assert.strictEqual(r.hit, false);
});

test("W1: two copies turn a miss by 8 into a hit", () => {
  const r = M.waveManMissRaise(17, 25, 2);
  assert.strictEqual(r.total, 27);
  assert.strictEqual(r.raisesUsed, 2);
  assert.strictEqual(r.hit, true);
});

test("W1: applies only the minimum number of raises needed (D10)", () => {
  // Missing by 3 with two copies spends ONE raise, not two.
  const r = M.waveManMissRaise(22, 25, 2);
  assert.strictEqual(r.total, 27);
  assert.strictEqual(r.raisesUsed, 1);
});

test("W1: no copies means no raise", () => {
  const r = M.waveManMissRaise(17, 25, 0);
  assert.strictEqual(r.total, 17);
  assert.strictEqual(r.raisesUsed, 0);
  assert.strictEqual(r.hit, false);
});

test("W1: a raised hit yields no excess damage dice (D11)", () => {
  // Raised to 27 against TN 25, but the excess used for damage dice is
  // computed from the UNRAISED total, which missed - so zero.
  assert.strictEqual(M.waveManExcessForDamage(17, 25, 2), 0);
  assert.strictEqual(M.waveManExcessForDamage(22, 25, 1), 0);
});

test("W1: a roll that hits on its own keeps its excess normally", () => {
  // 37 vs TN 25 is 12 over: two full multiples of 5.
  assert.strictEqual(M.waveManExcessForDamage(37, 25, 2), 12);
});

test("W1: exactly on the TN without a raise has zero excess", () => {
  assert.strictEqual(M.waveManExcessForDamage(25, 25, 2), 0);
});

// ---------------------------------------------------------------------------
// W9 - recover damage dice a failed parry took away
// ---------------------------------------------------------------------------

test("W9: recovers 2 dice per copy", () => {
  assert.strictEqual(M.waveManFailedParryDice(5, 1), 2);
  assert.strictEqual(M.waveManFailedParryDice(5, 2), 4);
});

test("W9: never recovers more dice than the parry removed", () => {
  // Defender's parry skill 3 removed 3 dice; two copies would want 4.
  assert.strictEqual(M.waveManFailedParryDice(3, 2), 3);
  assert.strictEqual(M.waveManFailedParryDice(1, 2), 1);
});

test("W9: no copies recovers nothing", () => {
  assert.strictEqual(M.waveManFailedParryDice(5, 0), 0);
});

test("W9: junk input recovers nothing", () => {
  assert.strictEqual(M.waveManFailedParryDice(null, 2), 0);
  assert.strictEqual(M.waveManFailedParryDice(-2, 2), 0);
});

// ---------------------------------------------------------------------------
// W5 - reroll 10s on one die per copy while impaired
// ---------------------------------------------------------------------------

test("W5: impaired still suppresses the roll's own 10s reroll", () => {
  // The ability frees specific dice; it does not clear the suppression,
  // which is what the Hida 3rd Dan technique does instead.
  assert.strictEqual(
    M.impairedSuppressesReroll("skill:etiquette", {}, { waveManTenDice: 2 }),
    true
  );
});

test("W5: frees one die per copy", () => {
  assert.strictEqual(M.waveManFreedDice(0), 0);
  assert.strictEqual(M.waveManFreedDice(1), 1);
  assert.strictEqual(M.waveManFreedDice(2), 2);
});

test("W5: explodes only the allotted number of 10s", () => {
  const dice = [{ value: 10 }, { value: 10 }, { value: 4 }];
  const rerolls = [{ value: 7, parts: [7] }, { value: 3, parts: [3] }];
  const out = M.waveManExplodeTens(dice, rerolls, 2, 1);
  // Only the first 10 explodes: 17. The second stays a bare 10.
  assert.deepStrictEqual(out.dice.map((d) => d.value), [17, 10, 4]);
  assert.strictEqual(out.keptSum, 27);
});

test("W5: two copies explode two 10s", () => {
  const dice = [{ value: 10 }, { value: 10 }, { value: 4 }];
  const rerolls = [{ value: 7, parts: [7] }, { value: 3, parts: [3] }];
  const out = M.waveManExplodeTens(dice, rerolls, 2, 2);
  assert.deepStrictEqual(out.dice.map((d) => d.value), [17, 13, 4]);
  assert.strictEqual(out.keptSum, 30);
});

test("W5: the freed die chains - a rerolled 10 rerolls again (D13)", () => {
  const dice = [{ value: 10 }, { value: 2 }];
  // The chain 10 -> 10 -> 4 arrives as one reroll with parts [10, 4].
  const rerolls = [{ value: 14, parts: [10, 4] }];
  const out = M.waveManExplodeTens(dice, rerolls, 1, 1);
  assert.strictEqual(out.dice[0].value, 24);
  assert.deepStrictEqual(out.dice[0].parts, [10, 10, 4]);
});

test("W5: no allotment leaves every die untouched", () => {
  const dice = [{ value: 10 }, { value: 4 }];
  const out = M.waveManExplodeTens(dice, [{ value: 7, parts: [7] }], 1, 0);
  assert.deepStrictEqual(out.dice.map((d) => d.value), [10, 4]);
});

test("W5: a roll with no 10s is unchanged", () => {
  const dice = [{ value: 6 }, { value: 4 }];
  const out = M.waveManExplodeTens(dice, [], 1, 2);
  assert.deepStrictEqual(out.dice.map((d) => d.value), [6, 4]);
  assert.strictEqual(out.keptSum, 6);
});
