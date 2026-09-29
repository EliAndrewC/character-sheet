"""Force the dice in a clicktest.

The server rolls every die the sheet shows (server-rolls-design), so the
dice are forced there: the clicktest server (``TEST_AUTH_BYPASS=true``)
honours the ``X-Test-Dice`` header by scripting its roller. Values cycle.
"""


def force_dice(page, values):
    if isinstance(values, int):
        values = [values]
    page.set_extra_http_headers({"X-Test-Dice": ",".join(str(v) for v in values)})


def restore_dice(page):
    page.set_extra_http_headers({})
