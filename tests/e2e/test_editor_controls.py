"""E2E: Editor field controls — min/max, disabled states, recognition halving, rank lock."""

from tests.e2e.helpers import select_school, click_plus, click_minus


def _go_to_editor(page, live_server_url, school="akodo_bushi"):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, school)


# --- Rings ---

def test_nonschool_ring_min_2(page, live_server_url):
    """Non-school ring cannot go below 2."""
    _go_to_editor(page, live_server_url)  # Water is school ring for akodo
    # Air is non-school, starts at 2 — minus should be disabled
    minus = page.locator('input[name="ring_air"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_nonschool_ring_max_5(page, live_server_url):
    """Non-school ring cannot exceed 5."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "ring_air", 3)  # 2 → 5
    plus = page.locator('input[name="ring_air"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


def test_school_ring_min_3(page, live_server_url):
    """School ring cannot go below 3."""
    _go_to_editor(page, live_server_url)  # Water is school ring, starts at 3
    minus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_school_ring_max_6(page, live_server_url):
    """School ring can go up to 6 (one higher than non-school)."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "ring_water", 3)  # 3 → 6
    plus = page.locator('input[name="ring_water"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()
    # Verify value is 6
    val = page.locator('input[name="ring_water"]').input_value()
    assert val == "6"


# --- Knacks ---

def test_knack_min_1(page, live_server_url):
    """Knack minimum is 1 (free from school), minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="knack_feint"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_knack_max_5(page, live_server_url):
    """Knack maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "knack_feint", 4)  # 1 → 5
    plus = page.locator('input[name="knack_feint"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Combat Skills ---

def test_attack_min_1(page, live_server_url):
    """Attack minimum is 1, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="attack"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_attack_max_5(page, live_server_url):
    """Attack maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "attack", 4)  # 1 → 5
    plus = page.locator('input[name="attack"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Skills ---

def test_skill_min_0(page, live_server_url):
    """Skill minimum is 0, minus disabled at 0."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="skill_precepts"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_skill_max_5(page, live_server_url):
    """Skill maximum is 5, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "skill_precepts", 5)  # 0 → 5
    plus = page.locator('input[name="skill_precepts"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Honor ---

def test_honor_min(page, live_server_url):
    """Honor minimum is 1.0, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="honor"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_honor_max(page, live_server_url):
    """Honor maximum is 5.0, plus disabled."""
    _go_to_editor(page, live_server_url)
    click_plus(page, "honor", 8)  # 1.0 → 5.0 in 0.5 steps
    plus = page.locator('input[name="honor"]').locator('..').locator('button', has_text="+")
    assert plus.is_disabled()


# --- Rank (locked) ---

def test_rank_locked_buttons_disabled(page, live_server_url):
    """Rank buttons are permanently disabled (locked for campaign)."""
    _go_to_editor(page, live_server_url)
    rank_section = page.locator('text="Rank"').first.locator('..')
    minus = rank_section.locator('button', has_text="-")
    plus = rank_section.locator('button', has_text="+")
    assert minus.is_disabled()
    assert plus.is_disabled()


# --- Recognition ---

def test_recognition_min_7_5(page, live_server_url):
    """Recognition minimum is 7.5, minus disabled."""
    _go_to_editor(page, live_server_url)
    minus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


def test_recognition_halve_sets_3_5(page, live_server_url):
    """Checking halve sets recognition to 3.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    val = page.locator('input[name="recognition"]').input_value()
    assert val == "3.5"


def test_recognition_halve_grants_3_xp(page, live_server_url):
    """Halving recognition reduces spent XP by 3 (net effect of -3 recognition XP)."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after == spent_before - 3


def test_recognition_unhalve_restores(page, live_server_url):
    """Unchecking halve restores recognition to at least 7.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    page.uncheck('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    val = page.locator('input[name="recognition"]').input_value()
    assert float(val) >= 7.5


def test_recognition_halved_min_3_5(page, live_server_url):
    """With halve checked, recognition minimum is 3.5."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    minus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="-")
    assert minus.is_disabled()


# --- Wealthy / Poor disabled ---

def test_wealthy_disabled(page, live_server_url):
    """Wealthy checkbox is disabled for Wasp campaign."""
    _go_to_editor(page, live_server_url)
    assert page.locator('input[name="adv_wealthy"]').is_disabled()


def test_poor_disadvantage_disabled(page, live_server_url):
    """Poor disadvantage checkbox is disabled for Wasp campaign."""
    _go_to_editor(page, live_server_url)
    assert page.locator('input[name="dis_poor"]').is_disabled()


# --- Recognition max ---

def test_recognition_max(page, live_server_url):
    """Recognition + disabled once it can't go higher without exceeding rank * 1.5."""
    _go_to_editor(page, live_server_url)
    # Max is rank(7.5) * 1.5 = 11.25. Click until we can't anymore.
    plus = page.locator('input[name="recognition"]').locator('..').locator('button', has_text="+")
    for _ in range(20):  # more than enough
        if plus.is_disabled():
            break
        plus.click(force=True)
    assert plus.is_disabled()
    val = float(page.locator('input[name="recognition"]').input_value())
    assert val <= 11.5  # JS rounds rank*1.5 to 11.3 via toFixed(1)


def test_recognition_halved_can_raise(page, live_server_url):
    """With halve checked, recognition can be raised above 3.5 (costs XP)."""
    _go_to_editor(page, live_server_url)
    page.check('input[name="recognition_halved"]')
    page.wait_for_timeout(300)
    click_plus(page, "recognition", 2)  # 3.5 → 4.5
    val = page.locator('input[name="recognition"]').input_value()
    assert float(val) == 4.5
    # Should cost XP: -3 (halve) + 1 (raised 1.0 above base) = -2
    spent = page.text_content('[x-text="grossSpent()"]').strip()
    assert int(spent) == -2


# --- Earned XP / Notes ---

def test_earned_xp_updates_budget(page, live_server_url):
    """Changing earned XP updates the total budget."""
    _go_to_editor(page, live_server_url)
    budget_before = page.text_content('[x-text="budgetWithDis()"]').strip()
    page.fill('input[name="earned_xp"]', "20")
    page.wait_for_timeout(300)
    budget_after = page.text_content('[x-text="budgetWithDis()"]').strip()
    assert int(budget_after) == int(budget_before) + 20


def test_notes_saves(page, live_server_url):
    """Notes textarea auto-saves."""
    _go_to_editor(page, live_server_url)
    page.fill('textarea[name="notes"]', "These are my test notes")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.reload()
    page.wait_for_selector('textarea[name="notes"]')
    assert page.locator('textarea[name="notes"]').input_value() == "These are my test notes"


# --- Save status ---

def test_save_status_indicator(page, live_server_url):
    """Save status shows 'Saved' after a change."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Status Test")
    page.wait_for_selector('text="Saved"', timeout=5000)


# --- Campaign advantages/disadvantages ---

def test_campaign_advantage_toggles_xp(page, live_server_url):
    """Campaign advantage checkbox updates XP."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    page.check('input[name="camp_adv_streetwise"]')
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after > spent_before


def test_campaign_disadvantage_toggles_xp(page, live_server_url):
    """Campaign disadvantage checkbox adds XP to budget."""
    _go_to_editor(page, live_server_url)
    budget_before = int(page.text_content('[x-text="budgetWithDis()"]').strip())
    page.check('input[name="camp_dis_peasantborn"]')
    page.wait_for_timeout(300)
    budget_after = int(page.text_content('[x-text="budgetWithDis()"]').strip())
    assert budget_after > budget_before


# --- Skill XP costs ---

def test_basic_skill_xp_cost(page, live_server_url):
    """Adding a basic skill rank increases XP spent."""
    _go_to_editor(page, live_server_url)
    page.wait_for_timeout(500)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    click_plus(page, "skill_bragging", 1)
    page.wait_for_timeout(300)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after > spent_before


def test_advanced_skill_costs_more(page, live_server_url):
    """Advanced skill at rank 1 costs more than basic skill at rank 1."""
    _go_to_editor(page, live_server_url)
    spent_before = int(page.text_content('[x-text="grossSpent()"]').strip())
    click_plus(page, "skill_precepts", 1)
    spent_after = int(page.text_content('[x-text="grossSpent()"]').strip())
    assert spent_after - spent_before > 1  # Advanced cost 2 at rank 1
