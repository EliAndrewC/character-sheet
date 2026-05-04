"""Tests for Attack and Parry combat skills.

Attack and Parry are special combat skills that every character has:
- Attack: rolled with Fire, starts at 1
- Parry: rolled with Air, starts at 1
- Both are raised using the advanced skill cost table
- Rank 1 is free (everyone starts there); XP cost applies for ranks above 1
"""

import pytest

from app.game_data import COMBAT_SKILLS, ADVANCED_SKILL_COSTS
from app.models import Character
from app.services.xp import (
    calculate_combat_skill_xp,
    calculate_total_xp,
    validate_character,
)
from tests.conftest import make_character_data


class TestCombatSkillGameData:
    def test_attack_exists(self):
        assert "attack" in COMBAT_SKILLS

    def test_parry_exists(self):
        assert "parry" in COMBAT_SKILLS

    def test_attack_ring_is_fire(self):
        assert COMBAT_SKILLS["attack"]["ring"] == "Fire"

    def test_parry_ring_is_air(self):
        assert COMBAT_SKILLS["parry"]["ring"] == "Air"

    def test_both_start_at_1(self):
        assert COMBAT_SKILLS["attack"]["start"] == 1
        assert COMBAT_SKILLS["parry"]["start"] == 1

    def test_both_use_advanced_costs(self):
        assert COMBAT_SKILLS["attack"]["cost_table"] is ADVANCED_SKILL_COSTS
        assert COMBAT_SKILLS["parry"]["cost_table"] is ADVANCED_SKILL_COSTS


class TestCombatSkillXP:
    def test_both_at_1_free(self):
        assert calculate_combat_skill_xp(attack=1, parry=1) == 0

    def test_attack_raised_to_2(self):
        # Advanced cost for rank 2 = 4
        assert calculate_combat_skill_xp(attack=2, parry=1) == 4

    def test_parry_raised_to_3(self):
        # Ranks 2+3 = 4+6 = 10
        assert calculate_combat_skill_xp(attack=1, parry=3) == 10

    def test_both_raised(self):
        # Attack to 3 = 4+6=10, Parry to 2 = 4
        assert calculate_combat_skill_xp(attack=3, parry=2) == 14

    def test_max_rank_5(self):
        # Attack to 5 = 4+6+8+10=28
        assert calculate_combat_skill_xp(attack=5, parry=1) == 28


class TestCombatSkillsInTotalXP:
    def test_default_combat_skills_cost_nothing(self):
        data = make_character_data()
        result = calculate_total_xp(data)
        assert result["combat_skills"] == 0

    def test_raised_combat_skills_cost_xp(self):
        data = make_character_data(attack=3, parry=2)
        result = calculate_total_xp(data)
        assert result["combat_skills"] == 14  # 10 + 4
        assert result["total"] == 14


class TestCombatSkillValidation:
    def test_attack_below_1_invalid(self):
        data = make_character_data(attack=0)
        errors = validate_character(data)
        assert any("attack" in e.lower() and "at least 1" in e for e in errors)

    def test_parry_above_5_invalid(self):
        data = make_character_data(parry=6)
        errors = validate_character(data)
        assert any("parry" in e.lower() and "exceeds" in e for e in errors)

    def test_valid_combat_skills(self):
        data = make_character_data(attack=3, parry=2, starting_xp=150)
        errors = validate_character(data)
        assert not any("attack" in e.lower() or "parry" in e.lower() for e in errors)


class TestCombatSkillsOnModel:
    def test_model_has_attack_and_parry(self):
        c = Character(name="Test", attack=2, parry=3)
        assert c.attack == 2
        assert c.parry == 3

    def test_model_defaults_to_1(self, db):
        c = Character(name="Test")
        db.add(c)
        db.flush()
        assert c.attack == 1
        assert c.parry == 1

    def test_to_dict_includes_combat_skills(self, db):
        c = Character(name="Test", attack=3, parry=2)
        db.add(c)
        db.flush()
        d = c.to_dict()
        assert d["attack"] == 3
        assert d["parry"] == 2

    def test_from_dict_reads_combat_skills(self):
        c = Character.from_dict({"name": "Test", "attack": 4, "parry": 2})
        assert c.attack == 4
        assert c.parry == 2


class TestCombatSkillsInRoutes:
    def test_autosave_stores_combat_skills(self, client):
        from tests.conftest import query_db
        from app.models import Character
        session = client._test_session_factory()
        c = Character(name="Combat", owner_discord_id="183026066498125825",
                      knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        session.add(c)
        session.commit()

        client.post(f"/characters/{c.id}/autosave", json={"attack": 3, "parry": 2})
        char = query_db(client).filter(Character.id == c.id).first()
        assert char.attack == 3
        assert char.parry == 2

    def test_character_sheet_shows_combat_skills(self, client):
        from tests.conftest import query_db
        from app.models import Character
        session = client._test_session_factory()
        c = Character(
            name="Combat Test",
            school="akodo_bushi",
            school_ring_choice="Water",
            ring_water=3,
            attack=3,
            parry=2,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        session.add(c)
        session.commit()

        resp = client.get(f"/characters/{c.id}")
        assert resp.status_code == 200
        body = resp.text
        # Should show attack/parry ranks and roll formulas
        assert "Attack" in body
        assert "Parry" in body

    def test_character_sheet_shows_correct_tn_to_hit(self, client):
        from app.models import Character
        session = client._test_session_factory()
        c = Character(
            name="TN Test",
            school="akodo_bushi",
            school_ring_choice="Water",
            ring_water=3,
            parry=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        session.add(c)
        session.commit()

        resp = client.get(f"/characters/{c.id}")
        # TN to hit = 5 + 5 * parry = 5 + 15 = 20
        assert "20" in resp.text


class TestCombatSkillRowLayout:
    """Attack and Parry rows on the character sheet display the roll
    formula (e.g. "7k3") to the LEFT of the rank pips, with an invisible
    chevron-sized spacer to the right of the pips so the pips line up
    vertically with the school-knack pip groups underneath (which are
    followed by an expand-chevron)."""

    def _seed(self, client):
        from app.models import Character
        session = client._test_session_factory()
        c = Character(
            name="Layout Test",
            school="akodo_bushi",
            school_ring_choice="Water",
            ring_water=3,
            attack=2, parry=2,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        session.add(c)
        session.commit()
        return c.id

    def _row_html(self, body: str, roll_key: str) -> str:
        """Slice out the row div for a given data-roll-key."""
        marker = f'data-roll-key="{roll_key}"'
        start = body.index(marker)
        # Walk back to the opening <div for that row
        start = body.rfind('<div', 0, start)
        # Find matching </div> at depth 1 by counting
        i = start
        depth = 0
        while i < len(body):
            if body.startswith('<div', i):
                depth += 1
                i += 4
            elif body.startswith('</div>', i):
                depth -= 1
                i += 6
                if depth == 0:
                    return body[start:i]
            else:
                i += 1
        raise AssertionError(f"unterminated row for {roll_key}")

    def _assert_roll_left_of_pips(self, row_html: str, roll_text: str):
        roll_idx = row_html.index(roll_text)
        # Pip group is the inner "flex gap-0.5" div that holds the 5 circles
        pips_idx = row_html.index('flex gap-0.5')
        assert roll_idx < pips_idx, (
            f"expected roll formula '{roll_text}' to appear before the pips "
            f"in DOM order, got roll at {roll_idx} and pips at {pips_idx}"
        )

    def _assert_invisible_chevron_after_pips(self, row_html: str):
        pips_idx = row_html.index('flex gap-0.5')
        # An invisible w-4 element (matching the knack chevron) must follow
        # the pips so the pips line up with the knack rows below.
        tail = row_html[pips_idx:]
        assert 'invisible' in tail and 'w-4' in tail, (
            "expected an invisible chevron-sized spacer after the pip group "
            "so the pips align with the knack-row pips below"
        )

    def test_attack_row_roll_left_of_pips_with_chevron_spacer(self, client):
        cid = self._seed(client)
        body = client.get(f"/characters/{cid}").text
        row = self._row_html(body, 'attack')
        # Akodo bushi 1st-Dan adds an extra rolled die: attack 2 + Fire 2 + 1 = 5k2
        self._assert_roll_left_of_pips(row, '5k2')
        self._assert_invisible_chevron_after_pips(row)

    def test_parry_row_roll_left_of_pips_with_chevron_spacer(self, client):
        cid = self._seed(client)
        body = client.get(f"/characters/{cid}").text
        row = self._row_html(body, 'parry')
        # parry 2 + Air 2 = 4k2
        self._assert_roll_left_of_pips(row, '4k2')
        self._assert_invisible_chevron_after_pips(row)
