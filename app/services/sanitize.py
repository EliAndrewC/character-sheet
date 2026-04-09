"""HTML sanitization for user-supplied rich text content.

Uses bleach with a strict allowlist of display tags. Strips:
  * <script>, <style>, <iframe>, <object>, <embed>, <link>, <meta>, <form>,
    <input>, and other unsafe elements
  * All inline event handlers (onclick, onload, onerror, ...)
  * Non-http(s)/mailto link protocols (e.g. javascript:, data:)

Allows:
  * Block tags (p, h1-h6, blockquote, pre, hr, ul, ol, li, table, ...)
  * Inline formatting (b/strong, i/em, u, s/del, code, sub, sup, mark, span)
  * Links with href, title, target, rel
  * Images (passive resource, no JavaScript) with src/alt/title/width/height
"""

from __future__ import annotations

import re

import bleach


# Tags whose entire contents (including the inner text) we want to remove,
# not just the surrounding tag. Bleach with ``strip=True`` only removes the
# tag, leaving the inner text behind, which would dump CSS or JavaScript code
# as plain text into the rendered sheet. We pre-process to drop these blocks
# entirely before handing the rest to bleach.
_DROP_BLOCK_RE = re.compile(
    r"<(?P<tag>script|style|iframe|object|embed|noscript|template)\b[^>]*>"
    r".*?</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Also kill self-closing or unclosed variants of the same dangerous tags.
_DROP_SELF_RE = re.compile(
    r"<(script|style|iframe|object|embed|noscript|template)\b[^>]*/?>",
    re.IGNORECASE,
)


ALLOWED_TAGS = frozenset({
    "a", "abbr", "b", "blockquote", "br", "code", "del", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "kbd", "li", "mark", "ol", "p", "pre", "s", "small", "span",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
    "thead", "tr", "u", "ul",
})

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "abbr": ["title"],
    "img": ["src", "alt", "title", "width", "height"],
    "th": ["scope", "colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "ol": ["start", "type"],
    "li": ["value"],
    # Quill emits these on most blocks for indentation/alignment via inline classes;
    # we deliberately do NOT allow class/style to keep the surface area minimal.
}

ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto"})


def sanitize_html(html: str) -> str:
    """Return a sanitized version of *html* safe for embedding in templates.

    Empty / None input returns an empty string.
    """
    if not html:
        return ""
    # First strip script/style/iframe/etc. INCLUDING their contents, so that
    # the inner CSS or JS source isn't dumped as plain text by bleach.
    pre_cleaned = _DROP_BLOCK_RE.sub("", html)
    pre_cleaned = _DROP_SELF_RE.sub("", pre_cleaned)
    cleaned = bleach.clean(
        pre_cleaned,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,            # remove disallowed tags entirely (don't escape)
        strip_comments=True,
    )
    return cleaned


def sanitize_sections(sections):
    """Sanitize a list of section dicts in-place style.

    Each input section is a dict with at least ``label`` and ``html``. Returns a
    new list of dicts (does not mutate the input). Empty sections (no label
    AND no html after sanitization) are dropped. Labels are stripped of
    leading/trailing whitespace and capped at 128 chars.
    """
    if not sections:
        return []
    out = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        label = (s.get("label") or "").strip()[:128]
        html = sanitize_html(s.get("html") or "")
        # Drop sections that are entirely empty (no label and only whitespace markup)
        text_only = bleach.clean(html, tags=set(), strip=True).strip() if html else ""
        if not label and not text_only:
            continue
        out.append({"label": label, "html": html})
    return out
