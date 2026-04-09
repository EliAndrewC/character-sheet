"""Tests for party-wide group effects integration in compute_effective_status
and the compute_party_effects helper."""

from app.services.status import compute_effective_status, compute_party_effects


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


# ---------------------------------------------------------------------------
# compute_party_effects helper
# ---------------------------------------------------------------------------


class TestComputePartyEffects:
    def test_empty_when_no_effects_and_no_party(self):
        effects = compute_party_effects(_bare_char(), "Self", [])
        assert effects == []

    def test_includes_self_effects(self):
        self_data = _bare_char(disadvantages=["thoughtless"])
        effects = compute_party_effects(self_data, "Hero", [])
        assert len(effects) == 1
        assert effects[0]["source_name"] == "Hero"
        assert effects[0]["effect_id"] == "thoughtless"
        assert effects[0]["effect_name"] == "Thoughtless"
        assert "Manipulation" in effects[0]["label"]

    def test_includes_other_party_member_effects(self):
        party = [{
            "name": "Tanaka",
            "advantages": [], "disadvantages": [], "campaign_advantages": [],
            "campaign_disadvantages": ["lion_enmity"],
        }]
        effects = compute_party_effects(_bare_char(), "Self", party)
        assert len(effects) == 1
        assert effects[0]["source_name"] == "Tanaka"
        assert effects[0]["effect_id"] == "lion_enmity"

    def test_self_and_other_combined(self):
        """Per UX, the callout should list ALL effects including self."""
        self_data = _bare_char(disadvantages=["thoughtless"])
        party = [{
            "name": "Tanaka",
            "advantages": [], "disadvantages": [], "campaign_advantages": [],
            "campaign_disadvantages": ["lion_enmity"],
        }]
        effects = compute_party_effects(self_data, "Hero", party)
        assert len(effects) == 2
        source_names = {e["source_name"] for e in effects}
        assert source_names == {"Hero", "Tanaka"}

    def test_all_five_effect_ids_recognised(self):
        all_effects_party = [{
            "name": "Multi",
            "advantages": [],
            "disadvantages": ["thoughtless"],
            "campaign_advantages": ["family_reckoning_righteous_sting"],
            "campaign_disadvantages": [
                "lion_enmity",
                "family_reckoning_venomous_sting",
                "imperial_disdain",
            ],
        }]
        effects = compute_party_effects(_bare_char(), "Self", all_effects_party)
        ids = {e["effect_id"] for e in effects}
        assert ids == {
            "thoughtless",
            "lion_enmity",
            "family_reckoning_righteous_sting",
            "family_reckoning_venomous_sting",
            "imperial_disdain",
        }

    def test_unknown_advantage_is_ignored(self):
        self_data = _bare_char(advantages=["fierce"])  # Fierce is not in GROUP_EFFECTS
        effects = compute_party_effects(self_data, "Hero", [])
        assert effects == []

    def test_party_members_default_none(self):
        effects = compute_party_effects(_bare_char(disadvantages=["thoughtless"]), "Hero")
        assert len(effects) == 1
