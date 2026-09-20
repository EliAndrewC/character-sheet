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

for (const c of initCases.action_values) {
  test("initiativeActionValues: " + c.name, () => {
    const kept = c.kept.slice();
    assert.deepEqual(M.initiativeActionValues(kept, c.flags), c.want);
    assert.deepEqual(kept, c.kept, "must not mutate its input");
  });
}

test("initiativeActionValues tolerates missing arguments", () => {
  assert.deepEqual(M.initiativeActionValues(undefined, undefined), []);
});
