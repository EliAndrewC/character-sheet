"""Unit tests for the roll-key -> explainer resolver."""

from app.game_data import SCHOOL_KNACKS, SCHOOLS, SKILLS
from app.services.roll_descriptions import describe_roll, label_for_roll


def test_label_from_payload_title():
    """The display label is the title captured in the payload (the value that
    used to be duplicated into the dropped roll_label column)."""
    assert label_for_roll("skill:bragging", {"title": "Bragging"}) == "Bragging"
    assert label_for_roll("spend_vp_xk1:ide_diplomat", {"title": "Ide 3rd Dan"}) == "Ide 3rd Dan"
    assert label_for_roll("attack:damage", {"title": "Damage"}) == "Damage"


def test_label_falls_back_to_key_explainer_when_payload_has_no_title():
    # Defensive: a malformed payload (no real roller produces this) falls back
    # to the explainer title for the key, then the raw key.
    assert "Wound Check" in label_for_roll("wound_check", {})
    assert "Wound Check" in label_for_roll("wound_check", None)
    assert label_for_roll("totally_unknown", {}) == "totally_unknown"


def test_label_empty_key_and_payload():
    assert label_for_roll("", None) == "Roll"
    assert label_for_roll(None, {}) == "Roll"


def test_unknown_key_falls_back():
    out = describe_roll("totally_unknown_key")
    assert out["title"] == "totally_unknown_key"
    assert out["body"] == ""


def test_empty_key_returns_generic():
    out = describe_roll("")
    assert out["title"] == "Roll"
    assert out["body"] == ""


def test_none_key_returns_generic():
    out = describe_roll(None)
    assert out["title"] == "Roll"
    assert out["body"] == ""


def test_hardcoded_attack():
    out = describe_roll("attack")
    assert "Attack" in out["title"]
    assert "Fire" in out["body"]


def test_hardcoded_parry():
    out = describe_roll("parry")
    assert "Parry" in out["title"]
    assert "Air" in out["body"]


def test_hardcoded_wound_check():
    out = describe_roll("wound_check")
    assert "Wound Check" in out["title"]
    assert "Earth" in out["body"]


def test_hardcoded_initiative():
    out = describe_roll("initiative")
    assert "Initiative" in out["title"]
    assert "Reflexes" in out["body"]


def test_hardcoded_initiative_athletics():
    out = describe_roll("initiative:athletics")
    assert "Initiative" in out["title"]
    assert "Togashi" in out["body"]


def test_hardcoded_bless():
    out = describe_roll("bless")
    assert "Bless" in out["title"]
    assert "Priest" in out["body"]


def test_hardcoded_freeform():
    out = describe_roll("freeform")
    assert "Freeform" in out["title"]


def test_hardcoded_spend_vp_xk1():
    out = describe_roll("spend_vp_xk1")
    assert "Void" in out["title"]


def test_spend_vp_xk1_school_keyed_shows_isawa_ishi_3rd_dan():
    """The ":<school>" suffix resolves to that school's actual 3rd Dan rules
    text so the Roll History tooltip explains the real mechanic."""
    out = describe_roll("spend_vp_xk1:isawa_ishi")
    assert "Isawa Ishi" in out["title"]
    assert "3rd Dan" in out["title"]
    # Body is the canonical 3rd Dan technique text, not the generic blurb.
    assert out["body"] == SCHOOLS["isawa_ishi"].techniques[3]
    assert "precepts" in out["body"]


def test_spend_vp_xk1_school_keyed_shows_ide_diplomat_3rd_dan():
    out = describe_roll("spend_vp_xk1:ide_diplomat")
    assert "Ide Diplomat" in out["title"]
    assert out["body"] == SCHOOLS["ide_diplomat"].techniques[3]
    assert "subtract" in out["body"].lower()
    assert "tact" in out["body"]


def test_spend_vp_xk1_unknown_school_falls_back_to_generic():
    out = describe_roll("spend_vp_xk1:not_a_real_school")
    assert "Void" in out["title"]  # generic _HARDCODED blurb


def test_skill_resolves_via_game_data():
    out = describe_roll("skill:bragging")
    skill = SKILLS["bragging"]
    assert skill.name in out["title"]
    assert "(skill)" in out["title"]
    assert out["body"]  # non-empty rules text or description


def test_skill_unknown_id():
    out = describe_roll("skill:not_a_skill")
    assert out["title"] == "not_a_skill"
    assert out["body"] == ""


def test_knack_resolves_via_game_data():
    out = describe_roll("knack:iaijutsu")
    knack = SCHOOL_KNACKS["iaijutsu"]
    assert knack.name in out["title"]
    assert "(knack)" in out["title"]


def test_knack_variant_in_title():
    out = describe_roll("knack:iaijutsu:strike")
    assert "strike" in out["title"]


def test_knack_unknown_id():
    out = describe_roll("knack:not_a_knack")
    assert out["title"] == "not_a_knack"
    assert out["body"] == ""


def test_ring_resolves():
    out = describe_roll("ring:Fire")
    assert "Fire" in out["title"]
    assert "Fire" in out["body"]


def test_ring_unknown():
    out = describe_roll("ring:NotARing")
    assert out["title"] == "ring:NotARing"


def test_athletics_resolves():
    out = describe_roll("athletics:Air")
    assert "Air" in out["title"]
    assert "Athletics" in out["title"]


def test_school_technique_resolves():
    """An Isawa Ishi 3rd Dan key resolves to the school's 3rd Dan rules
    text verbatim - verifying the lookup is wired, not paraphrased."""
    out = describe_roll("school:isawa_ishi:3")
    school = SCHOOLS["isawa_ishi"]
    assert "Isawa Ishi" in out["title"]
    assert "3rd Dan" in out["title"]
    assert out["body"] == school.techniques[3]


def test_school_special_ability_resolves():
    out = describe_roll("school:isawa_ishi:special")
    school = SCHOOLS["isawa_ishi"]
    assert "Isawa Ishi" in out["title"]
    assert "special ability" in out["title"]
    assert out["body"] == school.special_ability


def test_school_unknown():
    out = describe_roll("school:not_a_school:3")
    assert out["title"] == "school:not_a_school:3"


def test_school_malformed():
    out = describe_roll("school:isawa_ishi")  # missing dan
    assert out["title"] == "school:isawa_ishi"


def test_school_invalid_dan():
    out = describe_roll("school:isawa_ishi:abc")
    # The "abc" strip leaves empty string, int() fails -> dan stays None
    assert out["title"] == "school:isawa_ishi:abc"


def test_iaijutsu_contested_strike_damage_hardcoded():
    for k, fragment in (
        ("iaijutsu:contested", "Contested"),
        ("iaijutsu:strike", "Strike"),
        ("iaijutsu:damage", "Damage"),
    ):
        out = describe_roll(k)
        assert fragment in out["title"]
        assert out["body"]


def test_kakita_5th_dan_hardcoded():
    out = describe_roll("kakita_5th_dan")
    assert "Kakita" in out["title"]
    assert "5th Dan" in out["title"]
    assert out["body"]


def test_damage_suffix_routes_to_parent():
    """`<key>:damage` derives a "Damage (...)" title from the parent
    attack key while sharing one canonical damage-rules body."""
    out = describe_roll("attack:damage")
    assert "Damage" in out["title"]
    assert "Attack" in out["title"]
    assert "weapon" in out["body"].lower()


def test_damage_suffix_unknown_parent():
    """An unknown parent still resolves cleanly via the fallback."""
    out = describe_roll("totally_made_up:damage")
    assert "Damage" in out["title"]
    # The parent fallback puts the raw key into the title
    assert "totally_made_up" in out["title"]
