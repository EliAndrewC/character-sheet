"use strict";
// Unit tests for the Fly keep-alive pinger (app/static/js/keepalive.js).
//     node --test tests/js/
const { test } = require("node:test");
const assert = require("node:assert/strict");
const K = require("../../app/static/js/keepalive.js");

// Helper: a UTC instant that is `hour`:mm on the given weekday in New York.
// 2026-08-24 is a Monday; New York is UTC-4 (EDT) in August.
function nyAug2026(dayOffset, hour, minute) {
  return new Date(Date.UTC(2026, 7, 24 + dayOffset, hour + 4, minute || 0));
}

test("localParts converts to New York weekday and 24h hour", () => {
  assert.deepEqual(K.localParts(nyAug2026(0, 19, 5), "America/New_York"), { day: "Mon", hour: 19 });
  assert.deepEqual(K.localParts(nyAug2026(1, 0, 0), "America/New_York"), { day: "Tue", hour: 0 });
  // Same instant read in a different zone.
  assert.deepEqual(K.localParts(nyAug2026(0, 19, 5), "UTC"), { day: "Mon", hour: 23 });
});

test("shouldKeepAlive is true Mon/Tue 7pm-11pm New York", () => {
  assert.equal(K.shouldKeepAlive(nyAug2026(0, 19, 0)), true); // Mon 7:00pm - window opens
  assert.equal(K.shouldKeepAlive(nyAug2026(0, 22, 59)), true); // Mon 10:59pm
  assert.equal(K.shouldKeepAlive(nyAug2026(1, 20, 30)), true); // Tue 8:30pm
});

test("shouldKeepAlive is false outside the window", () => {
  assert.equal(K.shouldKeepAlive(nyAug2026(0, 18, 59)), false); // Mon 6:59pm - too early
  assert.equal(K.shouldKeepAlive(nyAug2026(0, 23, 0)), false); // Mon 11:00pm - window closed
  assert.equal(K.shouldKeepAlive(nyAug2026(2, 20, 0)), false); // Wed evening
  assert.equal(K.shouldKeepAlive(nyAug2026(6, 20, 0)), false); // Sun evening
});

test("shouldKeepAlive uses New York time, not UTC or the viewer's zone", () => {
  // Mon 22:30 New York == Tue 02:30 UTC. Only the NY reading is in-window.
  const d = nyAug2026(0, 22, 30);
  assert.equal(K.shouldKeepAlive(d), true);
  assert.equal(K.shouldKeepAlive(d, { timeZone: "UTC" }), false);
});

test("shouldKeepAlive honours DST (January is UTC-5)", () => {
  // 2026-01-05 is a Monday. 19:00 EST == 00:00 UTC next day.
  assert.equal(K.shouldKeepAlive(new Date(Date.UTC(2026, 0, 6, 0, 0))), true);
  assert.equal(K.shouldKeepAlive(new Date(Date.UTC(2026, 0, 5, 23, 59))), false);
});

test("shouldKeepAlive accepts option overrides", () => {
  assert.equal(K.shouldKeepAlive(nyAug2026(2, 20, 0), { days: ["Wed"] }), true);
  assert.equal(K.shouldKeepAlive(nyAug2026(0, 12, 0), { startHour: 12, endHour: 13 }), true);
});

test("tick pings only inside the window, with no-store and same-origin", () => {
  const calls = [];
  const fetchFn = (url, init) => {
    calls.push({ url, init });
    return Promise.resolve({ ok: true });
  };
  assert.equal(K.tick(nyAug2026(2, 20, 0), fetchFn), false);
  assert.equal(calls.length, 0);
  assert.equal(K.tick(nyAug2026(0, 20, 0), fetchFn), true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/keepalive");
  assert.equal(calls[0].init.cache, "no-store");
  assert.equal(calls[0].init.credentials, "same-origin");
});

test("tick swallows fetch failures (rejected promise and thrown error)", () => {
  const d = nyAug2026(0, 20, 0);
  assert.equal(K.tick(d, () => Promise.reject(new Error("offline"))), true);
  assert.equal(K.tick(d, () => { throw new Error("no fetch"); }), true);
});

test("start schedules a 60s interval and returns the handle", () => {
  const origSetInterval = globalThis.setInterval;
  const origFetch = globalThis.fetch;
  let scheduled = null;
  globalThis.setInterval = (fn, ms) => { scheduled = { fn, ms }; return 42; };
  globalThis.fetch = () => Promise.resolve({ ok: true });
  try {
    assert.equal(K.start(), 42);
    assert.equal(scheduled.ms, 60000);
    scheduled.fn(); // runs tick(new Date(), fetch) - must not throw
    globalThis.fetch = undefined;
    assert.equal(K.start(), null);
  } finally {
    globalThis.setInterval = origSetInterval;
    globalThis.fetch = origFetch;
  }
});
