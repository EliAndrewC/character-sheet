"""E2E: Mutually exclusive advantage/disadvantage pairs."""

from tests.e2e.helpers import select_school
import pytest

pytestmark = pytest.mark.exclusive_pairs

def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")


def _check_pair(page, check_id, expect_disabled_id):
    """Check one of a pair and verify the other is disabled."""

    page.check(f'input[name="{check_id}"]')
    page.wait_for_timeout(200)
    disabled = page.locator(f'input[name="{expect_disabled_id}"]').is_disabled()
    assert disabled, f"Expected {expect_disabled_id} to be disabled after checking {check_id}"


def _uncheck_reenables(page, uncheck_id, expect_enabled_id):
    """Uncheck one of a pair and verify the other is re-enabled."""
    page.uncheck(f'input[name="{uncheck_id}"]')
    page.wait_for_timeout(200)
    disabled = page.locator(f'input[name="{expect_enabled_id}"]').is_disabled()
    assert not disabled, f"Expected {expect_enabled_id} to be enabled after unchecking {uncheck_id}"


def test_vain_disables_unkempt(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "dis_vain", "dis_unkempt")


def test_unkempt_disables_vain(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "dis_unkempt", "dis_vain")


def test_lucky_and_unlucky_can_coexist(page, live_server_url):
    """Lucky and Unlucky can both be taken at the same time."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="adv_lucky"]')
    page.wait_for_timeout(200)
    assert not page.locator('input[name="dis_unlucky"]').is_disabled(), \
        "Unlucky should NOT be disabled when Lucky is checked"
    page.check('input[name="dis_unlucky"]')
    page.wait_for_timeout(200)
    assert page.locator('input[name="adv_lucky"]').is_checked()
    assert page.locator('input[name="dis_unlucky"]').is_checked()


def test_imperial_favor_disables_imperial_disdain(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "adv_imperial_favor", "camp_dis_imperial_disdain")


def test_imperial_disdain_disables_imperial_favor(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "camp_dis_imperial_disdain", "adv_imperial_favor")


def test_quick_healer_disables_slow_healer(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "adv_quick_healer", "dis_slow_healer")


def test_slow_healer_disables_quick_healer(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "dis_slow_healer", "adv_quick_healer")


def test_virtue_disables_unconventional(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "adv_virtue", "dis_unconventional")


def test_unconventional_disables_virtue(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "dis_unconventional", "adv_virtue")


def test_righteous_disables_venomous(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "camp_adv_family_reckoning_righteous_sting",
                "camp_dis_family_reckoning_venomous_sting")


def test_venomous_disables_righteous(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _check_pair(page, "camp_dis_family_reckoning_venomous_sting",
                "camp_adv_family_reckoning_righteous_sting")


def test_exclusive_tooltip_shows_reason(page, live_server_url):
    """Disabled exclusive pair shows 'Cannot be taken with X' in tooltip."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_vain"]')
    page.wait_for_timeout(200)
    tooltip = page.locator('input[name="dis_unkempt"]').locator('..').locator('.tooltip-content')
    assert "Cannot be taken with" in tooltip.text_content()


def test_unchecking_reenables_pair(page, live_server_url):
    """Unchecking one of a pair re-enables the other."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="dis_vain"]')
    page.wait_for_timeout(200)
    assert page.locator('input[name="dis_unkempt"]').is_disabled()
    _uncheck_reenables(page, "dis_vain", "dis_unkempt")
