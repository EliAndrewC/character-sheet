"""Tests for party-wide group effects integration in compute_effective_status."""

from app.services.status import compute_effective_status


# ---------------------------------------------------------------------------
# compute_effective_status — party_members integration
# ---------------------------------------------------------------------------


def _bare_char(**overrides):
    """A minimal character data dict for status computations."""
    base = {
        "rank": 7.5,
        "recognition": 7.5,
        "honor": 1.0,
        "advantages": [],
        "disadvantages": [],
        "campaign_advantages": [],
        "campaign_disadvantages": [],
        "school": "akodo_bushi",
    }
    base.update(overrides)
    return base


class TestComputeEffectiveStatusBackwardCompat:
    def test_no_party_argument_works_unchanged(self):
        """Calling without party_members defaults to None and behaves as before."""
        status = compute_effective_status(_bare_char())
        assert status.rank == 7.5
        # No new modifiers added
        assert all(m["source"] != "Imperial Disdain" for m in status.rank_modifiers)

    def test_empty_party_list_works(self):
        status = compute_effective_status(_bare_char(), party_members=[])
        assert status.rank == 7.5

    def test_none_party_works(self):
        status = compute_effective_status(_bare_char(), party_members=None)
        assert status.rank == 7.5


class TestPartyImperialDisdain:
    def test_party_member_imperial_disdain_adds_rank_modifier(self):
        party = [{
            "name": "Tanaka",
            "advantages": [],
            "disadvantages": [],
            "campaign_advantages": [],
            "campaign_disadvantages": ["imperial_disdain"],
        }]
        status = compute_effective_status(_bare_char(), party_members=party)
        modifiers = [m for m in status.rank_modifiers if "Imperial Disdain" in m["source"]]
        assert len(modifiers) == 1
        assert modifiers[0]["value"] == -1.0
        assert "Tanaka" in modifiers[0]["source"]
        assert "Imperial post holders" in modifiers[0]["context"]

    def test_two_party_members_with_same_effect_produce_two_modifiers(self):
        party = [
            {"name": "Tanaka", "campaign_disadvantages": ["imperial_disdain"],
             "advantages": [], "disadvantages": [], "campaign_advantages": []},
            {"name": "Hiroshi", "campaign_disadvantages": ["imperial_disdain"],
             "advantages": [], "disadvantages": [], "campaign_advantages": []},
        ]
        status = compute_effective_status(_bare_char(), party_members=party)
        modifiers = [m for m in status.rank_modifiers if "Imperial Disdain" in m["source"]]
        assert len(modifiers) == 2
        sources = {m["source"] for m in modifiers}
        assert any("Tanaka" in s for s in sources)
        assert any("Hiroshi" in s for s in sources)


class TestPartyFamilyReckoning:
    def test_venomous_sting_subtracts_one_rank(self):
        party = [{
            "name": "Tanaka",
            "advantages": [],
            "disadvantages": [],
            "campaign_advantages": [],
            "campaign_disadvantages": ["family_reckoning_venomous_sting"],
        }]
        status = compute_effective_status(_bare_char(), party_members=party)
        modifiers = [m for m in status.rank_modifiers if "Venomous" in m["source"]]
        assert len(modifiers) == 1
        assert modifiers[0]["value"] == -1.0
        assert "Tanaka's family history" in modifiers[0]["context"]

    def test_righteous_sting_adds_one_rank(self):
        party = [{
            "name": "Tanaka",
            "advantages": [],
            "disadvantages": [],
            "campaign_advantages": ["family_reckoning_righteous_sting"],
            "campaign_disadvantages": [],
        }]
        status = compute_effective_status(_bare_char(), party_members=party)
        modifiers = [m for m in status.rank_modifiers if "Righteous" in m["source"]]
        assert len(modifiers) == 1
        assert modifiers[0]["value"] == 1.0


class TestPartyNonRankEffects:
    def test_lion_enmity_does_not_add_rank_modifier(self):
        party = [{
            "name": "Tanaka",
            "advantages": [], "disadvantages": [], "campaign_advantages": [],
            "campaign_disadvantages": ["lion_enmity"],
        }]
        status = compute_effective_status(_bare_char(), party_members=party)
        # Lion Enmity has no rank_modifier in GROUP_EFFECTS — should add nothing
        assert all("Lion Enmity" not in m["source"] for m in status.rank_modifiers)

    def test_thoughtless_does_not_add_rank_modifier(self):
        party = [{
            "name": "Tanaka",
            "advantages": [], "disadvantages": ["thoughtless"], "campaign_advantages": [],
            "campaign_disadvantages": [],
        }]
        status = compute_effective_status(_bare_char(), party_members=party)
        assert all("Thoughtless" not in m["source"] for m in status.rank_modifiers)
