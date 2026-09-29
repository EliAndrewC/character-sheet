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

test("parryEffectiveTarget = max(0, tn - flat)", () => {
  assert.equal(M.parryEffectiveTarget(30, 0), 30); // no bonuses
  assert.equal(M.parryEffectiveTarget(30, 5), 25); // predeclared +5
  assert.equal(M.parryEffectiveTarget(30, 8), 22); // formula flat folded in
  assert.equal(M.parryEffectiveTarget(5, 20), 0); // bonuses exceed TN -> clamp 0
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

test("applyTotalCap: total at or under the cap is untouched", () => {
  assert.equal(M.applyTotalCap(12, 15), 12);
  assert.equal(M.applyTotalCap(15, 15), 15);
});

test("applyTotalCap: total over the cap returns the cap", () => {
  assert.equal(M.applyTotalCap(27, 15), 15);
});

test("applyTotalCap: no cap leaves the total alone", () => {
  // 0 is the "no cap" sentinel on RollFormula.max_total, so an
  // uncapped roll must not be flattened to 0.
  assert.equal(M.applyTotalCap(27, 0), 27);
  assert.equal(M.applyTotalCap(27, null), 27);
  assert.equal(M.applyTotalCap(27, undefined), 27);
  assert.equal(M.applyTotalCap(27, "15"), 27); // non-number is not a cap
});

test("applyTotalCap: caps a negative total up to the cap only when over", () => {
  // Withdrawn caps at 15; a badly-failed roll stays where it is.
  assert.equal(M.applyTotalCap(-3, 15), -3);
});

test("totalCapApplies: true only when the cap actually bites", () => {
  assert.equal(M.totalCapApplies(27, 15), true);
  assert.equal(M.totalCapApplies(15, 15), false);
  assert.equal(M.totalCapApplies(12, 15), false);
  assert.equal(M.totalCapApplies(27, 0), false);
  assert.equal(M.totalCapApplies(27, null), false);
});

// --- Alternative-totals rows (conditional bonuses, optional ceilings) ---

test("altCap: a row's own cap wins over the formula's", () => {
  assert.equal(M.altCap({max_total: 15}, 0), 15);
  assert.equal(M.altCap({max_total: 15}, 20), 15);
});

test("altCap: a row without its own cap inherits the formula's", () => {
  // Withdrawn + Etiquette + a Specialization: the formula carries the cap,
  // and the Specialization row is still an etiquette roll, so it inherits.
  assert.equal(M.altCap({}, 15), 15);
  assert.equal(M.altCap({extra_flat: 10}, 15), 15);
});

test("altCap: uncapped when neither row nor formula has one", () => {
  assert.equal(M.altCap({extra_flat: 10}, 0), 0);
  assert.equal(M.altCap({}, undefined), 0);
  assert.equal(M.altCap(null, 0), 0);
});

test("altTotal: base + delta, clamped to the row's cap", () => {
  // Withdrawn sincerity at Honor 3: 24 contested, open row capped at 15.
  assert.equal(M.altTotal(24, {extra_flat: 6, max_total: 15}, 0), 15);
  // Under the cap, untouched.
  assert.equal(M.altTotal(5, {extra_flat: 2, max_total: 15}, 0), 7);
  // Uncapped row.
  assert.equal(M.altTotal(29, {extra_flat: 10}, 0), 39);
  // Negative delta (Unkempt's -10 on Culture).
  assert.equal(M.altTotal(29, {extra_flat: -10}, 0), 19);
  // Missing delta counts as 0.
  assert.equal(M.altTotal(24, {max_total: 15}, 0), 15);
});

test("altTotalAll: sums every delta when nothing is capped", () => {
  assert.equal(M.altTotalAll(29, [{extra_flat: 10}, {extra_flat: 5}], 0), 44);
});

test("altTotalAll: the tightest cap among the rows binds", () => {
  // A combined row that includes a capped condition is an instance of that
  // condition, so it is capped too: 24 + 6 + 10 = 40 -> 15.
  assert.equal(M.altTotalAll(24, [
    {extra_flat: 6, max_total: 15},
    {extra_flat: 10},
  ], 0), 15);
  // Two different caps -> the lower one wins.
  assert.equal(M.altTotalAll(24, [
    {extra_flat: 6, max_total: 20},
    {extra_flat: 10, max_total: 15},
  ], 0), 15);
});

test("altTotalAll: rows inherit the formula cap", () => {
  assert.equal(M.altTotalAll(24, [{extra_flat: 6}, {extra_flat: 10}], 15), 15);
});

test("altTotalAll: empty list is just the base total", () => {
  assert.equal(M.altTotalAll(24, [], 0), 24);
  assert.equal(M.altTotalAll(24, null, 0), 24);
});

test("alt helpers tolerate malformed rows", () => {
  // Defensive: a null row must not throw mid-render and take the whole
  // result modal down with it.
  assert.equal(M.altTotal(24, null, 0), 24);
  assert.equal(M.altTotalAll(24, [null, {extra_flat: 5}], 0), 29);
});

test("visibleAlternatives: uncapped rows always pass through", () => {
  const rows = [{extra_flat: 5}, {extra_flat: -10}];
  assert.deepEqual(M.visibleAlternatives(24, rows, 0), rows);
});

test("visibleAlternatives: drops a row the formula cap makes redundant", () => {
  // Withdrawn + Etiquette + Streetwise: the roll displays as 15 (capped)
  // and the "+5 when invoking bounty hunter authority" row also caps at
  // 15 - it repeats the only total, so it must not render.
  assert.deepEqual(M.visibleAlternatives(27, [{extra_flat: 5}], 15), []);
  // Exactly at the cap: 15 + 5 -> 15 == displayed 15, still redundant.
  assert.deepEqual(M.visibleAlternatives(15, [{extra_flat: 5}], 15), []);
});

test("visibleAlternatives: keeps a capped row that still moves the total", () => {
  // Base 12 (under the cap): the row shows 15 vs a displayed 12 - a real
  // alternate total, so it stays.
  const row = {extra_flat: 5};
  assert.deepEqual(M.visibleAlternatives(12, [row], 15), [row]);
});

test("visibleAlternatives: row-level cap compares against the uncapped base", () => {
  // Withdrawn sincerity: the contested base is uncapped (24), the open-roll
  // row caps at 15 - different numbers, so the row stays...
  const capped = {extra_flat: 0, max_total: 15};
  assert.deepEqual(M.visibleAlternatives(24, [capped], 0), [capped]);
  // ...but when the base is under the cap and the delta is 0, the row
  // repeats the base total and is dropped.
  assert.deepEqual(M.visibleAlternatives(10, [capped], 0), []);
});

test("visibleAlternatives: filters per-row within a mixed list", () => {
  // Sincerity at the cap boundary: the open-roll honor row is swallowed
  // (15 + 5 -> 15 == base 15) while the uncapped Specialization row is not.
  const open = {extra_flat: 5, max_total: 15};
  const spec = {extra_flat: 10};
  assert.deepEqual(M.visibleAlternatives(15, [open, spec], 0), [spec]);
});

test("visibleAlternatives: tolerates null rows and a null list", () => {
  assert.deepEqual(M.visibleAlternatives(24, null, 0), []);
  // A null row's total equals the base (no delta, no cap) -> dropped,
  // and it must not throw.
  assert.deepEqual(M.visibleAlternatives(24, [null, {extra_flat: 5}], 0),
                   [{extra_flat: 5}]);
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

// --- Group E: thresholds / misc ---

test("isImpaired when serious wounds >= Earth ring", () => {
  assert.equal(M.isImpaired(3, 3), true);
  assert.equal(M.isImpaired(2, 3), false);
});

test("duelTn = floor(totalXp / 10)", () => {
  assert.equal(M.duelTn(157), 15);
  assert.equal(M.duelTn(0), 0);
});

test("pcpTotalCost is the Nth triangular number", () => {
  assert.equal(M.pcpTotalCost(0), 0);
  assert.equal(M.pcpTotalCost(1), 1);
  assert.equal(M.pcpTotalCost(2), 3);
  assert.equal(M.pcpTotalCost(3), 6);
  assert.equal(M.pcpTotalCost(5), 15);
  assert.equal(M.pcpTotalCost(-4), 0); // clamps negative
});

test("pcpNextCost = count + 1 (clamped)", () => {
  assert.equal(M.pcpNextCost(0), 1);
  assert.equal(M.pcpNextCost(4), 5);
  assert.equal(M.pcpNextCost(-2), 1);
});

test("pcpSpendBreakdown splits unspent vs debt", () => {
  assert.deepEqual(M.pcpSpendBreakdown(10, 3),
    { fromUnspent: 3, fromDebt: 0, remainingAfter: 7 });
  assert.deepEqual(M.pcpSpendBreakdown(1, 2),
    { fromUnspent: 1, fromDebt: 1, remainingAfter: -1 });
  assert.deepEqual(M.pcpSpendBreakdown(0, 3),
    { fromUnspent: 0, fromDebt: 3, remainingAfter: -3 });
  assert.deepEqual(M.pcpSpendBreakdown(-2, 3),
    { fromUnspent: 0, fromDebt: 3, remainingAfter: -5 });
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

test("roundToHundredths: round half up to nearest 0.01 (the zeni)", () => {
  assert.equal(M.roundToHundredths(1.654), 1.65);
  assert.equal(M.roundToHundredths(1.655), 1.66);
  assert.equal(M.roundToHundredths(2), 2);
  // Tenths (bu) survive untouched now that hundredths are tracked.
  assert.equal(M.roundToHundredths(1.65), 1.65);
  assert.equal(M.roundToHundredths(20.25), 20.25);
  // Float-representation traps: naive x*100 lands just under the .5
  // boundary for these, which would round them down.
  assert.equal(M.roundToHundredths(1.005), 1.01);
  assert.equal(M.roundToHundredths(8.285), 8.29);
  // Below half a zeni rounds away entirely.
  assert.equal(M.roundToHundredths(0.004), 0);
  assert.equal(M.roundToHundredths(0.005), 0.01);
});

test("formatKoku: one decimal normally, two when there are zeni", () => {
  assert.equal(M.formatKoku(4), "4.0");
  assert.equal(M.formatKoku(20.3), "20.3");
  assert.equal(M.formatKoku(20.25), "20.25");
  assert.equal(M.formatKoku(0), "0.0");
  // Rounds before formatting, so sub-zeni input never leaks through.
  assert.equal(M.formatKoku(1.005), "1.01");
  // Defensive: a null/undefined/NaN amount renders as zero, not "NaN".
  assert.equal(M.formatKoku(null), "0.0");
  assert.equal(M.formatKoku(undefined), "0.0");
  // Negatives (a corrupt persisted value) still render sanely.
  assert.equal(M.formatKoku(-2.5), "-2.5");
});

// --- Akodo (already wired in the sheet) ---

// --- Lucky reroll resolution ---

// --- Void-point allocation (spend menu + Commune's activation cost) ---

test("allocateVoidSpend draws temp first, then regular, then worldliness", () => {
  assert.deepEqual(M.allocateVoidSpend(1, 2, 3, 4), {
    fromTemp: 1, fromRegular: 0, fromWorldliness: 0, allocated: 1, short: false,
  });
  assert.deepEqual(M.allocateVoidSpend(3, 2, 3, 4), {
    fromTemp: 2, fromRegular: 1, fromWorldliness: 0, allocated: 3, short: false,
  });
  assert.deepEqual(M.allocateVoidSpend(6, 2, 3, 4), {
    fromTemp: 2, fromRegular: 3, fromWorldliness: 1, allocated: 6, short: false,
  });
});

test("allocateVoidSpend skips empty pools", () => {
  assert.deepEqual(M.allocateVoidSpend(2, 0, 0, 5), {
    fromTemp: 0, fromRegular: 0, fromWorldliness: 2, allocated: 2, short: false,
  });
  assert.deepEqual(M.allocateVoidSpend(2, 0, 5, 0), {
    fromTemp: 0, fromRegular: 2, fromWorldliness: 0, allocated: 2, short: false,
  });
});

test("allocateVoidSpend reports short when the pools can't cover the cost", () => {
  const r = M.allocateVoidSpend(3, 1, 1, 0);
  assert.deepEqual(r, {
    fromTemp: 1, fromRegular: 1, fromWorldliness: 0, allocated: 2, short: true,
  });
  // Commune with an empty pool: nothing to draw, so the roll is unavailable.
  assert.equal(M.allocateVoidSpend(1, 0, 0, 0).short, true);
});

test("allocateVoidSpend treats zero/negative/missing counts as no spend", () => {
  const none = {
    fromTemp: 0, fromRegular: 0, fromWorldliness: 0, allocated: 0, short: false,
  };
  assert.deepEqual(M.allocateVoidSpend(0, 3, 3, 3), none);
  assert.deepEqual(M.allocateVoidSpend(-2, 3, 3, 3), none);
  assert.deepEqual(M.allocateVoidSpend(undefined, 3, 3, 3), none);
  // Negative / undefined pools are clamped to empty, not treated as credit.
  assert.deepEqual(M.allocateVoidSpend(1, -5, undefined, null), {
    fromTemp: 0, fromRegular: 0, fromWorldliness: 0, allocated: 0, short: true,
  });
});

test("allocateVoidSpend is additive: reserving 1 then N == allocating N+1", () => {
  // The Commune menu reserves the activation point and offers the rest; the
  // roll re-derives the activation draw from the live pool. Both paths must
  // agree, which holds because the priority order is monotone.
  const pools = [3, 2, 1];
  for (let n = 0; n <= 5; n++) {
    const reserve = M.allocateVoidSpend(1, pools[0], pools[1], pools[2]);
    const extra = M.allocateVoidSpend(
      n,
      pools[0] - reserve.fromTemp,
      pools[1] - reserve.fromRegular,
      pools[2] - reserve.fromWorldliness,
    );
    const combined = M.allocateVoidSpend(n + 1, pools[0], pools[1], pools[2]);
    assert.equal(reserve.fromTemp + extra.fromTemp, combined.fromTemp);
    assert.equal(reserve.fromRegular + extra.fromRegular, combined.fromRegular);
    assert.equal(reserve.fromWorldliness + extra.fromWorldliness, combined.fromWorldliness);
  }
});

// ---------------------------------------------------------------------------
// impairedSuppressesReroll - rules/03-combat.md scopes the Impaired reroll
// suppression to SKILLS. Must stay in step with _reroll_fields in
// app/services/dice.py; the Python side asserts the same partition in
// TestBuildAllRollFormulas::test_impaired_suppresses_the_reroll_on_skills_only.
// ---------------------------------------------------------------------------

test("impairedSuppressesReroll: nearly everything loses its rerolls", () => {
  for (const key of ["skill:bragging", "skill:etiquette", "attack", "parry",
                     "double_attack", "counterattack", "lunge",
                     "knack:oppose_social", "knack:iaijutsu"]) {
    assert.equal(M.impairedSuppressesReroll(key, {}), true, key);
  }
});

test("impairedSuppressesReroll: wound checks keep rerolling", () => {
  assert.equal(M.impairedSuppressesReroll("wound_check", {}), false);
});

test("impairedSuppressesReroll: damage rolls keep rerolling", () => {
  // Named by the rule. Dragon Tattoo is the one that reaches here by key.
  assert.equal(
    M.impairedSuppressesReroll("knack:dragon_tattoo", { is_damage_roll: true }),
    false
  );
});

test("impairedSuppressesReroll: athletics and ring rolls ARE suppressed", () => {
  // GM ruling 2026-08-29: the rule's two written exceptions are the only
  // ones, so these lose their rerolls despite not being "skills".
  assert.equal(M.impairedSuppressesReroll("knack:athletics", {}), true);
  for (const key of ["athletics:Air", "athletics:Fire", "athletics:attack",
                     "athletics:parry", "ring:Air", "ring:Fire", "ring:Earth",
                     "ring:Water", "ring:Void"]) {
    assert.equal(M.impairedSuppressesReroll(key, {}), true, key);
  }
});

test("impairedSuppressesReroll: tolerates a missing formula or key", () => {
  assert.equal(M.impairedSuppressesReroll("skill:bragging"), true);
  assert.equal(M.impairedSuppressesReroll("ring:Air", null), true);
  assert.equal(M.impairedSuppressesReroll(undefined, {}), true);
});

test("impairedSuppressesReroll: Hida 3rd Dan keeps its rerolls on attack rolls", () => {
  const attack = { is_attack_type: true };
  const opts = { hidaReroll: true };
  assert.equal(M.impairedSuppressesReroll("attack", attack, opts), false);
  assert.equal(M.impairedSuppressesReroll("knack:counterattack", attack, opts), false);
  // Only attack rolls, and only for a character who has the ability.
  assert.equal(M.impairedSuppressesReroll("parry", {}, opts), true);
  assert.equal(M.impairedSuppressesReroll("skill:bragging", {}, opts), true);
  assert.equal(M.impairedSuppressesReroll("attack", attack, {}), true);
  assert.equal(M.impairedSuppressesReroll("attack", attack), true);
});

test("hidaRerollMax halves and rounds up when impaired", () => {
  assert.equal(M.hidaRerollMax(3, false, false), 3);
  assert.equal(M.hidaRerollMax(3, true, false), 6);   // counterattack: 2X
  assert.equal(M.hidaRerollMax(3, false, true), 2);   // ceil(3/2)
  assert.equal(M.hidaRerollMax(3, true, true), 3);    // ceil(6/2)
});
