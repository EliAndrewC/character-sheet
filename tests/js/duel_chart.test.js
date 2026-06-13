"use strict";
// JS unit tests for the iaijutsu-duel focus/strike odds chart math
// (Group F in app/static/js/roll_math.js). Run with:
//     node --test tests/js/*.test.js
const { test } = require("node:test");
const assert = require("node:assert/strict");
const M = require("../../app/static/js/roll_math.js");

// A 1k1 pool with no reroll: P(d10 >= x). survival[x] indexed 0..10.
// survival[0..1] = 1, survival[2] = 0.9, ..., survival[10] = 0.1.
const D10 = [1, 1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1];

const approx = (a, b, eps = 1e-9) =>
  assert.ok(Math.abs(a - b) < eps, `expected ${a} ~= ${b}`);

// --- survivalAt ---

test("survivalAt clamps out-of-range indices", () => {
  assert.equal(M.survivalAt(D10, -3), 1);
  assert.equal(M.survivalAt(D10, 0), 1);
  assert.equal(M.survivalAt(D10, 5), 0.6);
  assert.equal(M.survivalAt(D10, 11), 0); // past the array = impossible
  assert.equal(M.survivalAt(null, 4), 0); // no array = impossible
});

// --- duelDamageAvg ---

test("duelDamageAvg builds the duel pool: weapon + ring + a die per excess", () => {
  const avgs = { "6,2": 12, "9,2": 16.5 };
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  assert.equal(M.duelDamageAvg(dmg, 0, avgs), 12); // 6k2
  assert.equal(M.duelDamageAvg(dmg, 3, avgs), 16.5); // 9k2
});

test("duelDamageAvg caps at 10k10 with rolled overflow becoming kept dice", () => {
  // 4 + 2 + 6 excess = 12 rolled -> capped to 10, kept 2 + 2 overflow = 4.
  const avgs = { "10,4": 30 };
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  assert.equal(M.duelDamageAvg(dmg, 6, avgs), 30);
});

test("duelDamageAvg adds flat bonus and extra rolled/kept dice", () => {
  // 4 + 3 + 1 extra + 0 excess = 8 rolled, 2 + 1 extra kept = 3.
  const avgs = { "8,3": 20 };
  const dmg = {
    weaponRolled: 4, weaponKept: 2, ringVal: 3,
    extraRolled: 1, extraKept: 1, dmgFlat: 5,
  };
  assert.equal(M.duelDamageAvg(dmg, 0, avgs), 25);
});

test("duelDamageAvg negative excess is clamped (a hit never loses dice)", () => {
  const avgs = { "6,2": 12 };
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  assert.equal(M.duelDamageAvg(dmg, -2, avgs), 12);
});

test("duelDamageAvg defaults missing fields and unknown pools to 0", () => {
  assert.equal(M.duelDamageAvg({}, 0, {}), 0);
});

// --- expectedSeriousWounds ---

test("expectedSeriousWounds: zero or negative LW inflicts nothing", () => {
  assert.equal(M.expectedSeriousWounds(D10, 0, 0), 0);
  assert.equal(M.expectedSeriousWounds(D10, 0, -5), 0);
});

test("expectedSeriousWounds matches the wound-check modal's band arithmetic", () => {
  // 1k1 vs LW 15, no flat: bands are keptsum [5,15) -> 1 SW (P = 0.6),
  // [0,5) -> 2 SW (P = 1 - 0.6 = 0.4). Expected = 0.6 + 0.8 = 1.4.
  approx(M.expectedSeriousWounds(D10, 0, 15), 1.4);
});

test("expectedSeriousWounds: flat bonus shifts the target", () => {
  // 1k1 + 5 flat vs LW 15 -> target 10: bands [0,10) -> 1 SW
  // (P = 1 - P(>=10) = 1 - 0.1 = 0.9). Max SW = 2 but the 2-SW band
  // [max(0,-10), 0) is empty. Expected = 0.9.
  approx(M.expectedSeriousWounds(D10, 5, 15), 0.9);
});

test("expectedSeriousWounds: a check that always passes inflicts 0", () => {
  // 1k1 + 20 flat vs LW 10 -> target clamped to 0; every band is empty.
  approx(M.expectedSeriousWounds(D10, 20, 10), 0);
});

test("expectedSeriousWounds: Bayushi halfLw uses the effective-LW bands", () => {
  // LW 20, halfLw -> effLw 10, effTarget 10, target 20, maxSW 2.
  // sw=1 band [0,10): 1 - 0.2 = 0.8, plus the fail-real-but-beat-half
  // band [10,20): P(>=10) - P(>=20) = 0.2 - 0 = 0.2 -> 1.0 total.
  // sw=2 band [max(0,-10), 0) is empty.
  approx(M.expectedSeriousWounds(D10, 0, 20, { halfLw: true }), 1.0);
});

test("expectedSeriousWounds: halfLw with both targets clamped to 0 adds nothing", () => {
  // flat 20 vs LW 10 halved: target and effTarget both clamp to 0, so the
  // fail-real-but-beat-half band is empty too (effTarget < target is false).
  approx(M.expectedSeriousWounds(D10, 20, 10, { halfLw: true }), 0);
});

test("expectedSeriousWounds: dojiWc folds the per-5-over-10 LW bonus into flat", () => {
  // LW 15 -> doji bonus floor((15-10)/5) = 1 -> same as flat 1:
  // target 14: sw=1 band [4,14): 0.7 - 0 = 0.7; sw=2 band [0,4): 1 - 0.7 = 0.3.
  // Expected = 0.7 + 0.6 = 1.3.
  approx(M.expectedSeriousWounds(D10, 0, 15, { dojiWc: true }), 1.3);
});

// --- duelStrikeOutcome ---

test("duelStrikeOutcome: hit chance comes straight off the survival slice", () => {
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  const out = M.duelStrikeOutcome(D10, 0, 5, dmg, { "6,2": 12 });
  approx(out.hit, 0.6); // P(d10 >= 5)
});

test("duelStrikeOutcome: average damage integrates a die per point of excess", () => {
  // d10 vs TN 9: hits on 9 (excess 0 -> 6k2) and 10 (excess 1 -> 7k2),
  // each with probability 0.1 -> conditional weights 0.5 / 0.5.
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  const out = M.duelStrikeOutcome(D10, 0, 9, dmg, { "6,2": 12, "7,2": 14 });
  approx(out.hit, 0.2);
  approx(out.avgDamage, 13);
});

test("duelStrikeOutcome: flat bonus shifts both hit chance and excess", () => {
  // d10 + 4 flat vs TN 9 hits from keptsum 5 (P 0.6); keptsum 9 has
  // excess 4 -> 10k2.
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  const avgs = { "6,2": 12, "7,2": 14, "8,2": 15, "9,2": 16, "10,2": 17, "10,3": 21 };
  const out = M.duelStrikeOutcome(D10, 4, 9, dmg, avgs);
  approx(out.hit, 0.6);
  // keptsum 5..10 -> excess 0..5, each conditional weight 1/6;
  // excess 5 caps 11 rolled -> 10k3.
  approx(out.avgDamage, (12 + 14 + 15 + 16 + 17 + 21) / 6);
});

test("duelStrikeOutcome: impossible TN returns zeros", () => {
  const dmg = { weaponRolled: 4, weaponKept: 2, ringVal: 2, dmgFlat: 0 };
  assert.deepEqual(
    M.duelStrikeOutcome(D10, 0, 50, dmg, {}),
    { hit: 0, avgDamage: 0 }
  );
});

// --- duelOpponentThreat ---

test("duelOpponentThreat: katana 4k2 + Fire-from-kept damage, plus your WC's SW", () => {
  // Opponent pool = d10 (survival D10) vs your TN 9: hits on 9 and 10.
  // Fire 4 -> base damage 8k2; excess 1 -> 9k2.
  // Your WC: D10 slice, no flat, current LW 0.
  // avg damage rounds into the WC LW: 12 -> ESW(12), 14 -> ESW(14).
  const avgs = { "8,2": 12, "9,2": 14 };
  const wc = { survival: D10, flat: 0, halfLw: false, dojiWc: false };
  const out = M.duelOpponentThreat(D10, 9, 4, avgs, wc, 0);
  approx(out.hit, 0.2);
  approx(out.avgDamage, 13);
  // ESW(12): bands [2,12) -> 1 SW: P(>=2)-0 = 0.9; [0,2) -> 2 SW: 0.1 -> 1.1.
  // ESW(14): bands [4,14) -> 1 SW: 0.7; [0,4) -> 2 SW: 0.3 -> 1.3.
  approx(out.avgSw, (1.1 + 1.3) / 2);
});

test("duelOpponentThreat: current light wounds raise the stakes", () => {
  const avgs = { "8,2": 12 };
  const wc = { survival: D10, flat: 0, halfLw: false, dojiWc: false };
  // Only keptsum 10 hits TN 10 -> damage 12 on top of LW 8 -> ESW(20):
  // bands [10,20) -> 1 SW: P(>=10) = 0.1; [0,10) -> 2 SW: 0.9 -> 1.9.
  const out = M.duelOpponentThreat(D10, 10, 4, avgs, wc, 8);
  approx(out.hit, 0.1);
  approx(out.avgDamage, 12);
  approx(out.avgSw, 1.9);
});

test("duelOpponentThreat: impossible TN returns zeros", () => {
  const wc = { survival: D10, flat: 0 };
  assert.deepEqual(
    M.duelOpponentThreat(D10, 50, 4, {}, wc, 0),
    { hit: 0, avgDamage: 0, avgSw: 0 }
  );
});
