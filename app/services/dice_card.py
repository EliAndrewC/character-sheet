"""Render a roll-result as a PNG "dice card" for clipboard sharing.

The card matches the View Sheet's dice aesthetic (same kite path, gold
treatment for 10s and any reroll-tens follow-ups, parchment ground)
and is sized snug to its content - simple skill rolls produce a small
card, longer rolls with stacked banked bonuses grow as needed and the
bonus list wraps into two columns once it gets long.

Composition is done in SVG (which the View Sheet already speaks for
dice) and rasterized with cairosvg, so adding the feature doesn't pull
in a headless-browser dep. Results are cached in an LRU keyed by a
hash of the input payload - clicking Copy twice on the same roll skips
the work.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

import cairosvg

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Palette - lifted from app/templates/base.html so the card matches the
# View Sheet's dice styling exactly.
# ---------------------------------------------------------------------------

PARCHMENT = "#f5f0e8"
INK = "#2c1810"
ACCENT = "#8b0000"
GOLD_STROKE = "#d4a017"
GOLD_FILL = "#fff7e0"
DIE_STROKE = "rgba(44,24,16,0.55)"

# Canonical d10 kite path, viewBox 0 0 100 116 (same path the View Sheet uses).
DIE_PATH = (
    "M 54.59 6.55 L 95.41 64.85 Q 100 71.4 94.03 76.73 "
    "L 55.97 110.67 Q 50 116 44.03 110.67 L 5.97 76.73 "
    "Q 0 71.4 4.59 64.85 L 45.41 6.55 Q 50 0 54.59 6.55 Z"
)


# ---------------------------------------------------------------------------
# Layout constants - mirror the mockup script in dice-card-mockups/.
# ---------------------------------------------------------------------------

PAD = 22                          # outer margin from card edge to content
BORDER_INSET = 8                  # inner border offset from the card edge
DIE_W = 70                        # rendered pixel width of a single die
DIE_H = 81                        # 70 * 116/100 ≈ 81 (kite aspect)
DIE_TEXT_SIZE_SINGLE = 64
DIE_TEXT_SIZE_DOUBLE = 50         # 10s shrink to fit the narrow kite
CHAIN_GAP = 6                     # gap between dice in a reroll chain
CELL_GAP = 18                     # gap between separate dice cells in a row

# Bonus typography
BONUS_FONT_SIZE = 16
BONUS_ROW_HEIGHT = 22
BONUS_AMOUNT_LABEL_GAP = 8
BONUS_INTER_COL_GAP = 32
BONUS_WRAP_THRESHOLD = 5          # 5+ bonuses fan into two columns

# Alternative-totals typography. A touch smaller than the bonuses
# block since this section is supporting context rather than the
# primary breakdown.
ALT_FONT_SIZE = 14
ALT_ROW_HEIGHT = 20
ALT_AMOUNT_LABEL_GAP = 8
ALT_IF_ALL_LABEL = "if all of the above"

# "Details" bullets - free-text notes the client mirrors from the
# on-screen result panel's small print (void points spent, the 5th Dan
# +per-VP combat bonus, the above-10k10 overflow, Otherworldliness,
# Conviction, a Lucky/Togashi reroll, etc.). Unlike the bonus block
# these have no amount column - each entry is a full sentence already
# formatted by the sheet - so they render as a left-aligned bulleted
# list within a centered block.
EXTRA_FONT_SIZE = 14
EXTRA_ROW_HEIGHT = 20
EXTRA_BULLET = "• "

# Limits applied to incoming payloads - prevent abuse (huge SVGs) and
# clip patently invalid input rather than failing later.
MAX_DICE_PER_ROW = 30
MAX_CHAIN_PER_CELL = 12
MAX_BONUSES = 30
MAX_ALTERNATIVES = 20
MAX_EXTRAS = 20
MAX_TEXT_LEN = 200

# In-memory LRU. Each PNG is small (~30-50 KB); the cap keeps total
# memory bounded at ~5-8 MB even on the small Fly machine.
_LRU_MAX = 128


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Die:
    """One die face. ``is_ten`` styles the face like the View Sheet's
    is-ten class (gold ground, accent text); ``is_reroll`` is treated
    the same way so a 10 -> X chain reads as one matching gold
    cluster."""
    value: int
    is_ten: bool = False
    is_reroll: bool = False


@dataclass(frozen=True)
class DieCell:
    """One conceptual die slot. Chained rerolls share a cell with their
    originating 10; the cell renders its dice closer together than the
    inter-cell gap so the chain stays visually grouped."""
    parts: Tuple[Die, ...]


@dataclass(frozen=True)
class Bonus:
    label: str
    amount: int


@dataclass(frozen=True)
class Alternative:
    """One "Alternative totals" row. ``extra_flat`` is the delta applied
    on top of the unconditional roll total when the condition holds
    (e.g. ``+10 vs Wasp``, ``-10 in the eyes of those who judge the
    unkempt``). The card renders ``total + extra_flat`` next to the
    label and, when 2+ rows are present, an "if all of the above"
    summing row."""
    label: str
    extra_flat: int


@dataclass(frozen=True)
class RollCard:
    title: str
    formula: str
    kept: Tuple[DieCell, ...] = field(default_factory=tuple)
    dropped: Tuple[DieCell, ...] = field(default_factory=tuple)
    bonuses: Tuple[Bonus, ...] = field(default_factory=tuple)
    total: int = 0
    footer: Optional[str] = None
    alternatives: Tuple[Alternative, ...] = field(default_factory=tuple)
    # Free-text "details" bullets mirroring the on-screen result
    # panel's small print (void spent, overflow, Lucky, etc.). Render
    # below the numeric bonus block; each is a full sentence.
    extras: Tuple[str, ...] = field(default_factory=tuple)
    # Whether to render the "TOTAL <n>" trophy block at the bottom of
    # the card. Initiative rolls suppress this because there's no
    # meaningful sum across action dice - each die is its own
    # standalone phase number. The ``footer`` still renders below
    # where the trophy would have been so callers can label the dice
    # rows ("Action dice").
    show_total: bool = True
    # Attribution banner: set ONLY when the roll was made by someone who
    # is not the character's owner (a viewer rolling on another player's
    # sheet, or an anonymous "unknown user"). The /roll-image route sets
    # this server-side from the session; None means the owner rolled it
    # (the normal case) and no banner renders.
    rolled_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Payload -> RollCard
# ---------------------------------------------------------------------------


def _coerce_text(value, default: str = "") -> str:
    """Best-effort text sanitization for user-provided strings.

    Strings are clipped at MAX_TEXT_LEN to keep the SVG bounded.
    Anything non-string falls back to the default - we never raise
    here because the payload comes from the client and bad shapes
    shouldn't crash the renderer; the resulting card will just look
    a little off, which is fine for a copy-to-clipboard feature."""
    if not isinstance(value, str):
        return default
    s = value.strip()
    if len(s) > MAX_TEXT_LEN:
        s = s[:MAX_TEXT_LEN].rstrip() + "..."
    return s


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_cells(raw_list, default_is_ten=False) -> Tuple[DieCell, ...]:
    """Convert an incoming list of cell dicts into a tuple of DieCell.

    Accepted shapes per cell:
      - ``{"parts": [10, 5]}``   - explicit chain
      - ``{"value": 7}``         - single die
      - bare int                 - single die
    The first part of a chain is treated as the originating face (10
    in practice); the rest are rerolls. Both render with the gold
    treatment per the design decision in the mockup chat.
    """
    if not isinstance(raw_list, list):
        return ()
    cells: List[DieCell] = []
    for raw in raw_list[:MAX_DICE_PER_ROW]:
        if isinstance(raw, dict):
            parts_raw = raw.get("parts")
            if parts_raw is None:
                v = raw.get("value")
                parts_raw = [v] if v is not None else []
        elif isinstance(raw, int):
            parts_raw = [raw]
        else:
            continue
        if not isinstance(parts_raw, list) or not parts_raw:
            continue
        parts: List[Die] = []
        for i, v in enumerate(parts_raw[:MAX_CHAIN_PER_CELL]):
            iv = _coerce_int(v, 0)
            if iv <= 0:
                continue
            parts.append(Die(
                value=iv,
                is_ten=(i == 0 and iv >= 10),
                is_reroll=(i > 0),
            ))
        if parts:
            cells.append(DieCell(parts=tuple(parts)))
    return tuple(cells)


def _coerce_bonuses(raw_list) -> Tuple[Bonus, ...]:
    if not isinstance(raw_list, list):
        return ()
    out: List[Bonus] = []
    for raw in raw_list[:MAX_BONUSES]:
        if not isinstance(raw, dict):
            continue
        amount = _coerce_int(raw.get("amount"), 0)
        label = _coerce_text(raw.get("label"))
        # Drop zero-amount no-label entries - they'd render as a
        # phantom row with nothing useful.
        if amount == 0 and not label:
            continue
        out.append(Bonus(label=label, amount=amount))
    return tuple(out)


def _coerce_alternatives(raw_list) -> Tuple[Alternative, ...]:
    """Normalise a list of conditional ``{label, extra_flat}`` entries.

    Mirrors ``_coerce_bonuses`` but uses ``extra_flat`` (not ``amount``)
    to match the existing wire format on the View Sheet. Entries with
    no label or no delta are dropped - those would render as
    contentless rows."""
    if not isinstance(raw_list, list):
        return ()
    out: List[Alternative] = []
    for raw in raw_list[:MAX_ALTERNATIVES]:
        if not isinstance(raw, dict):
            continue
        extra = _coerce_int(raw.get("extra_flat"), 0)
        label = _coerce_text(raw.get("label"))
        if extra == 0 and not label:
            continue
        out.append(Alternative(label=label, extra_flat=extra))
    return tuple(out)


def _coerce_extras(raw_list) -> Tuple[str, ...]:
    """Normalise the free-text "details" bullets the client mirrors
    from the on-screen result panel (void spent, overflow, Lucky, ...).

    Each entry is a full sentence; non-strings and blanks are dropped
    (``_coerce_text`` returns "" for them), and the list is clipped to
    ``MAX_EXTRAS`` so a hostile payload can't balloon the card."""
    if not isinstance(raw_list, list):
        return ()
    out: List[str] = []
    for raw in raw_list[:MAX_EXTRAS]:
        text = _coerce_text(raw)
        if text:
            out.append(text)
    return tuple(out)


def parse_payload(payload: dict) -> RollCard:
    """Build a ``RollCard`` from an untrusted client payload.

    Validation is intentionally lenient - missing fields fall back to
    empty strings / empty tuples - because the renderer is only ever
    a convenience surface (copy-to-clipboard) and we'd rather produce
    a stripped-down card than refuse the request."""
    if not isinstance(payload, dict):
        payload = {}
    return RollCard(
        title=_coerce_text(payload.get("title")) or "Roll",
        formula=_coerce_text(payload.get("formula")),
        kept=_coerce_cells(payload.get("kept")),
        dropped=_coerce_cells(payload.get("dropped")),
        bonuses=_coerce_bonuses(payload.get("bonuses")),
        total=_coerce_int(payload.get("total"), 0),
        footer=_coerce_text(payload.get("footer")) or None,
        alternatives=_coerce_alternatives(payload.get("alternatives")),
        extras=_coerce_extras(payload.get("extras")),
        rolled_by=_coerce_text(payload.get("rolled_by")) or None,
        # Default True so all existing roll types keep their TOTAL
        # trophy. Initiative payloads pass ``show_total: false`` to
        # suppress it.
        show_total=payload.get("show_total") is not False,
    )


# ---------------------------------------------------------------------------
# SVG primitives
# ---------------------------------------------------------------------------


_FAMILY_CSS = {
    "serif": "Georgia, 'Iowan Old Style', Palatino, serif",
    "sans": "ui-sans-serif, system-ui, sans-serif",
    "mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
}


def _text(x: float, y: float, content: str, size: float,
          weight: int = 400, fill: str = INK, anchor: str = "middle",
          family: str = "serif", opacity: float = 1.0,
          letter_spacing: float = 0) -> str:
    """One <text> element. Content is XML-escaped so embedded angle
    brackets / quotes in player-typed labels can't break the SVG."""
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="{_FAMILY_CSS[family]}" font-weight="{weight}" '
        f'font-size="{size}" fill="{fill}" opacity="{opacity}" '
        f'letter-spacing="{letter_spacing}">{xml_escape(content)}</text>'
    )


def _hr(y: float, card_w: float) -> str:
    return (
        f'<line x1="{PAD}" y1="{y}" x2="{card_w - PAD}" y2="{y}" '
        f'stroke="{INK}" stroke-width="1" opacity="0.18"/>'
    )


def _die_svg(x: float, y: float, die: Die, opacity: float = 1.0) -> str:
    """One <svg> die nested into the parent canvas. 10s and any reroll
    dice both use the gold treatment so a chain reads as a single
    cluster."""
    if die.is_ten or die.is_reroll:
        fill, stroke, text_fill = GOLD_FILL, GOLD_STROKE, ACCENT
    else:
        fill, stroke, text_fill = "#ffffff", DIE_STROKE, INK
    text_size = DIE_TEXT_SIZE_DOUBLE if die.value >= 10 else DIE_TEXT_SIZE_SINGLE
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{DIE_W}" height="{DIE_H}" '
        f'viewBox="0 0 100 116" opacity="{opacity:.2f}">'
        f'<path d="{DIE_PATH}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="5" stroke-linejoin="round"/>'
        f'<text x="50" y="65" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" '
        f'font-weight="700" font-size="{text_size}" fill="{text_fill}">'
        f'{die.value}</text>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _cell_width(cell: DieCell) -> float:
    n = len(cell.parts)
    return n * DIE_W + (n - 1) * CHAIN_GAP


def _row_width(cells: Tuple[DieCell, ...]) -> float:
    if not cells:
        return 0
    return sum(_cell_width(c) for c in cells) + CELL_GAP * (len(cells) - 1)


def _row_svg(cells: Tuple[DieCell, ...], cx: float, top_y: float,
             opacity: float = 1.0) -> str:
    if not cells:
        return ""
    x = cx - _row_width(cells) / 2
    out = []
    for cell in cells:
        intra_x = x
        for part in cell.parts:
            out.append(_die_svg(intra_x, top_y, part, opacity))
            intra_x += DIE_W + CHAIN_GAP
        x += _cell_width(cell) + CELL_GAP
    return "".join(out)


def _measure_text(content: str, size: float, weight: int = 400,
                  family: str = "serif") -> float:
    """Heuristic text-width estimate.

    Used during layout to size the card snug to its content. We can't
    use real font metrics at render time - cairosvg picks whatever
    font the host has and the player's browser sees something else -
    so per-family average-character-width factors with an ~8% safety
    pad are enough to keep the layout from clipping in either
    rasterizer.
    """
    if family == "mono":
        avg = 0.60
    elif family == "sans":
        avg = 0.58 if weight >= 600 else 0.54
    else:
        avg = 0.55 if weight >= 600 else 0.50
    return len(content) * size * avg * 1.08


def _amount_str(bonus: Bonus) -> str:
    return ("+" if bonus.amount >= 0 else "") + str(bonus.amount)


def _amount_w(bonus: Bonus) -> float:
    return _measure_text(_amount_str(bonus), BONUS_FONT_SIZE,
                         weight=700, family="mono")


def _label_w(bonus: Bonus) -> float:
    return _measure_text(bonus.label, BONUS_FONT_SIZE,
                         weight=400, family="serif")


def _plan_bonus_layout(card: RollCard) -> dict:
    """Compute bonus-block geometry. The block centers on the card;
    within the block each column right-aligns its amounts and
    left-aligns its labels so a stack of "+5  label" rows reads as a
    clean column. With 5+ bonuses the block fans into two columns;
    fewer collapse to a single centered column."""
    bonuses = card.bonuses
    n = len(bonuses)
    if n == 0:
        return {"mode": "none", "block_w": 0.0, "rows": 0}
    if n < BONUS_WRAP_THRESHOLD:
        max_amount = max(_amount_w(b) for b in bonuses)
        max_label = max(_label_w(b) for b in bonuses)
        return {
            "mode": "single",
            "rows": n,
            "max_amount_w": max_amount,
            "block_w": max_amount + BONUS_AMOUNT_LABEL_GAP + max_label,
        }
    col1_size = (n + 1) // 2
    col1 = bonuses[:col1_size]
    col2 = bonuses[col1_size:]
    c1_amount = max(_amount_w(b) for b in col1)
    c1_label = max(_label_w(b) for b in col1)
    c2_amount = max(_amount_w(b) for b in col2)
    c2_label = max(_label_w(b) for b in col2)
    col1_w = c1_amount + BONUS_AMOUNT_LABEL_GAP + c1_label
    col2_w = c2_amount + BONUS_AMOUNT_LABEL_GAP + c2_label
    return {
        "mode": "dual",
        "rows": max(len(col1), len(col2)),
        "col1": col1,
        "col2": col2,
        "col1_w": col1_w,
        "col2_w": col2_w,
        "c1_amount": c1_amount,
        "c2_amount": c2_amount,
        "block_w": col1_w + BONUS_INTER_COL_GAP + col2_w,
    }


def _plan_alternative_layout(card: RollCard) -> dict:
    """Compute the alternative-totals block geometry. Each row reads
    "[total + extra_flat] [label]"; with 2+ alts a summing "if all of
    the above" row is appended. Returns ``{"rows": N, "block_w": W}``
    where ``rows`` is the visible row count and ``block_w`` is the
    widest row's pixel span (so the card-width pass can include it)."""
    alts = card.alternatives
    if not alts:
        return {"rows": 0, "block_w": 0.0, "max_amount_w": 0.0}
    base = card.total
    # Width of each row's left column = mono total. Both the per-alt
    # rows and the "if all" row contribute candidate widths.
    amount_widths = [
        _measure_text(str(base + a.extra_flat), ALT_FONT_SIZE,
                      weight=700, family="mono")
        for a in alts
    ]
    label_widths = [
        _measure_text(a.label, ALT_FONT_SIZE, weight=400, family="serif")
        for a in alts
    ]
    rows = len(alts)
    if len(alts) > 1:
        total_all = base + sum(a.extra_flat for a in alts)
        amount_widths.append(
            _measure_text(str(total_all), ALT_FONT_SIZE,
                          weight=700, family="mono")
        )
        label_widths.append(
            _measure_text(ALT_IF_ALL_LABEL, ALT_FONT_SIZE,
                          weight=400, family="serif")
        )
        rows += 1
    max_amount = max(amount_widths)
    max_label = max(label_widths)
    return {
        "rows": rows,
        "max_amount_w": max_amount,
        "block_w": max_amount + ALT_AMOUNT_LABEL_GAP + max_label,
    }


def _plan_extras_layout(card: RollCard) -> dict:
    """Compute the details-bullets block geometry. Each row is a full
    "• <sentence>" line; the block is as wide as its longest line so
    the card-width pass can fit it. Returns ``{"rows": N,
    "block_w": W}``."""
    extras = card.extras
    if not extras:
        return {"rows": 0, "block_w": 0.0}
    width = max(
        _measure_text(EXTRA_BULLET + e, EXTRA_FONT_SIZE,
                      weight=400, family="serif")
        for e in extras
    )
    return {"rows": len(extras), "block_w": width}


def _content_width(card: RollCard, bonus_plan: dict, alt_plan: dict,
                   extras_plan: dict) -> float:
    return max(
        _measure_text(card.title, 34, weight=700, family="serif"),
        _measure_text(card.formula, 18, weight=400, family="serif"),
        _row_width(card.kept),
        _row_width(card.dropped),
        bonus_plan["block_w"],
        extras_plan["block_w"],
        _measure_text(str(card.total), 56, weight=700, family="serif"),
        _measure_text(card.footer or "", 14, weight=400, family="serif"),
        (_measure_text("Roll made by " + card.rolled_by, 15, weight=700,
                       family="sans") if card.rolled_by else 0),
        alt_plan["block_w"],
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _bonus_line_svg(anchor_x: float, y: float, bonus: Bonus) -> str:
    """One bonus row. ``amount`` right-anchored at
    ``anchor_x - BONUS_AMOUNT_LABEL_GAP`` and ``label`` left-anchored
    at ``anchor_x`` produces a clean two-column readout when stacked."""
    return (
        _text(anchor_x - BONUS_AMOUNT_LABEL_GAP, y, _amount_str(bonus),
              size=BONUS_FONT_SIZE, weight=700, anchor="end",
              family="mono", fill=ACCENT)
        + _text(anchor_x, y, bonus.label, size=BONUS_FONT_SIZE,
                weight=400, anchor="start")
    )


def _alt_line_svg(anchor_x: float, y: float, total_str: str, label: str) -> str:
    """One alternative-totals row. Total in mono accent right-anchored
    before the gap; label in serif left-anchored at the anchor."""
    return (
        _text(anchor_x - ALT_AMOUNT_LABEL_GAP, y, total_str,
              size=ALT_FONT_SIZE, weight=700, anchor="end",
              family="mono", fill=ACCENT)
        + _text(anchor_x, y, label, size=ALT_FONT_SIZE,
                weight=400, anchor="start")
    )


def build_svg(card: RollCard) -> str:
    """Compose the SVG document for one card."""
    bonus_plan = _plan_bonus_layout(card)
    alt_plan = _plan_alternative_layout(card)
    extras_plan = _plan_extras_layout(card)
    card_w = int(_content_width(card, bonus_plan, alt_plan, extras_plan)
                 + 2 * PAD)
    cx = card_w / 2
    parts: List[str] = []

    # Header
    title_y = PAD + 32
    formula_y = title_y + 30
    parts.append(_text(cx, title_y, card.title, size=34, weight=700))
    parts.append(_text(cx, formula_y, card.formula, size=18, weight=400,
                       opacity=0.65))
    rule_y = formula_y + 18
    # Cross-roller attribution banner. Present only when someone other than
    # the character's owner made the roll, so a roll accidentally made on
    # another player's sheet is obvious on the pasted card. Accent-coloured
    # to catch the eye; pushes the rule (and the whole body below it) down.
    if card.rolled_by:
        attribution_y = formula_y + 20
        parts.append(_text(cx, attribution_y, "Roll made by " + card.rolled_by,
                           size=15, weight=700, fill=ACCENT, family="sans"))
        rule_y = attribution_y + 16
    parts.append(_hr(rule_y, card_w))

    # Dice
    intra_gap = 16
    inter_gap = 24
    kept_label_y = rule_y + 26
    parts.append(_text(cx, kept_label_y, "KEPT", size=11, weight=600,
                       opacity=0.55, letter_spacing=2.5, family="sans"))
    parts.append(_row_svg(card.kept, cx, kept_label_y + 10))

    if card.dropped:
        dropped_label_y = kept_label_y + 10 + DIE_H + intra_gap
        parts.append(_text(cx, dropped_label_y, "DROPPED", size=11, weight=600,
                           opacity=0.55, letter_spacing=2.5, family="sans"))
        parts.append(_row_svg(card.dropped, cx, dropped_label_y + 10,
                              opacity=0.4))
        post_dice_y = dropped_label_y + 10 + DIE_H + inter_gap
    else:
        post_dice_y = kept_label_y + 10 + DIE_H + inter_gap

    # Bonuses
    if bonus_plan["mode"] != "none":
        parts.append(_hr(post_dice_y, card_w))
        bonuses_label_y = post_dice_y + 22
        parts.append(_text(cx, bonuses_label_y, "BONUSES", size=11,
                           weight=600, opacity=0.55, letter_spacing=2.5,
                           family="sans"))
        if bonus_plan["mode"] == "dual":
            block_left = cx - bonus_plan["block_w"] / 2
            col1_anchor = (block_left + bonus_plan["c1_amount"]
                           + BONUS_AMOUNT_LABEL_GAP)
            col2_left = block_left + bonus_plan["col1_w"] + BONUS_INTER_COL_GAP
            col2_anchor = (col2_left + bonus_plan["c2_amount"]
                           + BONUS_AMOUNT_LABEL_GAP)
            for i, b in enumerate(bonus_plan["col1"]):
                parts.append(_bonus_line_svg(
                    col1_anchor,
                    bonuses_label_y + 22 + i * BONUS_ROW_HEIGHT, b))
            for i, b in enumerate(bonus_plan["col2"]):
                parts.append(_bonus_line_svg(
                    col2_anchor,
                    bonuses_label_y + 22 + i * BONUS_ROW_HEIGHT, b))
        else:
            anchor = (cx - bonus_plan["block_w"] / 2
                      + bonus_plan["max_amount_w"]
                      + BONUS_AMOUNT_LABEL_GAP)
            for i, b in enumerate(card.bonuses):
                parts.append(_bonus_line_svg(
                    anchor,
                    bonuses_label_y + 22 + i * BONUS_ROW_HEIGHT, b))
        post_bonuses_y = (bonuses_label_y + 22
                          + (bonus_plan["rows"] - 1) * BONUS_ROW_HEIGHT + 16)
    else:
        post_bonuses_y = post_dice_y + 4

    # Details bullets (void spent, the 5th Dan +per-VP combat bonus,
    # above-10k10 overflow, Otherworldliness, Lucky/Togashi reroll,
    # ...). These mirror the small print under the on-screen result
    # panel so a pasted card explains *why* the total landed where it
    # did - e.g. that some kept dice came from spent void points.
    # Rendered as a left-aligned bulleted list within a centered
    # block, between the numeric bonus column and the TOTAL trophy.
    if extras_plan["rows"] > 0:
        parts.append(_hr(post_bonuses_y, card_w))
        details_label_y = post_bonuses_y + 22
        parts.append(_text(cx, details_label_y, "DETAILS", size=11,
                           weight=600, opacity=0.55, letter_spacing=2.5,
                           family="sans"))
        block_left = cx - extras_plan["block_w"] / 2
        row_y = details_label_y + 22
        for e in card.extras:
            parts.append(_text(block_left, row_y, EXTRA_BULLET + e,
                               size=EXTRA_FONT_SIZE, weight=400,
                               anchor="start", opacity=0.7))
            row_y += EXTRA_ROW_HEIGHT
        post_bonuses_y = row_y - EXTRA_ROW_HEIGHT + 16

    # Total trophy - suppressed for initiative rolls where no
    # meaningful sum exists across action dice. The footer still
    # renders below the dice block in that case so callers can label
    # the row ("Action dice").
    if card.show_total:
        parts.append(_hr(post_bonuses_y, card_w))
        total_label_y = post_bonuses_y + 28
        total_value_y = total_label_y + 50
        parts.append(_text(cx, total_label_y, "TOTAL", size=12, weight=600,
                           opacity=0.55, letter_spacing=5, family="sans"))
        parts.append(_text(cx, total_value_y, str(card.total), size=56,
                           weight=700, fill=ACCENT, family="serif"))
        bottom_y = total_value_y
        if card.footer:
            bottom_y = total_value_y + 22
            parts.append(_text(cx, bottom_y, card.footer, size=14, weight=400,
                               opacity=0.6, family="serif"))
    elif card.footer:
        # No trophy: place the footer just below the dice block (with
        # the same hr separator the trophy would have used) so it
        # still reads as a label on the dice rather than orphaned
        # whitespace.
        parts.append(_hr(post_bonuses_y, card_w))
        bottom_y = post_bonuses_y + 28
        parts.append(_text(cx, bottom_y, card.footer, size=14, weight=400,
                           opacity=0.6, family="serif"))
    else:
        bottom_y = post_bonuses_y

    # Alternative totals (conditional bonuses). Mirrors the View
    # Sheet's "Alternative totals:" block - each row shows
    # ``total + extra_flat`` next to its condition label, with an "if
    # all of the above" summing row when 2+ alts are present.
    if alt_plan["rows"] > 0:
        alt_top = bottom_y + 14
        parts.append(_hr(alt_top, card_w))
        alt_label_y = alt_top + 22
        parts.append(_text(cx, alt_label_y, "ALTERNATIVE TOTALS",
                           size=11, weight=600, opacity=0.55,
                           letter_spacing=2.5, family="sans"))
        block_left = cx - alt_plan["block_w"] / 2
        anchor = block_left + alt_plan["max_amount_w"] + ALT_AMOUNT_LABEL_GAP
        row_y = alt_label_y + 22
        for a in card.alternatives:
            total_str = str(card.total + a.extra_flat)
            parts.append(_alt_line_svg(anchor, row_y, total_str, a.label))
            row_y += ALT_ROW_HEIGHT
        if len(card.alternatives) > 1:
            total_all = card.total + sum(a.extra_flat for a in card.alternatives)
            parts.append(
                _alt_line_svg(anchor, row_y, str(total_all), ALT_IF_ALL_LABEL)
            )
            row_y += ALT_ROW_HEIGHT
        bottom_y = row_y - ALT_ROW_HEIGHT + 14

    card_h = int(bottom_y + PAD)
    frame = (
        f'<rect width="{card_w}" height="{card_h}" fill="{PARCHMENT}"/>'
        f'<rect x="{BORDER_INSET}" y="{BORDER_INSET}" '
        f'width="{card_w - BORDER_INSET * 2}" '
        f'height="{card_h - BORDER_INSET * 2}" '
        f'fill="none" stroke="{INK}" stroke-width="1" opacity="0.12" rx="6"/>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {card_w} {card_h}" width="{card_w}" height="{card_h}">'
        f'{frame}{"".join(parts)}</svg>'
    )


# ---------------------------------------------------------------------------
# Public surface: payload -> PNG bytes (cached)
# ---------------------------------------------------------------------------


_cache: "OrderedDict[str, bytes]" = OrderedDict()


def _cache_key(payload: dict) -> str:
    """Stable hash of the input payload. ``sort_keys`` makes
    equivalent payloads with different key orderings cache-hit."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _cache_get(key: str) -> Optional[bytes]:
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_put(key: str, value: bytes) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _LRU_MAX:
        _cache.popitem(last=False)


def render_png(payload: dict) -> bytes:
    """Render ``payload`` to a PNG byte string.

    Behaviour:
      * Lenient input: missing or malformed fields collapse to empty
        sections; bad input never raises here.
      * LRU-cached: equal payloads share a single rasterized blob.
    """
    key = _cache_key(payload)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    # Time the build+rasterize on a cache miss. The rasterize
    # (cairosvg) dominates - building the SVG string is ~free - so this
    # is effectively the per-image cost. Logged at DEBUG so it's silent
    # by default but available for ad-hoc measurement on the live box
    # (e.g. ``LOG_LEVEL=DEBUG`` / a logging tweak) without code changes.
    t0 = time.perf_counter()
    card = parse_payload(payload)
    svg = build_svg(card)
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.debug(
        "dice_card render: %.1f ms (svg=%d B, png=%d B)",
        elapsed_ms, len(svg), len(png),
    )
    _cache_put(key, png)
    return png


# Minimal payload used to prime the rasterizer at startup (see ``warm``).
_WARM_PAYLOAD = {
    "title": "warm", "formula": "1k1",
    "kept": [{"parts": [1]}], "total": 1,
}


def warm() -> bool:
    """Prime the rasterizer in this process.

    The first ``cairosvg.svg2png`` call in a process pays a one-time
    setup cost (library import + font/rasterizer init) of ~100-150 ms.
    On Fly the machine auto-stops when idle, so without this the *first*
    player to roll after a wake eats that latency on their Copy-as-image
    button. Calling this once at startup (in a background thread) moves
    the cost off the request path. Renders a tiny throwaway card whose
    result is intentionally discarded; the LRU is left untouched so the
    dummy never serves a real request. Returns True on success.

    Failures are swallowed and logged - warming is best-effort and must
    never take down startup (e.g. if a font/lib is momentarily
    unavailable)."""
    try:
        t0 = time.perf_counter()
        card = parse_payload(_WARM_PAYLOAD)
        cairosvg.svg2png(bytestring=build_svg(card).encode("utf-8"))
        log.info(
            "dice_card rasterizer warmed in %.0f ms",
            (time.perf_counter() - t0) * 1000,
        )
        return True
    except Exception:  # pragma: no cover - best-effort; defensive only
        log.warning("dice_card warm-up failed", exc_info=True)
        return False


def clear_cache() -> None:
    """Test-only hook so the LRU doesn't leak between unit tests."""
    _cache.clear()
