"""Tests for ``app/services/dice_card.py``.

Coverage is hit-the-functions-from-the-outside style: feed real
payloads through ``render_png`` and confirm shape / cache / SVG-text
properties rather than poking at intermediate dataclasses.
"""

import pytest

from app.services import dice_card
from app.services.dice_card import (
    Bonus,
    Die,
    DieCell,
    RollCard,
    build_svg,
    clear_cache,
    parse_payload,
    render_png,
)


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Each test gets a fresh LRU so cache-hit assertions in one
    test can't be poisoned by a sibling test's leftover entries."""
    clear_cache()
    yield
    clear_cache()


def _basic_payload(**overrides):
    payload = {
        "title": "Bragging",
        "formula": "7k3",
        "kept": [{"parts": [9]}, {"parts": [8]}, {"parts": [7]}],
        "dropped": [{"parts": [6]}, {"parts": [4]}],
        "bonuses": [{"label": "from 1 raise spent", "amount": 5}],
        "total": 29,
    }
    payload.update(overrides)
    return payload


class TestParsePayload:
    def test_full_payload_round_trip(self):
        card = parse_payload(_basic_payload())
        assert card.title == "Bragging"
        assert card.formula == "7k3"
        assert len(card.kept) == 3
        assert card.kept[0].parts[0].value == 9
        assert len(card.dropped) == 2
        assert len(card.bonuses) == 1
        assert card.bonuses[0].amount == 5
        assert card.total == 29
        assert card.footer is None

    def test_missing_fields_collapse_to_empty(self):
        card = parse_payload({})
        assert card.title == "Roll"
        assert card.formula == ""
        assert card.kept == ()
        assert card.dropped == ()
        assert card.bonuses == ()
        assert card.total == 0
        assert card.footer is None

    def test_bare_int_die_normalizes_to_single_part_cell(self):
        """The frontend usually sends ``{parts: [v]}`` for each die,
        but a payload with bare ints should still resolve correctly."""
        card = parse_payload({
            "title": "T", "formula": "", "kept": [9, 8, 7],
            "dropped": [], "bonuses": [], "total": 24,
        })
        assert tuple(d.parts[0].value for d in card.kept) == (9, 8, 7)

    def test_value_only_dict_die_works(self):
        """``{value: N}`` (no parts list) is the third accepted die
        shape - some result modals construct dice that way."""
        card = parse_payload({
            "title": "T", "formula": "", "kept": [{"value": 10}],
            "dropped": [], "bonuses": [], "total": 10,
        })
        assert card.kept[0].parts[0].value == 10
        assert card.kept[0].parts[0].is_ten is True

    def test_chain_first_die_marked_is_ten_others_is_reroll(self):
        """First entry in a chain is the originating 10; subsequent
        entries are rerolls. Both render gold."""
        card = parse_payload({
            "title": "T", "formula": "", "kept": [{"parts": [10, 5]}],
            "dropped": [], "bonuses": [], "total": 15,
        })
        parts = card.kept[0].parts
        assert parts[0].is_ten and not parts[0].is_reroll
        assert parts[1].is_reroll and not parts[1].is_ten

    def test_three_part_chain(self):
        card = parse_payload({
            "title": "T", "formula": "", "kept": [{"parts": [10, 10, 4]}],
            "dropped": [], "bonuses": [], "total": 24,
        })
        parts = card.kept[0].parts
        assert len(parts) == 3
        assert parts[0].is_ten
        assert parts[1].is_reroll
        assert parts[2].is_reroll

    def test_first_die_below_ten_is_not_is_ten(self):
        """A chain's first die is only ``is_ten`` if it's literally
        a 10 - otherwise it's just a normal face. (Stub-out: chains
        should always start with a 10 in practice, but defensive
        handling matters since the payload is untrusted.)"""
        card = parse_payload({
            "title": "T", "formula": "", "kept": [{"parts": [8]}],
            "dropped": [], "bonuses": [], "total": 8,
        })
        assert card.kept[0].parts[0].is_ten is False

    def test_bonuses_with_zero_amount_and_no_label_drop(self):
        """Phantom bonus rows shouldn't pollute the rendered card."""
        card = parse_payload({
            "title": "T", "formula": "", "kept": [],
            "dropped": [], "total": 0,
            "bonuses": [
                {"label": "", "amount": 0},   # drop
                {"label": "real", "amount": 3},
                {"label": "zero with label", "amount": 0},
            ],
        })
        assert len(card.bonuses) == 2
        assert card.bonuses[0].label == "real"
        assert card.bonuses[1].label == "zero with label"

    def test_text_clipped_to_max_len(self):
        card = parse_payload({"title": "A" * 500, "formula": "B" * 500})
        assert card.title.endswith("...")
        assert len(card.title) <= dice_card.MAX_TEXT_LEN + 3
        assert card.formula.endswith("...")

    def test_dice_clipped_to_row_max(self):
        too_many = [{"parts": [9]} for _ in range(dice_card.MAX_DICE_PER_ROW + 5)]
        card = parse_payload({"title": "T", "kept": too_many})
        assert len(card.kept) == dice_card.MAX_DICE_PER_ROW

    def test_chain_clipped_to_max_per_cell(self):
        long_chain = [10] * (dice_card.MAX_CHAIN_PER_CELL + 5)
        card = parse_payload({"title": "T", "kept": [{"parts": long_chain}]})
        assert len(card.kept[0].parts) == dice_card.MAX_CHAIN_PER_CELL

    def test_bonuses_clipped_to_max(self):
        too_many = [{"label": f"b{i}", "amount": 1}
                    for i in range(dice_card.MAX_BONUSES + 5)]
        card = parse_payload({"title": "T", "bonuses": too_many})
        assert len(card.bonuses) == dice_card.MAX_BONUSES

    def test_invalid_outer_payload_returns_default_card(self):
        assert parse_payload("not a dict").title == "Roll"
        assert parse_payload(None).title == "Roll"

    def test_invalid_inner_shapes_are_skipped(self):
        """Non-dict / non-int dice entries and non-dict bonuses get
        skipped rather than raising; the card just renders thinner."""
        card = parse_payload({
            "title": "T",
            "kept": [None, "garbage", {"parts": []}, {"value": 7}],
            "bonuses": ["nope", None, {"label": "ok", "amount": 1}],
        })
        assert len(card.kept) == 1
        assert card.kept[0].parts[0].value == 7
        assert len(card.bonuses) == 1

    def test_negative_die_values_dropped(self):
        """Defensive: a negative die value would render outside the
        valid 1-10 range and confuse the styling. Drop it."""
        card = parse_payload({"title": "T", "kept": [{"parts": [-3]}]})
        assert card.kept == ()


class TestBuildSvg:
    def test_emits_dice_kite_path(self):
        svg = build_svg(parse_payload(_basic_payload()))
        # The d10 kite path's first quadratic curve is a distinctive
        # marker that the dice are present.
        assert "Q 100 71.4 94.03 76.73" in svg
        # Ten dice values from kept (9, 8, 7) and dropped (6, 4) all
        # appear as <text>...</text> tags.
        for n in (9, 8, 7, 6, 4):
            assert f">{n}</text>" in svg

    def test_xml_escapes_user_supplied_text(self):
        """A label like ``</text><script>...</script>`` must NOT be
        passed through. XML escaping turns the angle brackets into
        entities."""
        card = parse_payload({
            "title": "T", "formula": "",
            "bonuses": [{"label": "</text><script>alert(1)</script>",
                         "amount": 1}],
            "total": 1,
        })
        svg = build_svg(card)
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg or "&lt;/text&gt;" in svg

    def test_card_dimensions_grow_with_content(self):
        """A longer kept row produces a wider card. Width comes from
        the widest section's pixel span plus padding."""
        narrow = parse_payload({
            "title": "T", "formula": "",
            "kept": [{"parts": [9]}], "dropped": [],
            "total": 9,
        })
        wide = parse_payload({
            "title": "T", "formula": "",
            "kept": [{"parts": [i]} for i in range(1, 9)],
            "dropped": [],
            "total": 36,
        })
        import re
        nw = int(re.search(r'width="(\d+)"', build_svg(narrow)).group(1))
        ww = int(re.search(r'width="(\d+)"', build_svg(wide)).group(1))
        assert ww > nw

    def test_no_bonuses_section_when_empty(self):
        card = parse_payload({"title": "T", "kept": [{"parts": [7]}], "total": 7})
        assert ">BONUSES<" not in build_svg(card)

    def test_dual_column_bonuses_above_threshold(self):
        card = parse_payload({
            "title": "T",
            "kept": [{"parts": [7]}], "total": 7,
            "bonuses": [
                {"label": "a", "amount": 1},
                {"label": "b", "amount": 1},
                {"label": "c", "amount": 1},
                {"label": "d", "amount": 1},
                {"label": "e", "amount": 1},
                {"label": "f", "amount": 1},
            ],
        })
        svg = build_svg(card)
        # All 6 labels appear; the dual-column layout doesn't drop any.
        for letter in "abcdef":
            assert f">{letter}<" in svg

    def test_footer_renders_when_provided(self):
        card = parse_payload({
            "title": "Attack", "kept": [{"parts": [9]}], "total": 9,
            "footer": "vs TN 25 - Hit, 4 raises",
        })
        svg = build_svg(card)
        assert "vs TN 25 - Hit, 4 raises" in svg

    def test_footer_absent_does_not_emit_extra_line(self):
        card = parse_payload({
            "title": "T", "kept": [{"parts": [9]}], "total": 9,
        })
        svg = build_svg(card)
        assert "Hit" not in svg
        assert "Pass" not in svg

    def test_ten_and_reroll_dice_use_gold_styling(self):
        """A 10 and its reroll(s) share the gold fill / gold stroke /
        accent-red text so the chain reads as a single visual unit.
        Regression: removing the ``is_ten or is_reroll`` branch would
        render rerolls in the default white-on-ink palette."""
        card = parse_payload({
            "title": "Hit", "formula": "5k5",
            "kept": [{"parts": [10, 5]}, {"parts": [9]}],
            "total": 24,
        })
        svg = build_svg(card)
        # Gold fill + stroke + accent text appear in the SVG. There
        # are two of each (the 10 and its reroll); the single bare 9
        # uses the white-on-ink palette.
        assert svg.count(f'fill="{dice_card.GOLD_FILL}"') == 2
        assert svg.count(f'stroke="{dice_card.GOLD_STROKE}"') == 2
        # Plain die has the default white fill.
        assert f'fill="#ffffff"' in svg


class TestMeasureText:
    """Sanity-test the layout estimator. Real font metrics aren't
    available during rendering (the host font won't match the
    player's browser), so we use per-family average-character-width
    factors. Each family branch is exercised here so changes that
    silently break one family's layout get caught."""

    def test_serif_regular_under_bold(self):
        # Bold takes slightly more horizontal space than regular, so
        # the bold estimate must always be wider for the same string.
        regular = dice_card._measure_text("sample text", 18,
                                          weight=400, family="serif")
        bold = dice_card._measure_text("sample text", 18,
                                       weight=700, family="serif")
        assert bold > regular

    def test_sans_regular_under_bold(self):
        regular = dice_card._measure_text("KEPT", 11,
                                          weight=400, family="sans")
        bold = dice_card._measure_text("KEPT", 11,
                                       weight=600, family="sans")
        assert bold > regular

    def test_mono_independent_of_weight(self):
        """Monospace renders at a fixed advance per glyph regardless
        of weight - the estimator follows that convention."""
        regular = dice_card._measure_text("+10", 16,
                                          weight=400, family="mono")
        bold = dice_card._measure_text("+10", 16,
                                       weight=700, family="mono")
        assert regular == bold

    def test_longer_text_estimates_wider(self):
        short = dice_card._measure_text("Roll", 18)
        longer = dice_card._measure_text("Wound Check at TN 35", 18)
        assert longer > short


class TestRenderPng:
    def test_returns_valid_png_bytes(self):
        png = render_png(_basic_payload())
        # PNG file magic header.
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) > 200

    def test_cache_hit_returns_same_bytes_object(self):
        p = _basic_payload()
        first = render_png(p)
        second = render_png(p)
        # Identity check confirms we hit the LRU rather than
        # re-rasterizing on the second call.
        assert first is second

    def test_different_payloads_render_distinct_bytes(self):
        p1 = _basic_payload(total=29)
        p2 = _basic_payload(total=30)
        assert render_png(p1) != render_png(p2)

    def test_equivalent_payloads_with_different_key_order_share_cache(self):
        """``json.dumps(..., sort_keys=True)`` for the cache key means
        the same data in a different dict ordering hits the same
        cache entry."""
        a = {"title": "T", "total": 5, "kept": [{"parts": [5]}]}
        b = {"kept": [{"parts": [5]}], "total": 5, "title": "T"}
        first = render_png(a)
        second = render_png(b)
        assert first is second

    def test_lru_evicts_when_full(self):
        # Render enough unique payloads to overflow the LRU.
        first_payload = _basic_payload(title="evictee")
        first = render_png(first_payload)
        for i in range(dice_card._LRU_MAX + 1):
            render_png(_basic_payload(title=f"slot-{i}"))
        # ``first`` should have been pushed out by now; rendering its
        # payload again should produce a fresh bytes object (no
        # identity match with the original).
        again = render_png(first_payload)
        assert again is not first

    def test_empty_payload_still_renders(self):
        png = render_png({})
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def test_non_dict_payload_renders_default_card(self):
        png = render_png("malformed")
        assert png.startswith(b"\x89PNG\r\n\x1a\n")


class TestDataclasses:
    """Quick sanity check that the public dataclasses are immutable -
    needed because ``RollCard`` is stored in tuples used as dict keys
    transitively (parse -> card -> hash via payload)."""

    def test_die_is_frozen(self):
        d = Die(value=7)
        with pytest.raises(Exception):
            d.value = 8  # type: ignore[misc]

    def test_die_cell_is_frozen(self):
        c = DieCell(parts=(Die(value=7),))
        with pytest.raises(Exception):
            c.parts = ()  # type: ignore[misc]

    def test_roll_card_is_frozen(self):
        card = RollCard(title="x", formula="")
        with pytest.raises(Exception):
            card.title = "y"  # type: ignore[misc]

    def test_bonus_is_frozen(self):
        b = Bonus(label="x", amount=1)
        with pytest.raises(Exception):
            b.amount = 2  # type: ignore[misc]
