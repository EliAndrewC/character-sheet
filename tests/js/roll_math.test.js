"use strict";
// JS unit tests for the pure roll-math helpers (app/static/js/roll_math.js).
// Run with Node's built-in test runner - no npm install, no framework, ~0.2s:
//     node --test tests/js/
//     node --test --experimental-test-coverage tests/js/   # must be 100% on roll_math.js
//
// Every function + every branch is exercised here so the formula correctness is
// pinned in milliseconds instead of only through the slow browser clicktests.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const M = require("../../app/static/js/roll_math.js");

test("clampNonNegative", () => {
  assert.equal(M.clampNonNegative(5), 5);
  assert.equal(M.clampNonNegative(-3), 0);
  assert.equal(M.clampNonNegative(0), 0);
});

// --- Group A: wound checks ---

test("woundCheckEffectiveLw halves (round down) only under Bayushi 5th Dan", () => {
  assert.equal(M.woundCheckEffectiveLw(21, false), 21);
  assert.equal(M.woundCheckEffectiveLw(21, true), 10); // floor(21/2)
});

test("woundCheckResult: pass when rollTotal >= lightWounds", () => {
  assert.deepEqual(M.woundCheckResult(30, 20, false), {
    passed: true, margin: 10, seriousWounds: 0,
  });
  assert.deepEqual(M.woundCheckResult(20, 20, false), {
    passed: true, margin: 0, seriousWounds: 0,
  });
});

test("woundCheckResult: fail -> margin and floor(margin/10)+1 serious wounds", () => {
  // 35 LW, rolled 12 -> margin 23 -> floor(23/10)+1 = 3 SW.
  assert.deepEqual(M.woundCheckResult(12, 35, false), {
    passed: false, margin: 23, seriousWounds: 3,
  });
});

test("woundCheckResult: Bayushi half-LW path (and margin clamps at 0)", () => {
  // 20 LW halved -> effLw 10; rolled 15 < 20 so it's a 'fail', but 15 > 10
  // effective -> margin clamps to 0, still 1 serious wound (floor(0/10)+1).
  assert.deepEqual(M.woundCheckResult(15, 20, true), {
    passed: false, margin: 0, seriousWounds: 1,
  });
  // 40 LW halved -> 20; rolled 8 -> margin 12 -> 2 SW.
  assert.deepEqual(M.woundCheckResult(8, 40, true), {
    passed: false, margin: 12, seriousWounds: 2,
  });
});

test("woundCheckMaxSeriousWounds = floor(lw/10)+1", () => {
  assert.equal(M.woundCheckMaxSeriousWounds(9), 1);
  assert.equal(M.woundCheckMaxSeriousWounds(25), 3);
});

// --- Group B: attack / contest ---

test("attackEffectiveTn: +20 for double attack", () => {
  assert.equal(M.attackEffectiveTn(25, false), 25);
  assert.equal(M.attackEffectiveTn(25, true), 45);
});

test("excessToExtraDice: floor(excess/5), 0 when non-positive", () => {
  assert.equal(M.excessToExtraDice(12), 2);
  assert.equal(M.excessToExtraDice(5), 1);
  assert.equal(M.excessToExtraDice(0), 0);
  assert.equal(M.excessToExtraDice(-8), 0);
});

test("bonusPer5Over10 = max(0, floor((v-10)/5))", () => {
  assert.equal(M.bonusPer5Over10(25), 3);
  assert.equal(M.bonusPer5Over10(10), 0);
  assert.equal(M.bonusPer5Over10(14), 0);
  assert.equal(M.bonusPer5Over10(8), 0); // floor(-2/5) = -1 -> clamped
});

test("parrySkillFromTn = max(1, floor((tn-5)/step))", () => {
  assert.equal(M.parrySkillFromTn(45, 5), 8);
  assert.equal(M.parrySkillFromTn(45, 10), 4); // athletics step
  assert.equal(M.parrySkillFromTn(5, 5), 1); // floor(0) -> min 1
});

test("attackSpecBonus = 10 * count", () => {
  assert.equal(M.attackSpecBonus(0), 0);
  assert.equal(M.attackSpecBonus(3), 30);
});

test("freeRaisesFromResult = floor(result/5)", () => {
  assert.equal(M.freeRaisesFromResult(27), 5);
  assert.equal(M.freeRaisesFromResult(4), 0);
});

// --- Group C: damage / dice cap ---

test("applyDiceCap: no overflow leaves values untouched", () => {
  assert.deepEqual(M.applyDiceCap(8, 4, 0), {
    rolled: 8, kept: 4, flat: 0, overflowFlat: 0,
  });
});

test("applyDiceCap: rolled>10 converts to kept", () => {
  // 13 rolled -> 10 rolled, kept += 3.
  assert.deepEqual(M.applyDiceCap(13, 4, 0), {
    rolled: 10, kept: 7, flat: 0, overflowFlat: 0,
  });
});

test("applyDiceCap: kept>10 converts to +2 flat each", () => {
  // 16 rolled -> 10r, kept 6+6=12 -> 10k, overflow 2*(12-10)=4 flat.
  assert.deepEqual(M.applyDiceCap(16, 6, 1), {
    rolled: 10, kept: 10, flat: 5, overflowFlat: 4,
  });
  // kept>10 directly (no rolled overflow).
  assert.deepEqual(M.applyDiceCap(8, 13, 0), {
    rolled: 8, kept: 10, flat: 6, overflowFlat: 6,
  });
});

test("damageDiceContestAdjust: round toward zero on both signs", () => {
  assert.equal(M.damageDiceContestAdjust(12), 2);
  assert.equal(M.damageDiceContestAdjust(0), 0);
  assert.equal(M.damageDiceContestAdjust(-12), -2); // -floor(12/5) = -2, not -3
  assert.equal(M.damageDiceContestAdjust(-4), 0);
});

test("failedParryDiceReduction: full / half / none", () => {
  assert.equal(M.failedParryDiceReduction(8, 3, "full"), 5);
  assert.equal(M.failedParryDiceReduction(8, 5, "half"), 6); // 8 - floor(5/2)=2
  assert.equal(M.failedParryDiceReduction(8, 99, "none"), 8); // unchanged
  assert.equal(M.failedParryDiceReduction(2, 5, "full"), 0); // clamps at 0
});

test("tradeDiceFloor = max(2, rolled - tradeDice)", () => {
  assert.equal(M.tradeDiceFloor(12, 10), 2);
  assert.equal(M.tradeDiceFloor(8, 3), 5);
  assert.equal(M.tradeDiceFloor(5, 10), 2); // floor at 2
});

// --- Group D: per-school ---

test("shinjoPhasesHeld / shinjoPhaseBonus", () => {
  assert.equal(M.shinjoPhasesHeld(9, 4), 5);
  assert.equal(M.shinjoPhasesHeld(3, 4), 0); // clamps
  assert.equal(M.shinjoPhaseBonus(9, 4), 10); // 2 * 5
  assert.equal(M.shinjoPhaseBonus(3, 4), 0);
});

test("kakitaDefenderPhaseBonus = x * max(0, def - atk)", () => {
  assert.equal(M.kakitaDefenderPhaseBonus(4, 6, 2), 16);
  assert.equal(M.kakitaDefenderPhaseBonus(4, 6, 0), 24); // attacker phase 0
  assert.equal(M.kakitaDefenderPhaseBonus(4, 2, 6), 0); // clamps
});

test("contestSkillRaiseBonus = max(0, ours-theirs) * 5", () => {
  assert.equal(M.contestSkillRaiseBonus(5, 2), 15);
  assert.equal(M.contestSkillRaiseBonus(2, 5), 0);
});

test("bankExcess = max(0, ours - opponent)", () => {
  assert.equal(M.bankExcess(40, 25), 15);
  assert.equal(M.bankExcess(20, 25), 0);
});

test("yogoHealLightWounds = max(0, lw - vpSpent*healPerVp)", () => {
  assert.equal(M.yogoHealLightWounds(15, 2, 4), 7);
  assert.equal(M.yogoHealLightWounds(5, 3, 4), 0); // clamps
});

// --- Group E: thresholds / misc ---

test("isImpaired when serious wounds >= Earth ring", () => {
  assert.equal(M.isImpaired(3, 3), true);
  assert.equal(M.isImpaired(2, 3), false);
});

test("duelTn = floor(totalXp / 10)", () => {
  assert.equal(M.duelTn(157), 15);
  assert.equal(M.duelTn(0), 0);
});

test("evaluateStanceInfo: roll 27 reveals Fire<=4 exactly / >=5, TN<=26 / 27+", () => {
  // The canonical example from the rules: a 27 means X = floor(27/5) = 5,
  // so the exact Fire Ring is learned iff it is 4 or less, otherwise only
  // "at least 5"; the exact TN is learned iff it is 26 or less, else "27+".
  const info = M.evaluateStanceInfo(27);
  assert.deepEqual(info, {
    roll: 27,
    fireBound: 5,
    fireExactMax: 4,
    fireCertain: false, // bound 5 < cap 6: a Fire of 6 would read only "5+"
    tnBound: 27,
    tnExactMax: 26,
  });
});

test("evaluateStanceInfo: bound at/above the ring cap means Fire is certain", () => {
  // roll 30 -> X = 6 = RING_MAX_SCHOOL, so "at least 6" pins it to exactly 6.
  const info = M.evaluateStanceInfo(30);
  assert.equal(info.fireBound, 6);
  assert.equal(info.fireCertain, true);
  // Well above (the reported 46) is also certain.
  assert.equal(M.evaluateStanceInfo(46).fireCertain, true);
  // Just below the threshold is not.
  assert.equal(M.evaluateStanceInfo(29).fireCertain, false);
});

test("evaluateStanceInfo: maxRing override changes the certainty threshold", () => {
  // With a cap of 5, a bound of 5 (roll 25) is already certain.
  assert.equal(M.evaluateStanceInfo(25, 5).fireCertain, true);
  assert.equal(M.evaluateStanceInfo(24, 5).fireCertain, false);
});

test("evaluateStanceInfo: exact divisor boundary (25 -> X=5)", () => {
  const info = M.evaluateStanceInfo(25);
  assert.equal(info.fireBound, 5);
  assert.equal(info.fireExactMax, 4);
  assert.equal(info.tnBound, 25);
  assert.equal(info.tnExactMax, 24);
});

test("evaluateStanceInfo: low / non-integer / nullish rolls clamp safely", () => {
  // A 0 roll learns nothing: fireBound 0, fireExactMax -1 (no ring qualifies).
  assert.deepEqual(M.evaluateStanceInfo(0), {
    roll: 0, fireBound: 0, fireExactMax: -1, fireCertain: false,
    tnBound: 0, tnExactMax: -1,
  });
  // Fractional totals floor; negatives and nullish clamp to 0.
  assert.equal(M.evaluateStanceInfo(33.9).fireBound, 6); // floor(33/5)
  assert.equal(M.evaluateStanceInfo(33.9).roll, 33);
  assert.equal(M.evaluateStanceInfo(-7).roll, 0);
  assert.equal(M.evaluateStanceInfo(undefined).roll, 0);
});

test("hidaRerollMax: X, 2X on counterattack, halved-up when impaired", () => {
  assert.equal(M.hidaRerollMax(3, false, false), 3);
  assert.equal(M.hidaRerollMax(3, true, false), 6); // counterattack
  assert.equal(M.hidaRerollMax(3, false, true), 2); // ceil(3/2)
  assert.equal(M.hidaRerollMax(3, true, true), 3); // ceil(6/2)
});

test("roundToTenths: round half up to nearest 0.1", () => {
  assert.equal(M.roundToTenths(1.64), 1.6);
  assert.equal(M.roundToTenths(1.65), 1.7);
  assert.equal(M.roundToTenths(2), 2);
});

// --- Akodo (already wired in the sheet) ---

test("akodoBankedBonus = floor(margin/5) * attackSkill, 0 if non-positive", () => {
  assert.equal(M.akodoBankedBonus(19, 4), 12);
  assert.equal(M.akodoBankedBonus(4, 4), 0);
  assert.equal(M.akodoBankedBonus(19, 0), 0);
  assert.equal(M.akodoBankedBonus(0, 4), 0);
});

// --- Lucky reroll resolution ---

test("luckyResolveReroll: reroll higher -> keep reroll, original not higher", () => {
  assert.deepEqual(M.luckyResolveReroll(15, 22, false),
                   { keepReroll: true, originalHigher: false });
});

test("luckyResolveReroll: reroll lower -> keep original (auto)", () => {
  // The whole point of the auto-use-higher rule: a strictly-lower reroll
  // returns keepReroll=false so the modal restores the original dice/total
  // and the followup step (damage, serious wounds) reads the higher value.
  assert.deepEqual(M.luckyResolveReroll(22, 15, false),
                   { keepReroll: false, originalHigher: true });
});

test("luckyResolveReroll: tie keeps the reroll (either is equivalent)", () => {
  assert.deepEqual(M.luckyResolveReroll(18, 18, false),
                   { keepReroll: true, originalHigher: false });
});

test("luckyResolveReroll: initiative keeps both - never auto-pick", () => {
  // Initiative produces two action-die layouts that aren't strictly
  // comparable. Whatever the totals look like, we report keepReroll=true
  // (so the live result shows the fresh roll) and never mark the original
  // as the winner - the modal lets the player choose which set to keep.
  assert.deepEqual(M.luckyResolveReroll(22, 15, true),
                   { keepReroll: true, originalHigher: false });
  assert.deepEqual(M.luckyResolveReroll(15, 22, true),
                   { keepReroll: true, originalHigher: false });
});
