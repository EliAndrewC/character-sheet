"use strict";
// Fly.io keep-alive pinger.
//
// The app runs on Fly with auto_stop_machines, so the first request after a
// quiet spell pays a cold-boot penalty. To keep it warm during actual game
// sessions - and ONLY then, so a sheet left open all week doesn't keep the
// machine (and the bill) running - every open page pings GET /keepalive once
// a minute while the wall clock in America/New_York falls inside a session
// window (Mon/Tue, 7pm-11pm by default).
//
// The pure decision (`shouldKeepAlive`) is separated from the timer/fetch so
// it can be unit-tested under Node: `node --test tests/js/`.
(function () {
  var DEFAULTS = {
    timeZone: "America/New_York",
    days: ["Mon", "Tue"],
    startHour: 19, // inclusive: 7:00pm
    endHour: 23, // exclusive: pings stop at 11:00pm
  };
  var INTERVAL_MS = 60 * 1000;
  var URL = "/keepalive";

  // Weekday abbreviation + hour of `date` in `timeZone`, as {day, hour}.
  function localParts(date, timeZone) {
    var parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timeZone,
      weekday: "short",
      hour: "numeric",
      hourCycle: "h23",
    }).formatToParts(date);
    var out = { day: null, hour: null };
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === "weekday") out.day = parts[i].value;
      if (parts[i].type === "hour") out.hour = parseInt(parts[i].value, 10);
    }
    return out;
  }

  function shouldKeepAlive(date, opts) {
    var o = Object.assign({}, DEFAULTS, opts || {});
    var p = localParts(date, o.timeZone);
    return o.days.indexOf(p.day) !== -1 && p.hour >= o.startHour && p.hour < o.endHour;
  }

  // One timer tick: ping if we're inside the window. Returns true if a ping
  // was sent. `fetchFn` is injectable for tests.
  function tick(date, fetchFn, opts) {
    if (!shouldKeepAlive(date, opts)) return false;
    try {
      fetchFn(URL, { cache: "no-store", credentials: "same-origin" }).catch(function () {});
    } catch (e) {
      /* a failed ping is harmless - the next tick retries */
    }
    return true;
  }

  function start() {
    if (typeof setInterval !== "function" || typeof fetch !== "function") return null;
    return setInterval(function () {
      tick(new Date(), fetch);
    }, INTERVAL_MS);
  }

  var L7RKeepAlive = {
    DEFAULTS: DEFAULTS,
    INTERVAL_MS: INTERVAL_MS,
    URL: URL,
    localParts: localParts,
    shouldKeepAlive: shouldKeepAlive,
    tick: tick,
    start: start,
  };

  globalThis.L7RKeepAlive = L7RKeepAlive;
  /* node:coverage disable */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = L7RKeepAlive;
  } else if (typeof window !== "undefined") {
    // Browser: start the once-a-minute timer on every page.
    start();
  }
  /* node:coverage enable */
})();
