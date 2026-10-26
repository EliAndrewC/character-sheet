"""Assert that a rendered page's ``<div>`` tags balance.

An unmatched ``</div>`` does not fail loudly: the browser closes whatever div
is open above it, so everything after it lands in the wrong container. In the
sheet's roller that meant a modal included after ``modal_result.html`` fell
outside the ``diceRoller()`` Alpine scope and stayed ``x-cloak``ed forever.
Counting on the RENDERED page catches it wherever the stray tag came from,
and ``html.parser`` skips ``<script>`` bodies, so a ``'<div'`` inside JS is
not counted.
"""

from html.parser import HTMLParser


class _DivCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.stray_close = None

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == "div":
            self.depth -= 1
            if self.depth < 0 and self.stray_close is None:
                self.stray_close = self.getpos()


def assert_divs_balanced(html: str, page: str) -> None:
    counter = _DivCounter()
    counter.feed(html)
    counter.close()
    tip = (
        " Every template partial must close exactly the divs it opens; a parent "
        "that wraps an include closes its own wrapper. Find the culprit by counting "
        "per file: grep -o '<div\\b' FILE | wc -l vs grep -o '</div>' FILE | wc -l."
    )
    if counter.stray_close is not None:
        line, _col = counter.stray_close
        raise AssertionError(
            f"{page}: a </div> at rendered line {line} closes a div that was never "
            f"opened, so the elements after it sit in the wrong container." + tip
        )
    assert counter.depth == 0, (
        f"{page}: {counter.depth} <div> tag(s) are never closed." + tip
    )
