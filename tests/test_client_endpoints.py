"""Every URL the front end calls must be a live route.

The Group Details page's "Apply Unlucky" chip kept posting to
``POST /characters/{id}/track`` after that whole-state write was retired:
production answers it 404 and the clicktest server only keeps it as a
test-setup seam, so the chip silently did nothing and no test noticed. This
test greps every template and static script for the URLs they call
(``fetch``, ``hx-*``, ``action=``, ``htmx.ajax``, ``sendBeacon``, links,
``url`` variables, and ``combat_page.js``'s ``this.post`` / ``this.url``
helpers), and fails when one:

- matches no registered route,
- matches one only with the wrong HTTP method (a 405), or
- matches a route that production disables (gated on ``TEST_AUTH_BYPASS``),
  unless that call site is listed in ``TEST_ONLY_CALL_SITES``.

It is a grep, not a parser: a URL held in a variable it does not know about
is invisible to it. The floor test below keeps it from passing by finding
nothing.
"""

import inspect
import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
STATIC_JS = ROOT / "app" / "static" / "js"

# Call sites allowed to reach a test-only route, as (path relative to the
# repo, normalized URL). Each needs a reason.
TEST_ONLY_CALL_SITES = {
    # The tracking bridge's save(): exists only for clicktest setup (see
    # CLAUDE.md, "Tracking state is guarded by a revision").
    ("app/templates/character/partials/sheet/_tracking_js.html", "/characters/X/track"),
}

# The one gate that marks a route as test-only. Feature flags (IMPORT_ENABLED,
# unset tokens answering 503) are deliberately NOT this.
TEST_ONLY_GATE = re.compile(r"""TEST_AUTH_BYPASS["']\s*\)\s*!=\s*["']true["']""")

# Helpers that take a path relative to a fixed prefix, per file.
RELATIVE_HELPERS = {
    "app/static/js/combat_page.js": {
        "prefix": "/groups/X/combat",
        "calls": {r"this\.post": "POST", r"this\.url": None},
    },
}

_STR = r"""(?:"[^"\n]*"|'[^'\n]*'|`[^`\n]*`)"""
_TERM = r"""(?:""" + _STR + r"""|[\w.$\[\]]+(?:\([^()\n]*\))?)"""
_CONCAT = re.compile(_STR + r"(?:\s*\+\s*" + _TERM + r")*")

_CALLS = [
    # (regex up to the URL expression, method or None, where to find a method)
    (re.compile(r"""\bfetch\s*\(\s*"""), "GET", "fetch"),
    (re.compile(r"""navigator\.sendBeacon\s*\(\s*"""), "POST", None),
    (re.compile(r"""htmx\.ajax\s*\(\s*['"]([A-Za-z]+)['"]\s*,\s*"""), "group", None),
    (re.compile(r"""\bhx-(get|post|put|patch|delete)\s*=\s*"""), "group", None),
    (re.compile(r"""(?<![\w-])(?::|x-bind:)?action\s*=\s*"""), "form", None),
    (re.compile(r"""(?<![\w-])(?::|x-bind:)?(?:href|src)\s*=\s*"""), "GET", None),
    (re.compile(r"""\b(?:const|let|var)\s+\w*(?:url|URL|Url)\w*\s*=\s*"""), None, None),
]


def normalize(expr: str) -> str:
    """A URL expression with every interpolation replaced by ``X``.

    ``'/characters/' + id + '/track'`` and
    ``/characters/{{ c.id }}/track`` both become ``/characters/X/track``.
    """
    out = ""
    for part in re.findall(_STR + r"|[^+\s]+", expr):
        if part[0] in "\"'`":
            out += re.sub(r"\$\{[^}]*\}", "X", part[1:-1])
        else:
            out += "X"
    out = re.sub(r"\{\{.*?\}\}", "X", out)
    out = re.sub(r"\{%.*?%\}", "", out)
    return re.split(r"[?#]", out, maxsplit=1)[0]


def _fetch_method(rest: str) -> str:
    # The options object follows the URL; stop at the call's end or the next
    # fetch so one call cannot borrow another's method.
    window = re.split(r"\bfetch\s*\(|\)\s*;", rest[:400], maxsplit=1)[0]
    m = re.search(r"""method\s*:\s*['"]([A-Za-z]+)['"]""", window)
    if m:
        return m.group(1).upper()
    if re.search(r"method\s*:", window):
        return None  # a variable method: unknown
    return "GET"


def _form_method(text: str, pos: int) -> str:
    start = text.rfind("<", 0, pos)
    tag = text[start:text.find(">", pos) + 1]
    if not tag.startswith("<form"):
        return None
    m = re.search(r"""\bmethod\s*=\s*['"]?(\w+)""", tag)
    return (m.group(1) if m else "GET").upper()


def extract_calls(rel: str, text: str):
    """Yield ``(line, url, method)`` for each URL ``text`` calls.

    ``method`` is None when it cannot be told from the source.
    """
    found = []
    for pattern, method, how in _CALLS:
        for m in pattern.finditer(text):
            rest = text[m.end():]
            cm = _CONCAT.match(rest)
            if not cm:
                continue
            url = normalize(cm.group(0))
            if method == "group":
                meth = m.group(1).upper()
            elif method == "form":
                meth = _form_method(text, m.start())
            elif how == "fetch":
                meth = _fetch_method(rest[cm.end():])
            else:
                meth = method
            found.append((m.start(), url, meth))
    helpers = RELATIVE_HELPERS.get(rel)
    if helpers:
        for call, meth in helpers["calls"].items():
            for m in re.finditer(call + r"\s*\(\s*", text):
                cm = _CONCAT.match(text[m.end():])
                if cm:
                    found.append((m.start(), helpers["prefix"] + normalize(cm.group(0)), meth))
    for pos, url, meth in found:
        if url.startswith("/") and not url.startswith(("//", "/static/")):
            yield text.count("\n", 0, pos) + 1, url, meth


def client_files():
    files = sorted(TEMPLATES.rglob("*.html"))
    files += sorted(p for p in STATIC_JS.rglob("*.js")
                    if "vendor" not in p.parts and not p.name.endswith(".min.js"))
    return files


def all_calls():
    for path in client_files():
        rel = str(path.relative_to(ROOT))
        for line, url, meth in extract_calls(rel, path.read_text()):
            yield rel, line, url, meth


def _routes():
    out = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        if not methods:
            continue  # mounts (static files)
        rx = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$")
        try:
            test_only = bool(TEST_ONLY_GATE.search(inspect.getsource(r.endpoint)))
        except (OSError, TypeError):  # pragma: no cover - framework-built endpoints
            test_only = False
        out.append((rx, r.path, methods, test_only))
    return out


ROUTES = _routes()


def _url_pattern(url: str) -> re.Pattern:
    # An X in the middle stands for one segment; a trailing X for an open
    # tail ('/characters/' + id may be '5' or '5/edit').
    if url.endswith("X"):
        body, tail = url[:-1], ".+"
    else:
        body, tail = url, ""
    return re.compile("^" + re.escape(body).replace("X", "[^/]+") + tail + "$")


def matching_routes(url: str):
    """The routes a normalized client URL can reach."""
    candidates = {url, url.rstrip("/") or "/"}
    exact = [r for r in ROUTES if any(r[0].match(c) for c in candidates)]
    if exact:
        return exact
    # Compare against the route template with its params written as X, so a
    # client placeholder may stand where the route has a parameter.
    pattern = _url_pattern(url)
    return [r for r in ROUTES if pattern.match(re.sub(r"\{[^}]+\}", "X", r[1]))]


FIX_HINT = (
    "If a template or script still calls a retired route, switch it to the "
    "current one (whole-state /track writes became the tracking op "
    "POST /characters/{id}/track/op, see CLAUDE.md 'Tracking state is "
    "guarded by a revision'). If the call is deliberately test-only, add "
    "(file, url) to TEST_ONLY_CALL_SITES in tests/test_client_endpoints.py "
    "with a reason."
)


def problems(calls):
    """Human-readable failures for ``(file, line, url, method)`` calls."""
    out = []
    for rel, line, url, meth in calls:
        routes = matching_routes(url)
        where = f"{rel}:{line} {meth or '?'} {url}"
        if not routes:
            out.append(f"{where}: no route matches this URL")
            continue
        if meth and not any(meth in r[2] for r in routes):
            allowed = sorted({m for r in routes for m in r[2]})
            out.append(f"{where}: route allows only {', '.join(allowed)} (a 405)")
            continue
        live = [r for r in routes if not r[3] and (not meth or meth in r[2])]
        if not live and (rel, url) not in TEST_ONLY_CALL_SITES:
            out.append(f"{where}: {routes[0][1]} is test-only "
                       "(production answers 404)")
    return out


def _report(found):
    return "\n".join(found) + "\n\n" + FIX_HINT


def test_every_client_url_is_a_live_route():
    found = problems(all_calls())
    assert not found, _report(found)


def test_the_extractor_finds_the_call_sites_it_should():
    """A floor, so a regex that stops matching cannot pass by finding nothing."""
    calls = list(all_calls())
    assert len(calls) >= 100
    urls = {url for _, _, url, _ in calls}
    assert "/characters/X/track/op" in urls
    assert "/groups/X/combat/start" in urls  # combat_page.js's this.post
    assert "/client-log" in urls  # telemetry's REPORT_URL variable
    assert ("app/templates/group_summary.html", "/characters/X/track/op", "POST") in {
        (rel, url, meth) for rel, _, url, meth in calls}


def test_a_call_to_the_retired_track_route_is_flagged():
    """The bug this test exists for, replayed in a file not on the allow-list."""
    text = '''<div x-data='{ async apply() {
        const resp = await fetch("/characters/{{ c.id }}/track", {
            method: "POST", body: "{}" });
    } }'></div>'''
    calls = [("app/templates/group_summary.html", line, url, meth)
             for line, url, meth in extract_calls("app/templates/group_summary.html", text)]
    assert calls == [("app/templates/group_summary.html", 2, "/characters/X/track", "POST")]
    found = problems(calls)
    assert found == ["app/templates/group_summary.html:2 POST /characters/X/track: "
                     "/characters/{char_id}/track is test-only (production answers 404)"]
    report = _report(found)
    assert "POST /characters/{id}/track/op" in report
    assert "TEST_ONLY_CALL_SITES" in report


def test_unknown_urls_and_wrong_methods_are_flagged():
    js = ('fetch("/characters/" + id + "/no-such-thing", {method: "POST"});\n'
          'fetch("/characters/" + id + "/publish");\n'
          'this.post("/start", {});\n')
    rel = "app/static/js/combat_page.js"
    calls = [(rel, line, url, meth) for line, url, meth in extract_calls(rel, js)]
    found = problems(calls)
    assert len(found) == 2
    assert found[0].endswith("no route matches this URL")
    assert "/characters/X/publish" in found[1] and "(a 405)" in found[1]


def test_a_mid_url_placeholder_matches_one_segment_only():
    # A placeholder between literals stands for exactly one segment...
    assert not _url_pattern("/characters/X/X/annotation").match("/characters/X/rolls/X/annotation")
    assert _url_pattern("/characters/X/rolls/X/annotation").match("/characters/X/rolls/X/annotation")
    # ...while a trailing one is an open tail ('/characters/' + id).
    assert _url_pattern("/characters/X").match("/characters/X/rolls/X/annotation")


def test_every_test_only_route_is_known():
    """Every route behind the TEST_AUTH_BYPASS gate is one this test knows.

    A new test seam is fine; the point is that adding one is noticed here,
    and that the gate regex has not drifted from how routes spell it.
    """
    gated = sorted(path for _, path, _, test_only in ROUTES if test_only)
    assert gated == ["/characters/{char_id}/track"]
    sources = "\n".join(p.read_text() for p in (ROOT / "app" / "routes").glob("*.py"))
    assert len(TEST_ONLY_GATE.findall(sources)) == len(gated)
