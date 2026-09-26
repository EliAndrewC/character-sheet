"use strict";
// Client diagnostics. Server half: app/services/telemetry.py.
//
// Written after a player's tab crashed mid-session and there was no way to
// tell whether this app was to blame. Four jobs, all tiny on the wire:
//
//   1. ERRORS. Uncaught errors and unhandled promise rejections are sent to
//      POST /client-log (at most MAX_REPORTS per page load, each distinct
//      message once). Alpine re-throws expression errors asynchronously with
//      the expression attached, so those arrive here too, expression and all.
//
//   2. TABS THAT DIED. A crashed tab cannot report its own death, so every
//      page keeps a small entry in localStorage ("l7r.tab.<id>"), refreshes
//      it every HEARTBEAT_MS, and deletes it on `pagehide` - a clean close or
//      a navigation. The next page load asks the other open pages who is
//      alive (BroadcastChannel); an entry nobody answers for belonged to a
//      tab that ended without closing, and is reported as `unclean_exit`
//      with how long it was open and its memory samples. A browser that
//      froze a background tab (it cannot answer) will report it by mistake;
//      if that tab later wakes and finds its entry gone it says so
//      (`resumed`), which marks the earlier report as a false alarm.
//
//   3. MEMORY. keepalive.js's once-a-minute ping (game nights only) carries
//      this page's id, uptime, build and - in Chrome - its JS heap in MB, so
//      a leak shows up in the access log as a number that keeps climbing.
//
//   4. NEW VERSIONS. Every response carries X-App-Build; when one names a
//      build other than the one this page was rendered by (data-build on
//      <html>), a banner offers a reload. It never reloads by itself.
//
// Chrome's own crash reports (Reporting API) need no script: the server
// names the endpoint in a header. They cover the tab that is never reopened.
//
// The decisions are pure functions of their arguments and unit-tested under
// Node (`node --test tests/js/*.test.js`); the impure layer is below them.
(function () {
  var REPORT_URL = "/client-log";
  var TAB_PREFIX = "l7r.tab.";
  var CHANNEL_NAME = "l7r-tabs";
  var HEARTBEAT_MS = 30 * 1000;
  // Without BroadcastChannel nobody can be asked, so fall back to age:
  // an entry not refreshed for this long is presumed dead. Longer than
  // the one-per-minute timer a hidden tab is throttled to.
  var STALE_MS = 3 * 60 * 1000;
  // Entries older than this are dropped without a report; a week-old
  // death is no longer worth a log line.
  var MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
  var PROBE_MS = 1000; // how long to wait for "I'm alive" answers
  var REAP_DELAY_MS = 1500; // start reaping after the page has settled
  var MAX_REPORTS = 5;
  var BUILD_HEADER = "X-App-Build";

  // ------------------------------------------------------------------
  // Pure layer
  // ------------------------------------------------------------------

  function newTabId(rand) {
    rand = rand || Math.random;
    var s = "";
    while (s.length < 8) s += Math.floor(rand() * 36).toString(36);
    return s;
  }

  // At most `max` reports, each key at most once.
  function makeLimiter(max) {
    var seen = {};
    var count = 0;
    return {
      allow: function (key) {
        if (count >= max || Object.prototype.hasOwnProperty.call(seen, key)) return false;
        seen[key] = true;
        count++;
        return true;
      },
    };
  }

  // JS heap in MB, or null where the browser does not expose it (only
  // Chromium has performance.memory, and it is coarse - good enough to
  // see a climb).
  function heapMB(perf) {
    var m = perf && perf.memory;
    if (!m || typeof m.usedJSHeapSize !== "number") return null;
    return Math.round(m.usedJSHeapSize / 1048576);
  }

  function clip(value, n) {
    return typeof value === "string" ? value.slice(0, n) : undefined;
  }

  function num(value) {
    return typeof value === "number" && isFinite(value) ? Math.round(value) : undefined;
  }

  // Drop undefined/null so the payload only carries what is known.
  function compact(obj) {
    var out = {};
    for (var k in obj) {
      if (obj[k] !== undefined && obj[k] !== null) out[k] = obj[k];
    }
    return out;
  }

  // The body for an "error" / "rejection" report.
  function errorReport(kind, info, ctx, now, heap) {
    info = info || {};
    return compact({
      kind: kind,
      tab: ctx.tab,
      build: ctx.build,
      page: clip(ctx.page, 300),
      message: clip(info.message, 500),
      source: clip(info.source, 300),
      line: num(info.line),
      col: num(info.col),
      stack: clip(info.stack, 2000),
      expression: clip(info.expression, 300),
      up: num((now - ctx.started) / 1000),
      heap: heap,
    });
  }

  // The entry this page keeps in localStorage, refreshed on each heartbeat.
  function nextEntry(prev, ctx, now, heap, vis) {
    var e = {
      tab: ctx.tab,
      build: ctx.build,
      page: ctx.page,
      started: ctx.started,
      last: now,
      vis: vis || null,
      heap: heap,
      heap_start: prev ? prev.heap_start : heap,
      heap_max: prev ? prev.heap_max : heap,
    };
    if (e.heap_start === null || e.heap_start === undefined) e.heap_start = heap;
    if (typeof heap === "number" && !(e.heap_max >= heap)) e.heap_max = heap;
    return e;
  }

  // A stored entry, or null if it is not one of ours / is corrupt.
  function parseEntry(key, raw) {
    if (typeof key !== "string" || key.indexOf(TAB_PREFIX) !== 0) return null;
    try {
      var e = JSON.parse(raw);
      if (!e || typeof e.last !== "number" || typeof e.started !== "number") return null;
      e.key = key;
      return e;
    } catch (err) {
      return null;
    }
  }

  // Which other pages' entries belong to tabs that ended without closing.
  // `alive` is the set of tab ids that answered the probe, or null when
  // there was no way to ask (then fall back to staleness).
  function findUncleanTabs(entries, now, alive, opts) {
    var o = Object.assign({ staleMs: STALE_MS, maxAgeMs: MAX_AGE_MS }, opts || {});
    var out = { report: [], drop: [] };
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var age = now - e.last;
      if (age > o.maxAgeMs) {
        out.drop.push(e.key);
        continue;
      }
      var dead = alive ? !alive[e.tab] : age > o.staleMs;
      if (dead) out.report.push(e);
    }
    return out;
  }

  function uncleanReport(entry, now) {
    return compact({
      kind: "unclean_exit",
      tab: entry.tab,
      build: entry.build,
      page: clip(entry.page, 300),
      up: num((entry.last - entry.started) / 1000),
      ago: num((now - entry.last) / 1000),
      heap: entry.heap,
      heap_start: entry.heap_start,
      heap_max: entry.heap_max,
      vis: entry.vis,
    });
  }

  // Query string for the keepalive ping: the memory sample (job 3).
  function sampleQuery(ctx, now, heap, vis) {
    var parts = [
      "tab=" + encodeURIComponent(ctx.tab),
      "up=" + Math.round((now - ctx.started) / 1000),
      "build=" + encodeURIComponent(ctx.build || ""),
    ];
    if (typeof heap === "number") parts.push("heap=" + heap);
    if (vis) parts.push("vis=" + encodeURIComponent(vis));
    return parts.join("&");
  }

  // True when the server says a different build than the page was made by.
  // Either side unknown is never stale: a missing header must not nag.
  function isStale(pageBuild, serverBuild) {
    return !!pageBuild && !!serverBuild && pageBuild !== serverBuild;
  }

  // ------------------------------------------------------------------
  // Impure layer
  // ------------------------------------------------------------------

  var ctx = { tab: null, build: "", page: "", started: 0 };
  var state = {
    entry: null, // what this page last wrote
    registered: false, // written and not since removed by our own pagehide
    // Between pagehide and a bfcache restore. The browser fires
    // visibilitychange AFTER pagehide when navigating away; without this the
    // handler below would write the entry straight back, leaving a phantom
    // tab for the next page to report as dead.
    hiding: false,
    dismissed: false, // the viewer said "Later" to the update banner
    bannerShown: false,
    channel: null,
    probe: null, // tab ids that answered the current probe
  };
  var errorLimiter = makeLimiter(MAX_REPORTS);
  var reapLimiter = makeLimiter(MAX_REPORTS);

  function storage() {
    try {
      return window.localStorage || null;
    } catch (e) {
      return null; // blocked storage throws on access
    }
  }

  function perf() {
    return typeof performance !== "undefined" ? performance : null;
  }

  function visibility() {
    return typeof document !== "undefined" ? document.visibilityState || null : null;
  }

  function myKey() {
    return TAB_PREFIX + ctx.tab;
  }

  // Beacons survive the page going away and carry the session cookie, so
  // the server can name the user. A plain string body (text/plain) keeps
  // the request CORS-simple in every browser; the server parses it anyway.
  function send(report) {
    var body;
    try {
      body = JSON.stringify(report);
      if (navigator.sendBeacon && navigator.sendBeacon(REPORT_URL, body)) return true;
    } catch (e) {
      /* fall through to fetch */
    }
    try {
      fetch(REPORT_URL, {
        method: "POST",
        body: body,
        keepalive: true,
        credentials: "same-origin",
      }).catch(function () {});
      return true;
    } catch (e) {
      return false;
    }
  }

  function reportError(kind, info) {
    if (!errorLimiter.allow(kind + ":" + (info && info.message))) return false;
    return send(errorReport(kind, info, ctx, Date.now(), heapMB(perf())));
  }

  function onError(e) {
    // A failed <img>/<script> load also fires "error" on window (in the
    // capture phase) but is an Event, not an ErrorEvent, and has no message.
    if (!e || typeof e.message !== "string" || !e.message) return;
    var err = e.error || {};
    reportError("error", {
      message: e.message,
      source: e.filename,
      line: e.lineno,
      col: e.colno,
      stack: err.stack,
      expression: err.expression,
    });
  }

  function onRejection(e) {
    var r = e ? e.reason : undefined;
    var message = r && typeof r.message === "string" ? r.message : String(r);
    reportError("rejection", { message: message, stack: r && r.stack });
  }

  function writeEntry(vis) {
    var s = storage();
    if (!s || state.hiding) return false;
    var key = myKey();
    try {
      var existed = s.getItem(key) !== null;
      state.entry = nextEntry(state.entry, ctx, Date.now(), heapMB(perf()), vis || visibility());
      s.setItem(key, JSON.stringify(state.entry));
      // Our entry vanished although we never removed it: another page gave
      // this tab up for dead while the browser had it frozen. Tell the log.
      if (state.registered && !existed) {
        send(compact({
          kind: "resumed",
          tab: ctx.tab,
          build: ctx.build,
          page: ctx.page,
          up: num((Date.now() - ctx.started) / 1000),
        }));
      }
      state.registered = true;
      return true;
    } catch (e) {
      return false; // quota / privacy mode: diagnostics are best-effort
    }
  }

  function heartbeat() {
    return writeEntry();
  }

  function removeEntry() {
    state.hiding = true;
    state.registered = false;
    var s = storage();
    try {
      if (s) s.removeItem(myKey());
    } catch (e) {
      /* best-effort */
    }
  }

  function otherEntries() {
    var s = storage();
    var out = [];
    if (!s) return out;
    try {
      for (var i = 0; i < s.length; i++) {
        var key = s.key(i);
        if (key === myKey()) continue;
        var e = parseEntry(key, s.getItem(key));
        if (e) out.push(e);
        else if (key && key.indexOf(TAB_PREFIX) === 0) out.push({ key: key, tab: null, last: -Infinity, started: 0 });
      }
    } catch (e) {
      /* best-effort */
    }
    return out;
  }

  function onChannelMessage(ev) {
    var d = (ev && ev.data) || {};
    if (d.type === "ping" && d.from !== ctx.tab && state.channel) {
      state.channel.postMessage({ type: "pong", to: d.from, tab: ctx.tab });
    } else if (d.type === "pong" && d.to === ctx.tab && state.probe) {
      state.probe[d.tab] = true;
    }
  }

  // Ask every other open page of this site to answer; call back with the
  // set of ids that did, or null if there is no channel to ask on.
  function probeAlive(cb) {
    if (!state.channel) {
      cb(null);
      return;
    }
    state.probe = {};
    state.channel.postMessage({ type: "ping", from: ctx.tab });
    setTimeout(function () {
      var alive = state.probe;
      state.probe = null;
      cb(alive);
    }, PROBE_MS);
  }

  function reap(done) {
    var entries = otherEntries();
    if (!entries.length) {
      if (done) done([]);
      return;
    }
    probeAlive(function (alive) {
      var now = Date.now();
      var s = storage();
      var found = findUncleanTabs(entries, now, alive);
      var sent = [];
      try {
        for (var i = 0; i < found.drop.length; i++) s.removeItem(found.drop[i]);
        for (var j = 0; j < found.report.length; j++) {
          var e = found.report[j];
          // Gone while we were asking: that page closed cleanly after all.
          if (s.getItem(e.key) === null) continue;
          s.removeItem(e.key);
          if (e.tab && reapLimiter.allow(e.tab)) {
            var r = uncleanReport(e, now);
            send(r);
            sent.push(r);
          }
        }
      } catch (err) {
        /* best-effort */
      }
      if (done) done(sent);
    });
  }

  // --- job 4: new versions -------------------------------------------

  function banner() {
    return typeof document !== "undefined" ? document.getElementById("update-banner") : null;
  }

  function showUpdateBanner() {
    var el = banner();
    if (!el || state.dismissed) return false;
    if (!state.bannerShown) {
      var reload = el.querySelector("[data-update-reload]");
      var later = el.querySelector("[data-update-dismiss]");
      if (reload) reload.addEventListener("click", function () { location.reload(); });
      if (later) later.addEventListener("click", function () {
        state.dismissed = true;
        el.hidden = true;
      });
    }
    state.bannerShown = true;
    el.hidden = false;
    return true;
  }

  function noteServerBuild(serverBuild) {
    if (!isStale(ctx.build, serverBuild)) return false;
    return showUpdateBanner();
  }

  // For fetch() responses (keepalive.js hands us its ping's response).
  function noteResponse(resp) {
    try {
      noteServerBuild(resp && resp.headers ? resp.headers.get(BUILD_HEADER) : null);
    } catch (e) {
      /* never let diagnostics break a caller */
    }
  }

  // What keepalive.js appends to its ping.
  function currentSampleQuery() {
    return sampleQuery(ctx, Date.now(), heapMB(perf()), visibility());
  }

  function start() {
    var doc = document.documentElement;
    ctx.tab = newTabId();
    ctx.build = (doc && doc.getAttribute("data-build")) || "";
    ctx.page = location.pathname;
    ctx.started = Date.now();

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);

    try {
      if (typeof BroadcastChannel === "function") {
        state.channel = new BroadcastChannel(CHANNEL_NAME);
        state.channel.onmessage = onChannelMessage;
      }
    } catch (e) {
      state.channel = null;
    }

    writeEntry();
    setInterval(heartbeat, HEARTBEAT_MS);
    document.addEventListener("visibilitychange", function () { writeEntry(); });
    // Chrome freezes background tabs; note it, so a report about a tab that
    // was frozen when it disappeared reads as the browser's doing.
    document.addEventListener("freeze", function () { writeEntry("frozen"); });
    document.addEventListener("resume", function () { writeEntry(); });
    window.addEventListener("pagehide", removeEntry);
    // Restored from the back/forward cache: the same page, alive again.
    window.addEventListener("pageshow", function (e) {
      if (!e.persisted) return;
      state.hiding = false;
      writeEntry();
    });

    // Chrome sets this when it threw the tab away to save memory and the
    // viewer has now brought it back.
    if (document.wasDiscarded) {
      send(compact({ kind: "discarded", tab: ctx.tab, build: ctx.build, page: ctx.page }));
    }

    document.addEventListener("htmx:afterRequest", function (e) {
      var xhr = e && e.detail && e.detail.xhr;
      if (xhr && xhr.getResponseHeader) noteServerBuild(xhr.getResponseHeader(BUILD_HEADER));
    });

    setTimeout(function () { reap(); }, REAP_DELAY_MS);
  }

  var L7RTelemetry = {
    REPORT_URL: REPORT_URL,
    TAB_PREFIX: TAB_PREFIX,
    HEARTBEAT_MS: HEARTBEAT_MS,
    STALE_MS: STALE_MS,
    MAX_AGE_MS: MAX_AGE_MS,
    MAX_REPORTS: MAX_REPORTS,
    newTabId: newTabId,
    makeLimiter: makeLimiter,
    heapMB: heapMB,
    errorReport: errorReport,
    nextEntry: nextEntry,
    parseEntry: parseEntry,
    findUncleanTabs: findUncleanTabs,
    uncleanReport: uncleanReport,
    sampleQuery: sampleQuery,
    isStale: isStale,
    // impure, used by keepalive.js and the clicktests
    context: function () { return Object.assign({}, ctx); },
    currentSampleQuery: currentSampleQuery,
    noteResponse: noteResponse,
    noteServerBuild: noteServerBuild,
    heartbeat: heartbeat,
    reap: reap,
  };

  globalThis.L7RTelemetry = L7RTelemetry;
  /* node:coverage disable */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = L7RTelemetry;
  } else if (typeof window !== "undefined") {
    start();
  }
  /* node:coverage enable */
})();
