"use strict";
// Fly.io keep-alive pinger.
//
// The app runs on Fly with auto_stop_machines, so the first request after a
// quiet spell pays a cold-boot penalty. Every open page pings GET /keepalive
// once a minute, but only when one of two windows is open - a sheet left open
// all week must not keep the machine (and the bill) running.
//
//   1. THE SESSION WINDOW, for everyone: the wall clock in America/New_York
//      falls on a game night (Mon/Tue, 7pm-11pm by default).
//
//   2. THE ACTIVITY WINDOW, only for viewers the server opted in via
//      `data-extended-keepalive="1"` on <html> (see app/main.py
//      extended_keepalive_enabled + EXTENDED_KEEPALIVE_DISCORD_IDS): pings
//      continue for an hour after that person's last interaction with the
//      page. Loading a page counts as an interaction, so following a link
//      restarts the hour; a forgotten tab goes quiet an hour after it was
//      last touched instead of pinging forever.
//
// The pure decisions (`shouldKeepAlive` and the two window predicates) take
// everything they need as arguments and are unit-tested under Node:
// `node --test tests/js/`. The mutable activity state lives in the impure
// layer below and is fed in through `currentOptions()`.
(function () {
  var DEFAULTS = {
    timeZone: "America/New_York",
    days: ["Mon", "Tue"],
    startHour: 19, // inclusive: 7:00pm
    endHour: 23, // exclusive: pings stop at 11:00pm
    // Activity window. Off unless the server opted this viewer in, and inert
    // until an interaction has been recorded.
    extended: false,
    lastInteraction: null,
    extendedWindowMs: 60 * 60 * 1000, // one hour
  };
  var INTERVAL_MS = 60 * 1000;
  var URL = "/keepalive";

  // What counts as "interacting with the app". Deliberately narrow: pointer
  // and keyboard input a person had to actually perform. Mouse movement or
  // tab focus would let a forgotten tab renew itself indefinitely, which is
  // the whole thing the hour limit exists to prevent.
  var INTERACTION_EVENTS = ["click", "keydown", "submit"];
  var FLAG_ATTRIBUTE = "data-extended-keepalive";

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

  // Window 1: a game night, for every visitor.
  function inSessionWindow(date, o) {
    var p = localParts(date, o.timeZone);
    return o.days.indexOf(p.day) !== -1 && p.hour >= o.startHour && p.hour < o.endHour;
  }

  // Window 2: within an hour of an opted-in viewer's last interaction.
  // A negative elapsed time means the system clock moved backwards; treat
  // that as out-of-window rather than trusting it, since the next
  // interaction re-opens the window anyway.
  function inActivityWindow(date, o) {
    if (!o.extended || typeof o.lastInteraction !== "number") return false;
    var elapsed = date.getTime() - o.lastInteraction;
    return elapsed >= 0 && elapsed < o.extendedWindowMs;
  }

  function shouldKeepAlive(date, opts) {
    var o = Object.assign({}, DEFAULTS, opts || {});
    return inSessionWindow(date, o) || inActivityWindow(date, o);
  }

  // One timer tick: ping if either window is open. Returns true if a ping
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

  // --------------------------------------------------------------------
  // Impure layer: the activity state the timer feeds into the predicates.
  // --------------------------------------------------------------------

  var state = { extended: false, lastInteraction: null };

  // The options the live timer rolls with. Kept separate from DEFAULTS so
  // `shouldKeepAlive` stays a pure function of its arguments.
  function currentOptions() {
    return { extended: state.extended, lastInteraction: state.lastInteraction };
  }

  function noteInteraction(now) {
    state.lastInteraction = (now || new Date()).getTime();
    return state.lastInteraction;
  }

  function enableExtended(on) {
    state.extended = !!on;
    return state.extended;
  }

  // Read the server's opt-in flag off <html>.
  function extendedFromDocument(doc) {
    var el = doc && doc.documentElement;
    return !!(el && el.getAttribute(FLAG_ATTRIBUTE) === "1");
  }

  // Listen in the CAPTURE phase so a handler that stops propagation (the
  // sheet's modals do) can't hide an interaction from us, and passively so
  // we never delay the interaction we're only observing.
  function watchInteractions(target) {
    if (!target || typeof target.addEventListener !== "function") return false;
    var handler = function () { noteInteraction(); };
    for (var i = 0; i < INTERACTION_EVENTS.length; i++) {
      target.addEventListener(INTERACTION_EVENTS[i], handler, {
        capture: true,
        passive: true,
      });
    }
    return true;
  }

  function start() {
    if (typeof setInterval !== "function" || typeof fetch !== "function") return null;
    if (typeof document !== "undefined") {
      enableExtended(extendedFromDocument(document));
      watchInteractions(document);
    }
    // Loading the page is itself an interaction - it is how following a link
    // restarts the hour.
    noteInteraction();
    return setInterval(function () {
      tick(new Date(), fetch, currentOptions());
    }, INTERVAL_MS);
  }

  var L7RKeepAlive = {
    DEFAULTS: DEFAULTS,
    INTERVAL_MS: INTERVAL_MS,
    URL: URL,
    INTERACTION_EVENTS: INTERACTION_EVENTS,
    FLAG_ATTRIBUTE: FLAG_ATTRIBUTE,
    localParts: localParts,
    inSessionWindow: inSessionWindow,
    inActivityWindow: inActivityWindow,
    shouldKeepAlive: shouldKeepAlive,
    tick: tick,
    currentOptions: currentOptions,
    noteInteraction: noteInteraction,
    enableExtended: enableExtended,
    extendedFromDocument: extendedFromDocument,
    watchInteractions: watchInteractions,
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
