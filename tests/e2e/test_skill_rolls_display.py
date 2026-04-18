"""E2E: Skill roll display on character sheet — advantage bonuses, synergies, disadvantage notes."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.skill_rolls

def _create_char_with_skills(page, live_server_url, advantages=None, disadvantages=None,
                              skills=None, school="akodo_bushi", name="Roll Test"):
    """Create a character with specific skills and advantages, apply, return URL."""

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    for sid, ranks in (skills or {}).items():
        click_plus(page, f"skill_{sid}", ranks)
    for adv in (advantages or []):
        page.check(f'input[name="adv_{adv}"]')
    for dis in (disadvantages or []):
        page.check(f'input[name="dis_{dis}"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test character")
    return page.url


def test_discerning_bonus_on_investigation(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"investigation": 1}, advantages=["discerning"],
                              name="Discerning Inv")
    assert "Discerning" in page.text_content("body")


def test_discerning_bonus_on_interrogation(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"interrogation": 1}, advantages=["discerning"],
                              name="Discerning Int")
    assert "Discerning" in page.text_content("body")


def test_genealogist_bonus_on_heraldry(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"heraldry": 1}, advantages=["genealogist"],
                              name="Genealogist")
    assert "Genealogist" in page.text_content("body")


def test_tactician_bonus_on_strategy(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"strategy": 1}, advantages=["tactician"],
                              name="Tactician Str")
    assert "Tactician" in page.text_content("body")


def test_tactician_bonus_on_history(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"history": 1}, advantages=["tactician"],
                              name="Tactician His")
    assert "Tactician" in page.text_content("body")


def test_worldly_bonus_on_commerce(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"commerce": 1}, advantages=["worldly"],
                              name="Worldly Com")
    body = page.text_content("body")
    assert "Worldly" in body


def test_history_synergy_on_culture(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"culture": 1, "history": 2}, name="History Syn")
    assert "History" in page.text_content("body")


def test_acting_synergy_on_sincerity(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"sincerity": 1, "acting": 1}, name="Acting Syn")
    assert "Acting" in page.text_content("body")


def test_recognition_bonus_on_bragging(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"bragging": 1}, name="Recog Brag")
    assert "Recognition" in page.text_content("body")


def test_transparent_note_on_sincerity(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"sincerity": 1}, disadvantages=["transparent"],
                              name="Transparent")
    assert "always considered 5" in page.text_content("body")


def test_unkempt_note_on_culture(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"culture": 1}, disadvantages=["unkempt"],
                              name="Unkempt")
    assert "unkempt" in page.text_content("body").lower()


def test_thoughtless_note_on_tact(page, live_server_url):
    _create_char_with_skills(page, live_server_url,
                              skills={"tact": 1}, disadvantages=["thoughtless"],
                              name="Thoughtless")
    assert "Manipulation" in page.text_content("body")
