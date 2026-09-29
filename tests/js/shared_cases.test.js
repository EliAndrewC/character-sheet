// Rules that must exist in BOTH the browser and the server, pinned to one
// table of cases. The Python suites (tests/test_void_spend.py,
// tests/test_roll_engine.py) read these same JSON files, so a change to the
// rule that is made on only one side turns one of the two suites red.
//
// Run: node --test tests/js/*.test.js

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const M = require("../../app/static/js/roll_math.js");

function load(name) {
  return JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "shared", name), "utf8")
  );
}

const voidCases = load("void_spend_cases.json");
const initCases = load("initiative_cases.json");

for (const c of voidCases.allocate) {
  test("allocateVoidSpend: " + c.name, () => {
    assert.deepEqual(M.allocateVoidSpend.apply(M, c.args), c.want);
  });
}

for (const c of voidCases.dice_cap) {
  test("applyDiceCap: " + c.name, () => {
    const got = M.applyDiceCap.apply(M, c.args);
    assert.deepEqual(
      { rolled: got.rolled, kept: got.kept, flat: got.flat, overflow: got.overflowFlat },
      c.want
    );
  });
}

for (const c of initCases.sort_value) {
  test("initiativeSortValue: " + c.name, () => {
    assert.equal(M.initiativeSortValue.apply(M, c.args), c.want);
  });
}

// Attack / damage / wound-check arithmetic shared with
// app/services/combat_math.py (the GM combat tracker's NPC rolls).
const combatCases = load("combat_math_cases.json");
const combatFns = {
  excess_to_extra_dice: "excessToExtraDice",
  attack_effective_tn: "attackEffectiveTn",
  wound_check_result: "woundCheckResult",
  wave_man_weapon_floor: "waveManWeaponFloor",
  wave_man_failed_parry_dice: "waveManFailedParryDice",
};
for (const [section, fn] of Object.entries(combatFns)) {
  for (const c of combatCases[section]) {
    test(fn + ": " + c.name, () => {
      assert.deepEqual(M[fn].apply(M, c.args), c.want);
    });
  }
}
