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

// ---------------------------------------------------------------------------
// W1 - raise a missing attack roll by 5 per copy
// ---------------------------------------------------------------------------

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
