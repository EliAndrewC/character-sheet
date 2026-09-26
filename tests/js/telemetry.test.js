"use strict";
// Unit tests for the pure layer of app/static/js/telemetry.js.
//     node --test tests/js/*.test.js
const { test } = require("node:test");
const assert = require("node:assert/strict");
const T = require("../../app/static/js/telemetry.js");

const CTX = { tab: "abc12345", build: "deployment-01", page: "/characters/14", started: 1_000_000 };
const MIN = 60 * 1000;

test("newTabId is 8 base-36 characters", () => {
  assert.match(T.newTabId(), /^[0-9a-z]{8}$/);
  let i = 0;
  const seq = [0, 0.5, 0.99];
  assert.equal(T.newTabId(() => seq[i++ % 3]), "0iz0iz0i");
});

test("makeLimiter allows each key once, up to the cap", () => {
  const lim = T.makeLimiter(2);
  assert.equal(lim.allow("a"), true);
  assert.equal(lim.allow("a"), false); // duplicate
  assert.equal(lim.allow("b"), true);
  assert.equal(lim.allow("c"), false); // over the cap
});

test("heapMB reads Chromium's performance.memory, null elsewhere", () => {
  assert.equal(T.heapMB({ memory: { usedJSHeapSize: 87 * 1048576 + 1000 } }), 87);
  assert.equal(T.heapMB({}), null);
  assert.equal(T.heapMB(null), null);
  assert.equal(T.heapMB({ memory: {} }), null);
});

test("errorReport carries context, truncates, and drops unknowns", () => {
  const r = T.errorReport(
    "error",
    { message: "x".repeat(900), source: "/static/js/dice.js", line: 12.4, col: "7", stack: undefined },
    CTX, CTX.started + 90_500, 64,
  );
  assert.equal(r.kind, "error");
  assert.equal(r.tab, "abc12345");
  assert.equal(r.build, "deployment-01");
  assert.equal(r.page, "/characters/14");
  assert.equal(r.message.length, 500);
  assert.equal(r.line, 12);
  assert.equal("col" in r, false); // not a number
  assert.equal("stack" in r, false);
  assert.equal(r.up, 91);
  assert.equal(r.heap, 64);
});

test("errorReport tolerates missing info and heap", () => {
  const r = T.errorReport("rejection", undefined, CTX, CTX.started, null);
  assert.deepEqual(Object.keys(r).sort(), ["build", "kind", "page", "tab", "up"]);
});

test("nextEntry tracks first and peak heap across heartbeats", () => {
  let e = T.nextEntry(null, CTX, 2_000_000, 50, "visible");
  assert.deepEqual(
    [e.heap, e.heap_start, e.heap_max, e.last, e.vis, e.started],
    [50, 50, 50, 2_000_000, "visible", CTX.started],
  );
  e = T.nextEntry(e, CTX, 2_030_000, 80, "hidden");
  assert.deepEqual([e.heap, e.heap_start, e.heap_max], [80, 50, 80]);
  e = T.nextEntry(e, CTX, 2_060_000, 60, null);
  assert.deepEqual([e.heap, e.heap_start, e.heap_max, e.vis], [60, 50, 80, null]);
});

test("nextEntry without heap samples (Firefox/Safari) keeps nulls", () => {
  let e = T.nextEntry(null, CTX, 1, null, "visible");
  e = T.nextEntry(e, CTX, 2, null, "visible");
  assert.deepEqual([e.heap, e.heap_start, e.heap_max], [null, null, null]);
  // A first sample after nulls becomes the start.
  e = T.nextEntry(e, CTX, 3, 40, "visible");
  assert.deepEqual([e.heap_start, e.heap_max], [40, 40]);
});

test("parseEntry accepts our entries and rejects everything else", () => {
  const good = JSON.stringify({ tab: "t", last: 5, started: 1 });
  assert.equal(T.parseEntry("l7r.tab.t", good).key, "l7r.tab.t");
  assert.equal(T.parseEntry("other", good), null);
  assert.equal(T.parseEntry(null, good), null);
  assert.equal(T.parseEntry("l7r.tab.t", "{not json"), null);
  assert.equal(T.parseEntry("l7r.tab.t", JSON.stringify({ tab: "t" })), null);
  assert.equal(T.parseEntry("l7r.tab.t", "null"), null);
});

function entry(tab, last, started) {
  return { key: T.TAB_PREFIX + tab, tab, last, started: started || 0 };
}

test("findUncleanTabs: with a probe, whoever did not answer is dead", () => {
  const now = 10 * MIN;
  const res = T.findUncleanTabs(
    [entry("live", now - 1000), entry("dead", now - 1000)],
    now, { live: true },
  );
  // Freshness does not save a tab that did not answer: the crash-and-reopen
  // happens within seconds, which is the case that matters.
  assert.deepEqual(res.report.map((e) => e.tab), ["dead"]);
  assert.deepEqual(res.drop, []);
});

test("findUncleanTabs: without a probe, falls back to staleness", () => {
  const now = 10 * MIN;
  const res = T.findUncleanTabs(
    [entry("fresh", now - MIN), entry("stale", now - 4 * MIN)], now, null,
  );
  assert.deepEqual(res.report.map((e) => e.tab), ["stale"]);
});

test("findUncleanTabs drops entries older than a week without reporting", () => {
  const now = 30 * 24 * 60 * MIN;
  const res = T.findUncleanTabs([entry("ancient", now - T.MAX_AGE_MS - 1)], now, {});
  assert.deepEqual(res.report, []);
  assert.deepEqual(res.drop, [T.TAB_PREFIX + "ancient"]);
});

test("findUncleanTabs honours option overrides", () => {
  const res = T.findUncleanTabs([entry("x", 0)], 2000, null, { staleMs: 1000 });
  assert.equal(res.report.length, 1);
});

test("uncleanReport says how long the tab lived and when it was last seen", () => {
  const e = {
    tab: "t1", build: "b", page: "/characters/14", started: 0,
    last: 45 * MIN, heap: 400, heap_start: 60, heap_max: 410, vis: "visible",
  };
  assert.deepEqual(T.uncleanReport(e, 45 * MIN + 20_000), {
    kind: "unclean_exit", tab: "t1", build: "b", page: "/characters/14",
    up: 2700, ago: 20, heap: 400, heap_start: 60, heap_max: 410, vis: "visible",
  });
});

test("sampleQuery carries id, uptime, build and (when known) heap/visibility", () => {
  assert.equal(
    T.sampleQuery(CTX, CTX.started + 61_000, 88, "visible"),
    "tab=abc12345&up=61&build=deployment-01&heap=88&vis=visible",
  );
  assert.equal(
    T.sampleQuery({ tab: "a b", started: 0 }, 0, null, null),
    "tab=a%20b&up=0&build=",
  );
});

test("isStale only when both builds are known and differ", () => {
  assert.equal(T.isStale("a", "b"), true);
  assert.equal(T.isStale("a", "a"), false);
  assert.equal(T.isStale("a", null), false);
  assert.equal(T.isStale("", "b"), false);
});
