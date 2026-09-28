"""Force the dice in a clicktest - in the browser AND on the server.

The server rolls the sheet's dice now (server-rolls-design), so stubbing
``Math.random`` alone no longer reaches most rolls. ``force_dice`` does both:
the ``Math.random`` stub (for flows still rolled in the browser until their
phase moves) and the ``X-Test-Dice`` header, which the clicktest server
(``TEST_AUTH_BYPASS=true``) honours by scripting its roller. Values cycle.
"""


def force_dice(page, values):
    if isinstance(values, int):
        values = [values]
    seq = [((v - 1) / 10) + 0.001 for v in values]
    page.evaluate(f"""() => {{
        if (!window._origRandom) window._origRandom = Math.random;
        const seq = {seq!r};
        let i = 0;
        Math.random = () => {{ const v = seq[i % seq.length]; i++; return v; }};
    }}""")
    page.set_extra_http_headers({"X-Test-Dice": ",".join(str(v) for v in values)})


def restore_dice(page):
    page.evaluate("if (window._origRandom) { Math.random = window._origRandom; window._origRandom = null; }")
    page.set_extra_http_headers({})
