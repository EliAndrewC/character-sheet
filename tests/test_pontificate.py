"""Server-side tests for Pontificate "(as <skill>)" roll variants.

Pontificate may be rolled in place of any basic skill. ``build_all_roll_formulas``
pre-builds one ``knack:pontificate:as:<skill>`` formula per eligible basic
skill, inheriting that skill's bonuses (honor/recognition flat, conditional
alternatives, 3rd Dan free raises) while keeping Pontificate's own Water/Air
dice, plus a ``pontificate_skills`` menu list on the base formula.
"""

from app.services.dice import _skill_formula_has_bonus, build_all_roll_formulas
from tests.conftest import make_character_data


class TestSkillFormulaHasBonus:
    """The eligibility predicate for the Pontificate submenu. Tested
    directly so every bonus source counts (some, like Courtier/Doji 5th
    Dan, only co-occur with Pontificate via a foreign knack)."""

    def test_positive_flat_bonus_counts(self):
        assert _skill_formula_has_bonus({"bonuses": [{"label": "Honor", "amount": 10}]})

    def test_conditional_alternative_counts(self):
        assert _skill_formula_has_bonus({"alternatives": [{"label": "x", "extra_flat": 5}]})

    def test_courtier_5th_dan_optional_counts(self):
        assert _skill_formula_has_bonus({"courtier_5th_dan_optional": 3})

    def test_doji_5th_dan_flags_count(self):
        assert _skill_formula_has_bonus({"doji_5th_dan_always": True})
        assert _skill_formula_has_bonus({"doji_5th_dan_optional": True})

    def test_third_dan_raises_count(self):
        assert _skill_formula_has_bonus({"adventure_raises_max_per_roll": 2})

    def test_no_bonus_and_only_penalty_are_false(self):
        assert not _skill_formula_has_bonus({})
        # The unskilled-advanced -10 penalty is the only negative entry
        # and must NOT qualify a skill as having a bonus.
        assert not _skill_formula_has_bonus(
            {"bonuses": [{"label": "unskilled advanced penalty", "amount": -10}]}
        )


def _shosuro(**overrides):
    """A Shosuro Actor (Jimen-like): has the Pontificate knack, plus the
    honor/recognition and 3rd-Dan-on-sincerity bonuses from the goal."""
    data = make_character_data(
        school="shosuro_actor",
        school_ring_choice="Water",
        rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        skills={"sincerity": 3, "acting": 3},
        knacks={"athletics": 3, "discern_honor": 3, "pontificate": 3},
        honor=5.0,
        recognition=3.5,
    )
    data.update(overrides)
    return data


class TestPontificateVariants:
    def test_base_formula_lists_eligible_skills_sorted(self):
        f = build_all_roll_formulas(_shosuro())
        pont = f["knack:pontificate"]
        names = [s["name"] for s in pont["pontificate_skills"]]
        ids = [s["id"] for s in pont["pontificate_skills"]]
        # Sorted by display name.
        assert names == sorted(names)
        # bragging (honor+recognition), precepts (honor), sincerity
        # (conditional honor + 3rd Dan), intimidation (Acting synergy).
        assert set(ids) == {"bragging", "intimidation", "precepts", "sincerity"}
        # Each entry carries the variant formula key.
        for s in pont["pontificate_skills"]:
            assert s["key"] == f"knack:pontificate:as:{s['id']}"

    def test_base_pontificate_has_no_skill_bonuses(self):
        # Rolling Pontificate from the main menu (not a submenu) gets no
        # skill bonuses - the base formula stays bonus-free for Jimen.
        f = build_all_roll_formulas(_shosuro())
        assert f["knack:pontificate"].get("bonuses") in ([], None)
        assert f["knack:pontificate"].get("alternatives") in ([], None)

    def test_bragging_variant_inherits_flat_honor_recognition(self):
        f = build_all_roll_formulas(_shosuro())
        base = f["knack:pontificate"]
        v = f["knack:pontificate:as:bragging"]
        # Pontificate's own dice (Water 4 + rank 3 = 7k4), not bragging's.
        assert (v["rolled"], v["kept"]) == (base["rolled"], base["kept"])
        # +10 Honor (2*5) and +7 Recognition (2*3.5) = +17 flat.
        assert v["flat"] == 17
        labels = {b["label"]: b["amount"] for b in v["bonuses"]}
        assert labels.get("Honor") == 10
        assert labels.get("Recognition") == 7
        assert v["label"] == "Pontificate (as Bragging)"
        assert v["pontificate_as_skill"] == "bragging"
        assert v["pontificate_as_skill_name"] == "Bragging"

    def test_variant_drops_skill_identity_fields(self):
        # The Copy-as-image card must not show a misleading
        # "(bragging skill: N)" parenthetical, so skill_name/skill_rank
        # are stripped from the variant.
        v = build_all_roll_formulas(_shosuro())["knack:pontificate:as:bragging"]
        assert "skill_name" not in v
        assert "skill_rank" not in v
        assert "is_unskilled" not in v

    def test_sincerity_variant_carries_conditional_and_3rd_dan(self):
        v = build_all_roll_formulas(_shosuro())["knack:pontificate:as:sincerity"]
        # Conditional honor bonus surfaces as an "on open rolls" alternative.
        assert any(
            "open rolls" in a["label"] and a["extra_flat"] == 10
            for a in v["alternatives"]
        )
        # Shosuro Actor 3rd Dan (source skill sincerity, rank 3) makes
        # sincerity eligible for post-roll free raises.
        assert v["adventure_raises_max_per_roll"] == 3

    def test_excluded_skills_never_offered(self):
        # Give the character a History rank so heraldry would otherwise
        # gain a (conditional) synergy bonus - it must STILL be excluded.
        f = build_all_roll_formulas(_shosuro(skills={
            "sincerity": 3, "acting": 3, "history": 3,
        }))
        ids = {s["id"] for s in f["knack:pontificate"]["pontificate_skills"]}
        assert ids.isdisjoint({"sneaking", "heraldry", "investigation"})
        for excluded in ("sneaking", "heraldry", "investigation"):
            assert f"knack:pontificate:as:{excluded}" not in f

    def test_skills_without_bonus_are_absent(self):
        f = build_all_roll_formulas(_shosuro())
        # tact/etiquette/culture/law/strategy have no bonus for this char.
        for sk in ("tact", "etiquette", "culture", "law", "strategy"):
            assert f"knack:pontificate:as:{sk}" not in f

    def test_no_variants_when_school_lacks_pontificate(self):
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 2, "iaijutsu": 2, "lunge": 2},
        )
        f = build_all_roll_formulas(char)
        assert "knack:pontificate" not in f
        assert not any(k.startswith("knack:pontificate:as:") for k in f)

    def test_variant_keys_are_real_formulas(self):
        # Every key advertised in pontificate_skills resolves to an actual
        # formula dict (so the client menu's executeRoll(key) works).
        f = build_all_roll_formulas(_shosuro())
        for s in f["knack:pontificate"]["pontificate_skills"]:
            assert s["key"] in f
            assert f[s["key"]]["rolled"] > 0
