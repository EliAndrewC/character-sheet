"""Tests for game_data helper functions."""

from app.game_data import (
    DAN_XP_THRESHOLDS,
    HONOR_COST_PER_HALF,
    RANK_COST_PER_HALF,
    RECOGNITION_COST_PER_ONE,
    RECOGNITION_MAX_FACTOR,
    Ring,
    dan_for_xp,
    honor_raise_cost,
    max_recognition,
    rank_raise_cost,
    recognition_raise_cost,
    ring_max,
    starting_recognition,
    starting_rings,
    void_points_max,
    void_points_max_shugenja,
    void_regen_per_night,
    void_regen_per_night_shugenja,
    void_spend_cap_shugenja,
)


class TestStartingRings:
    def test_school_ring_starts_at_3(self):
        rings = starting_rings("Water")
        assert rings["Water"] == 3
        assert rings["Air"] == 2
        assert rings["Fire"] == 2

    def test_all_non_school_rings_at_2(self):
        rings = starting_rings("Fire")
        assert rings["Fire"] == 3
        for name in ["Air", "Earth", "Water", "Void"]:
            assert rings[name] == 2

    def test_invalid_school_ring_all_at_2(self):
        rings = starting_rings("Nonsense")
        for name in ["Air", "Fire", "Earth", "Water", "Void"]:
            assert rings[name] == 2


class TestRingMax:
    def test_school_ring_below_4th_dan_max_5(self):
        """Below 4th Dan the school ring is capped at 5, same as any
        ring. The 6 cap only becomes available at 4th Dan."""
        assert ring_max("Water", "Water") == 5
        assert ring_max("Water", "Water", dan=3) == 5

    def test_school_ring_at_or_above_4th_dan_max_6(self):
        """At 4th Dan and above the school ring can climb to 6, but
        never higher."""
        assert ring_max("Water", "Water", dan=4) == 6
        assert ring_max("Water", "Water", dan=5) == 6

    def test_non_school_ring_max_5(self):
        assert ring_max("Air", "Water") == 5
        assert ring_max("Air", "Water", dan=4) == 5


class TestVoidPoints:
    def test_standard_max(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2}
        assert void_points_max(rings) == 2

    def test_shugenja_max(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2}
        assert void_points_max_shugenja(rings, school_rank=2) == 6  # 4 + 2

    def test_standard_regen(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        assert void_regen_per_night(rings) == 1

    def test_shugenja_regen(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2}
        assert void_regen_per_night_shugenja(rings) == 2

    def test_shugenja_spend_cap(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2}
        assert void_spend_cap_shugenja(rings) == 1  # min(2) - 1


class TestHonorRankRecognitionHelpers:
    def test_honor_raise_cost(self):
        assert honor_raise_cost(1.0, 3.0) == 4  # 4 steps of 0.5

    def test_honor_raise_cost_zero(self):
        assert honor_raise_cost(2.0, 2.0) == 0

    def test_rank_raise_cost(self):
        assert rank_raise_cost(1.0, 2.5) == 3  # 3 steps of 0.5

    def test_recognition_raise_cost(self):
        assert recognition_raise_cost(1.0, 3.0) == 2  # 2 steps of 1.0

    def test_starting_recognition_normal(self):
        assert starting_recognition(2.0) == 2.0

    def test_starting_recognition_halved(self):
        assert starting_recognition(2.0, halved=True) == 1.0

    def test_max_recognition(self):
        assert max_recognition(2.0) == 3.0  # 150% of 2.0

    def test_max_recognition_rounds_down_to_half(self):
        # rank 7.5 * 1.5 = 11.25 -> rounded down to 11.0
        assert max_recognition(7.5) == 11.0
        # rank 6.5 * 1.5 = 9.75 -> rounded down to 9.5
        assert max_recognition(6.5) == 9.5
        # rank 5.5 * 1.5 = 8.25 -> rounded down to 8.0
        assert max_recognition(5.5) == 8.0
        # rank 3.5 * 1.5 = 5.25 -> rounded down to 5.0
        assert max_recognition(3.5) == 5.0


class TestDan:
    def test_dan_at_0_xp(self):
        assert dan_for_xp(0) == 1

    def test_dan_at_50_xp(self):
        assert dan_for_xp(50) == 2

    def test_dan_at_49_xp(self):
        assert dan_for_xp(49) == 1

    def test_dan_at_250_xp(self):
        assert dan_for_xp(250) == 5

    def test_dan_at_999_xp(self):
        assert dan_for_xp(999) == 5


class TestSocialVisibleSets:
    """The Group Summary page uses these allowlists to filter each
    PC's adv/disadv chip strip down to "conversation-relevant" entries.
    The membership choices here are a campaign-design call by the GM,
    so regressions to the set are flagged rather than silently changing
    what the GM sees on the roster."""

    def test_social_visible_advantages_membership(self):
        from app.game_data import (
            ADVANTAGES, CAMPAIGN_ADVANTAGES, SOCIAL_VISIBLE_ADVANTAGES,
        )
        # Every entry must exist in the standard or campaign catalogs.
        all_advs = set(ADVANTAGES) | set(CAMPAIGN_ADVANTAGES)
        for aid in SOCIAL_VISIBLE_ADVANTAGES:
            assert aid in all_advs, f"unknown advantage id: {aid}"
        # Specific entries the GM explicitly opted in.
        expected_in = {
            "charming", "wealthy",
            "imperial_favor", "highest_regard",
            "minor_clan_major_ally_sparrow",
            "minor_clan_major_ally_fox",
            "minor_clan_major_ally_mantis",
        }
        assert expected_in <= SOCIAL_VISIBLE_ADVANTAGES
        # Specific mechanical-only entries that must stay OUT.
        for excluded in ("higher_purpose", "tactician", "lucky",
                         "specialization", "kind_eye"):
            assert excluded not in SOCIAL_VISIBLE_ADVANTAGES
        # Surfaced via the Honor color highlight / Rank-Recognition
        # rows instead of as chips, so they're deliberately not in
        # the chip allowlist. ``household_wealth`` is excluded for
        # space (the chip text was too long for what it conveys).
        for excluded in ("virtue", "good_reputation", "household_wealth"):
            assert excluded not in SOCIAL_VISIBLE_ADVANTAGES

    def test_social_visible_disadvantages_membership(self):
        from app.game_data import (
            DISADVANTAGES, CAMPAIGN_DISADVANTAGES,
            SOCIAL_VISIBLE_DISADVANTAGES,
        )
        all_disadvs = set(DISADVANTAGES) | set(CAMPAIGN_DISADVANTAGES)
        for did in SOCIAL_VISIBLE_DISADVANTAGES:
            assert did in all_disadvs, f"unknown disadvantage id: {did}"
        expected_in = {
            "unkempt", "vain", "proud", "humble", "emotional",
            "short_temper", "long_temper", "contrary", "meddler",
            "jealousy", "transparent", "thoughtless",
            "dark_secret", "unlucky",
        }
        assert expected_in <= SOCIAL_VISIBLE_DISADVANTAGES
        # Same rationale as the advantage side: surfaced elsewhere on
        # the card (Honor color, Rank/Recognition rows), or roll-only.
        for excluded in ("unconventional", "bad_reputation",
                         "withdrawn", "permanent_wound"):
            assert excluded not in SOCIAL_VISIBLE_DISADVANTAGES

    def test_social_chip_labels_compact_names(self):
        """The chip-label override map shortens names that read better
        on a compact card. Each override must be (a) a known adv/disadv
        ID, and (b) actually shorter than the canonical name."""
        from app.game_data import (
            ADVANTAGES, CAMPAIGN_ADVANTAGES,
            DISADVANTAGES, CAMPAIGN_DISADVANTAGES,
            SOCIAL_CHIP_LABELS,
        )
        known = (set(ADVANTAGES) | set(CAMPAIGN_ADVANTAGES)
                 | set(DISADVANTAGES) | set(CAMPAIGN_DISADVANTAGES))
        for cid, short_label in SOCIAL_CHIP_LABELS.items():
            assert cid in known, f"unknown chip-label id: {cid}"
            adv = (
                ADVANTAGES.get(cid) or CAMPAIGN_ADVANTAGES.get(cid)
                or DISADVANTAGES.get(cid) or CAMPAIGN_DISADVANTAGES.get(cid)
            )
            assert len(short_label) < len(adv.name), (
                f"short label {short_label!r} is not shorter than the "
                f"canonical name {adv.name!r}"
            )
        # The three minor-clan allies are the named cases.
        assert SOCIAL_CHIP_LABELS == {
            "minor_clan_major_ally_sparrow": "Sparrow Ally",
            "minor_clan_major_ally_fox": "Fox Ally",
            "minor_clan_major_ally_mantis": "Mantis Ally",
        }
