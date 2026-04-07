"""Tests for game_data integrity — ensures the rules module is internally consistent."""

from app.game_data import (
    ADVANTAGES,
    ADVANCED_SKILL_COSTS,
    BASIC_SKILL_COSTS,
    DISADVANTAGES,
    KNACK_COSTS,
    SCHOOLS,
    SCHOOLS_BY_CATEGORY,
    SCHOOL_KNACKS,
    SKILLS,
    SPELLS,
    SPELLS_BY_ELEMENT,
    Ring,
    ring_raise_cost,
    skill_raise_cost,
    total_skill_cost,
)


class TestRingCosts:
    def test_raise_to_3(self):
        assert ring_raise_cost(3) == 15

    def test_raise_to_4(self):
        assert ring_raise_cost(4) == 20

    def test_raise_to_5(self):
        assert ring_raise_cost(5) == 25

    def test_raise_to_6(self):
        assert ring_raise_cost(6) == 30


class TestSkillCosts:
    def test_basic_skill_costs(self):
        assert BASIC_SKILL_COSTS == {1: 2, 2: 2, 3: 3, 4: 3, 5: 3}

    def test_advanced_skill_costs(self):
        assert ADVANCED_SKILL_COSTS == {1: 4, 2: 4, 3: 6, 4: 8, 5: 10}

    def test_knack_costs_match_advanced(self):
        assert KNACK_COSTS is ADVANCED_SKILL_COSTS

    def test_total_basic_to_5(self):
        # 2 + 2 + 3 + 3 + 3 = 13
        assert total_skill_cost(5, is_advanced=False) == 13

    def test_total_advanced_to_5(self):
        # 4 + 4 + 6 + 8 + 10 = 32
        assert total_skill_cost(5, is_advanced=True) == 32

    def test_total_skill_cost_zero(self):
        assert total_skill_cost(0, is_advanced=False) == 0
        assert total_skill_cost(0, is_advanced=True) == 0

    def test_skill_raise_cost_basic(self):
        assert skill_raise_cost(1, is_advanced=False) == 2
        assert skill_raise_cost(3, is_advanced=False) == 3

    def test_skill_raise_cost_advanced(self):
        assert skill_raise_cost(1, is_advanced=True) == 4
        assert skill_raise_cost(5, is_advanced=True) == 10


class TestSkills:
    def test_all_skills_have_required_fields(self):
        for sid, skill in SKILLS.items():
            assert skill.id == sid
            assert skill.name
            assert skill.ring in Ring
            assert skill.category in ("social", "knowledge")
            assert isinstance(skill.is_advanced, bool)
            assert skill.description
            assert skill.roll_description

    def test_social_skills_use_air(self):
        for skill in SKILLS.values():
            if skill.category == "social":
                assert skill.ring == Ring.AIR, f"{skill.name} should use Air"

    def test_knowledge_skills_use_water(self):
        for skill in SKILLS.values():
            if skill.category == "knowledge":
                assert skill.ring == Ring.WATER, f"{skill.name} should use Water"

    def test_basic_social_count(self):
        count = sum(
            1 for s in SKILLS.values()
            if s.category == "social" and not s.is_advanced
        )
        assert count == 6

    def test_advanced_social_count(self):
        count = sum(
            1 for s in SKILLS.values()
            if s.category == "social" and s.is_advanced
        )
        assert count == 3

    def test_basic_knowledge_count(self):
        count = sum(
            1 for s in SKILLS.values()
            if s.category == "knowledge" and not s.is_advanced
        )
        assert count == 6

    def test_advanced_knowledge_count(self):
        count = sum(
            1 for s in SKILLS.values()
            if s.category == "knowledge" and s.is_advanced
        )
        assert count == 3


class TestSchools:
    def test_school_count(self):
        assert len(SCHOOLS) == 26

    def test_all_schools_have_three_knacks(self):
        for sid, school in SCHOOLS.items():
            assert len(school.school_knacks) == 3, (
                f"{school.name} has {len(school.school_knacks)} knacks, expected 3"
            )

    def test_all_schools_have_five_techniques(self):
        for sid, school in SCHOOLS.items():
            assert set(school.techniques.keys()) == {1, 2, 3, 4, 5}, (
                f"{school.name} techniques: {list(school.techniques.keys())}"
            )

    def test_all_school_knacks_exist(self):
        for sid, school in SCHOOLS.items():
            for knack_id in school.school_knacks:
                assert knack_id in SCHOOL_KNACKS, (
                    f"{school.name} references unknown knack '{knack_id}'"
                )

    def test_schools_by_category_covers_all(self):
        ids_from_categories = set()
        for cat_schools in SCHOOLS_BY_CATEGORY.values():
            for s in cat_schools:
                ids_from_categories.add(s.id)
        assert ids_from_categories == set(SCHOOLS.keys())

    def test_school_has_required_fields(self):
        for sid, school in SCHOOLS.items():
            assert school.id == sid
            assert school.name
            assert school.school_ring
            assert school.category
            assert school.special_ability


class TestSchoolKnacks:
    def test_knack_count(self):
        assert len(SCHOOL_KNACKS) == 20

    def test_all_knacks_have_required_fields(self):
        for kid, knack in SCHOOL_KNACKS.items():
            assert knack.id == kid
            assert knack.name
            assert knack.description
            assert knack.rules_text


class TestAdvantagesAndDisadvantages:
    def test_advantage_count(self):
        assert len(ADVANTAGES) == 17

    def test_disadvantage_count(self):
        assert len(DISADVANTAGES) == 22

    def test_advantages_have_positive_cost(self):
        for aid, adv in ADVANTAGES.items():
            assert adv.xp_cost > 0, f"{adv.name} should have positive cost"

    def test_disadvantages_have_positive_value(self):
        for did, dis in DISADVANTAGES.items():
            assert dis.xp_value > 0, f"{dis.name} should have positive value"


class TestSpells:
    def test_spell_count(self):
        assert len(SPELLS) == 12

    def test_three_spells_per_element(self):
        for element, spells in SPELLS_BY_ELEMENT.items():
            assert len(spells) == 3, f"{element} has {len(spells)} spells"

    def test_mastery_levels_3_4_5(self):
        for element, spells in SPELLS_BY_ELEMENT.items():
            levels = sorted(s.mastery_level for s in spells)
            assert levels == [3, 4, 5], f"{element} mastery levels: {levels}"
