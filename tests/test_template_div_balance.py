"""The sheet and the editor render with balanced <div> tags.

See ``tests/div_balance.py`` for why. The combat page's NPC roll overlay,
which includes the same roller, is checked in ``test_combat_actions.py``.
"""

import pytest

from app.models import User
from tests.conftest import make_character_form
from tests.div_balance import assert_divs_balanced


def _char(client, **overrides):
    r = client.post("/characters", data=make_character_form(**overrides), follow_redirects=False)
    return int(r.headers["location"].split("/")[2])


def _turn_on_roll_stats(client):
    s = client._test_session_factory()
    s.add(User(discord_id="183026066498125825", discord_name="gm", display_name="GM"))
    s.commit()
    s.close()
    client.post("/profile", data={"display_name": "GM", "roll_stats": "on"})


@pytest.mark.parametrize("roll_stats", [False, True])
def test_the_sheet_balances(client, roll_stats):
    if roll_stats:
        _turn_on_roll_stats(client)
    cid = _char(client)
    page = client.get(f"/characters/{cid}").text
    assert ('roll-stats-modal' in page) is roll_stats
    assert_divs_balanced(page, f"sheet (roll stats {'on' if roll_stats else 'off'})")


def test_a_profession_sheet_balances(client):
    cid = _char(client, school="profession", school_ring_choice="",
                knack_double_attack="0", knack_feint="0", knack_iaijutsu="0")
    assert_divs_balanced(client.get(f"/characters/{cid}").text, "profession sheet")


def test_the_editor_balances(client):
    cid = _char(client)
    assert_divs_balanced(client.get(f"/characters/{cid}/edit").text, "editor")


def test_the_check_catches_a_stray_close_and_an_unclosed_open():
    with pytest.raises(AssertionError, match="closes a div that was never opened"):
        assert_divs_balanced("<div></div></div><div>", "stray")
    with pytest.raises(AssertionError, match="1 <div> tag"):
        assert_divs_balanced("<div><div></div>", "unclosed")
    with pytest.raises(AssertionError, match="grep -o"):
        assert_divs_balanced("</div>", "tip")
    assert_divs_balanced("<div><script>'<div>'</script></div>", "script bodies are skipped")
