"""Tests for effective Honor/Rank/Recognition computation with advantage modifiers."""

from app.services.status import compute_effective_status, EffectiveStatus
from tests.conftest import make_character_data


class TestBaseStatus:
    def test_no_advantages_no_modifiers(self):
        data = make_character_data(rank=2.0, recognition=2.0, honor=2.0)
        status = compute_effective_status(data)
        assert status.rank == 2.0
        assert status.recognition == 2.0
        assert status.rank_modifiers == []

    def test_stipend_base(self):
        data = make_character_data()
        status = compute_effective_status(data)
        assert status.stipend == 16  # campaign base rank 4 -> 4^2

    def test_stipend_ignores_actual_rank(self):
        data = make_character_data(rank=7.5)
        status = compute_effective_status(data)
        assert status.stipend == 16  # still 4^2, actual rank doesn't matter


class TestGMAwardedReputation:
    def test_gm_good_reputation_adds_rank_and_recognition(self):
        """A GM-awarded Good Reputation in rank_recognition_awards adds the
        same modifiers as the checkbox version, with the source text."""
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "heroism at White Stag"},
        ]
        status = compute_effective_status(data)
        assert any(
            m["value"] == 2.0 and "heroism at White Stag" in m["source"]
            for m in status.rank_modifiers
        )
        assert any(
            m["value"] == 1.0 and "heroism at White Stag" in m["source"]
            for m in status.recognition_modifiers
        )

    def test_gm_bad_reputation_adds_rank_and_recognition(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "bad_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "cowardice at the bridge"},
        ]
        status = compute_effective_status(data)
        assert any(
            m["value"] == -1.5 and "cowardice" in m["source"]
            for m in status.rank_modifiers
        )

    def test_multiple_gm_reputations_stack(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "valor"},
            {"id": "a2", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "diplomacy"},
        ]
        status = compute_effective_status(data)
        good_rank = [m for m in status.rank_modifiers if "Good Reputation" in m["source"]]
        assert len(good_rank) == 2

    def test_numeric_award_does_not_add_reputation_modifier(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "rank_recognition", "rank_delta": 1.0,
             "recognition_delta": 0.5, "source": "promotion"},
        ]
        status = compute_effective_status(data)
        assert not any("promotion" in m.get("source", "") for m in status.rank_modifiers)


class TestGoodReputation:
    def test_recognition_plus_1(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, advantages=["good_reputation"]
        )
        status = compute_effective_status(data)
        assert any(
            m["context"] == "for identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_plus_2_with_familiar(self):
        data = make_character_data(rank=2.0, advantages=["good_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["context"] == "with those familiar with your reputation"
            and m["value"] == 2.0
            for m in status.rank_modifiers
        )


class TestImperialFavor:
    def test_rank_plus_3_imperial_family(self):
        data = make_character_data(rank=2.0, advantages=["imperial_favor"])
        status = compute_effective_status(data)
        assert any(
            "Imperial family" in m["context"] and m["value"] == 3.0
            for m in status.rank_modifiers
        )

    def test_recognition_plus_3_imperial_family(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, advantages=["imperial_favor"]
        )
        status = compute_effective_status(data)
        assert any(
            "Imperial family" in m["context"] and m["value"] == 3.0
            for m in status.recognition_modifiers
        )

    def test_rank_plus_1_imperial_post(self):
        data = make_character_data(rank=2.0, advantages=["imperial_favor"])
        status = compute_effective_status(data)
        assert any(
            "Imperial post" in m["context"] and m["value"] == 1.0
            for m in status.rank_modifiers
        )


class TestBadReputation:
    def test_recognition_plus_1_identification(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, disadvantages=["bad_reputation"]
        )
        status = compute_effective_status(data)
        assert any(
            m["context"] == "for identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_minus_1_5_with_aware(self):
        data = make_character_data(rank=2.0, disadvantages=["bad_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["value"] == -1.5 for m in status.rank_modifiers
        )


class TestWealthy:
    def test_wealthy_no_stipend_effect(self):
        """Wealthy is disabled for Wasp campaign — no stipend impact."""
        data = make_character_data(advantages=["wealthy"])
        status = compute_effective_status(data)
        assert status.stipend == 16  # still campaign base


class TestPoor:
    def test_poor_no_stipend_effect(self):
        """Poor is disabled for Wasp campaign — no stipend impact."""
        data = make_character_data(disadvantages=["poor"])
        status = compute_effective_status(data)
        assert status.stipend == 16  # still campaign base


class TestHouseholdWealth:
    def test_household_wealth_stipend(self):
        data = make_character_data(campaign_advantages=["household_wealth"])
        status = compute_effective_status(data)
        assert status.stipend == 100  # 10^2

    def test_household_wealth_with_merchant_below_4th_dan(self):
        data = make_character_data(
            school="merchant", campaign_advantages=["household_wealth"]
        )
        status = compute_effective_status(data)
        assert status.stipend == 100  # 10^2 (no +5, below 4th Dan)

    def test_household_wealth_with_merchant_at_4th_dan(self):
        data = make_character_data(
            school="merchant",
            campaign_advantages=["household_wealth"],
            knacks={"discern_honor": 4, "oppose_knowledge": 4, "worldliness": 4},
        )
        status = compute_effective_status(data)
        assert status.stipend == 225  # (10+5)^2

    def test_household_wealth_with_shosuro_actor_below_4th_dan(self):
        data = make_character_data(
            school="shosuro_actor", campaign_advantages=["household_wealth"]
        )
        status = compute_effective_status(data)
        assert status.stipend == 100  # 10^2 (no +5, below 4th Dan)

    def test_household_wealth_with_shosuro_actor_at_4th_dan(self):
        data = make_character_data(
            school="shosuro_actor",
            campaign_advantages=["household_wealth"],
            knacks={"athletics": 4, "discern_honor": 4, "pontificate": 4},
        )
        status = compute_effective_status(data)
        assert status.stipend == 225  # (10+5)^2


class TestMerchantStipend:
    def test_merchant_school_stipend_below_4th_dan(self):
        data = make_character_data(school="merchant")
        # Default knacks are rank 1 (dan=1), stipend bonus should NOT apply
        status = compute_effective_status(data)
        assert status.stipend == 16  # 4^2 (no +5 bonus)

    def test_merchant_school_stipend_at_4th_dan(self):
        data = make_character_data(
            school="merchant",
            knacks={"discern_honor": 4, "oppose_knowledge": 4, "worldliness": 4},
        )
        status = compute_effective_status(data)
        assert status.stipend == 81  # (4+5)^2

    def test_shosuro_actor_stipend_below_4th_dan(self):
        data = make_character_data(school="shosuro_actor")
        status = compute_effective_status(data)
        assert status.stipend == 16  # 4^2 (no +5 bonus)

    def test_shosuro_actor_stipend_at_4th_dan(self):
        data = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 4, "discern_honor": 4, "pontificate": 4},
        )
        status = compute_effective_status(data)
        assert status.stipend == 81  # (4+5)^2


class TestStipendModifiers:
    def test_base_has_modifier(self):
        data = make_character_data()
        status = compute_effective_status(data)
        assert len(status.stipend_modifiers) >= 1
        assert status.stipend_modifiers[0]["source"] == "Wasp campaign base"

    def test_household_wealth_modifier(self):
        data = make_character_data(campaign_advantages=["household_wealth"])
        status = compute_effective_status(data)
        sources = [m["source"] for m in status.stipend_modifiers]
        assert "Household Wealth" in sources

    def test_school_modifier(self):
        data = make_character_data(
            school="merchant",
            knacks={"discern_honor": 4, "oppose_knowledge": 4, "worldliness": 4},
        )
        status = compute_effective_status(data)
        sources = [m["source"] for m in status.stipend_modifiers]
        assert "Merchant (4th Dan)" in sources

    def test_no_school_modifier_below_4th_dan(self):
        data = make_character_data(school="merchant")
        status = compute_effective_status(data)
        sources = [m["source"] for m in status.stipend_modifiers]
        assert not any("Merchant" in s for s in sources)


class TestCombined:
    def test_multiple_rank_modifiers(self):
        data = make_character_data(
            rank=2.0,
            advantages=["good_reputation", "imperial_favor"],
        )
        status = compute_effective_status(data)
        # Should have modifiers from both
        assert len(status.rank_modifiers) >= 3  # good_rep(+2) + imperial(+3, +1)


class TestStatusPills:
    """``rank_pills()`` and ``recognition_pills()`` collapse the per-source
    modifier list into one entry per short_label with summed values. Two
    Good Reputation awards yield a single ``+2 identification`` pill,
    not two separate ``+1`` pills."""

    def test_pills_collapse_same_label(self):
        data = make_character_data(
            rank_recognition_awards=[
                {"type": "good_reputation", "source": "Saved a village",
                 "recognition_delta": 1.0, "rank_delta": 2.0},
                {"type": "good_reputation", "source": "Outwitted a courtier",
                 "recognition_delta": 1.0, "rank_delta": 2.0},
            ],
        )
        status = compute_effective_status(data)
        rec_pills = status.recognition_pills()
        rank_pills = status.rank_pills()
        # Two Good Rep awards share short_label='identification' for
        # recognition and 'reputation' for rank.
        assert len(rec_pills) == 1
        assert rec_pills[0] == {"short_label": "identification", "value": 2.0}
        assert len(rank_pills) == 1
        assert rank_pills[0] == {"short_label": "reputation", "value": 4.0}

    def test_pills_keep_distinct_labels(self):
        """Imperial Favor produces both 'imperial family' and 'imperial
        post' pills, which must NOT collapse together."""
        data = make_character_data(advantages=["imperial_favor"])
        status = compute_effective_status(data)
        rank_pills = status.rank_pills()
        labels = [p["short_label"] for p in rank_pills]
        assert "imperial family" in labels
        assert "imperial post" in labels
        assert len(rank_pills) == 2

    def test_pills_empty_when_no_modifiers(self):
        data = make_character_data()
        status = compute_effective_status(data)
        assert status.rank_pills() == []
        assert status.recognition_pills() == []

    def test_group_effect_pill_uses_effect_category_label(self):
        """Family Reckoning from a party member surfaces in the pills
        as the category label ``Family Reckoning`` (no name prefix).
        Multiple sources combine on this label."""
        data = make_character_data(name="Mine")
        party = [{
            "name": "Bob", "school": "akodo_bushi", "dan": 1,
            "advantages": [], "disadvantages": [],
            "campaign_advantages": ["family_reckoning_righteous_sting"],
            "campaign_disadvantages": [],
        }]
        status = compute_effective_status(data, party_members=party)
        pills = status.rank_pills()
        labels = [p["short_label"] for p in pills]
        assert labels == ["Family Reckoning"]

    def test_family_reckoning_self_gets_double_value(self):
        """The taker of Family Reckoning gets +/-2.0 to their own Rank
        (not +/-1.0); other party members get +/-1.0."""
        data = make_character_data(
            name="Self",
            campaign_advantages=["family_reckoning_righteous_sting"],
        )
        status = compute_effective_status(data)
        pills = status.rank_pills()
        assert pills == [{"short_label": "Family Reckoning", "value": 2.0}]

    def test_family_reckoning_sources_combine_and_cancel(self):
        """Multiple party members contributing to the same category get
        their values summed in the top-line pill view. If the sum is 0
        the pill is dropped (e.g. one Righteous +1 and one Venomous -1
        from different party members cancel out for an uninvolved third
        character). The cancellation is summary-only: the raw modifier
        list keeps both entries so the expanded breakdown still shows
        each contributor individually."""
        data = make_character_data(name="Third")
        party = [
            {"name": "Alice", "school": "akodo_bushi", "dan": 1,
             "advantages": [], "disadvantages": [],
             "campaign_advantages": ["family_reckoning_righteous_sting"],
             "campaign_disadvantages": []},
            {"name": "Bob", "school": "akodo_bushi", "dan": 1,
             "advantages": [], "disadvantages": [],
             "campaign_advantages": [],
             "campaign_disadvantages": ["family_reckoning_venomous_sting"]},
        ]
        status = compute_effective_status(data, party_members=party)
        # Top-line pills cancel out.
        assert status.rank_pills() == []
        # But the raw modifier list keeps both entries so the expanded
        # breakdown can attribute the +1 and -1 to their owners.
        fr_mods = [m for m in status.rank_modifiers
                   if "Family Reckoning" in m["source"]]
        assert len(fr_mods) == 2
        values = sorted(m["value"] for m in fr_mods)
        assert values == [-1.0, 1.0]
        sources = {m["source"] for m in fr_mods}
        assert any("Alice" in s for s in sources)
        assert any("Bob" in s for s in sources)

    def test_imperial_disdain_label_is_for_imperials(self):
        """Imperial Disdain's pill is labelled ``for Imperials`` (no
        per-source ``Tetsuro's imperial post`` prefixing)."""
        data = make_character_data(name="Self")
        party = [{
            "name": "Tetsuro", "school": "akodo_bushi", "dan": 1,
            "advantages": [], "disadvantages": [],
            "campaign_advantages": [],
            "campaign_disadvantages": ["imperial_disdain"],
        }]
        status = compute_effective_status(data, party_members=party)
        pills = status.rank_pills()
        assert pills == [{"short_label": "for Imperials", "value": -1.0}]


class TestSchoolRingMinimum:
    def test_school_ring_min_3_in_validation(self):
        """School ring cannot be lowered below 3."""
        from app.services.xp import validate_character
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            school_ring_choice="Water",
        )
        errors = validate_character(data)
        assert any("school ring" in e.lower() or ("Water" in e and "below" in e) for e in errors)


class TestXpBudgetDisplay:
    def test_disadvantage_xp_separate(self):
        """Total XP breakdown should separate disadvantage XP from budget."""
        from app.services.xp import calculate_total_xp
        data = make_character_data(
            disadvantages=["proud", "vain"],  # 2 + 2 = 4 XP
            skills={"bragging": 2},  # 4 XP
        )
        result = calculate_total_xp(data)
        assert result["disadvantages"] == -4
        # The "spent" (before disadvantages) should be computable
        spent_before_dis = result["total"] - result["disadvantages"]
        assert spent_before_dis == 4  # just the skill cost
