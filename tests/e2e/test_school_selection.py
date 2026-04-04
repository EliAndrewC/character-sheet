"""E2E: School selection via HTMX and its effects on the form."""


def test_school_selection_loads_details(page, live_server_url):
    """Selecting a school should load its details via HTMX."""
    page.goto(f"{live_server_url}/characters/new")

    # Initially no school details
    details = page.text_content("#school-details")
    assert "Special Ability" not in details

    # Select a school
    page.select_option('select[name="school"]', "hida_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    details = page.text_content("#school-details")
    assert "Water" in details  # School ring
    assert "counterattack" in details.lower()  # School knack


def test_switching_schools_updates_details(page, live_server_url):
    """Changing the school should replace the details panel."""
    page.goto(f"{live_server_url}/characters/new")

    # Select Akodo Bushi
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('feint')", timeout=5000)
    assert "feint" in page.text_content("#school-details").lower()

    # Switch to Kakita Duelist
    page.select_option('select[name="school"]', "kakita_duelist")
    page.wait_for_selector("#school-details :text('Phase 0')", timeout=5000)
    details = page.text_content("#school-details")
    assert "Fire" in details  # Kakita's school ring
    assert "lunge" in details.lower()  # Kakita's knack


def test_school_knack_selectors_appear(page, live_server_url):
    """School selection should show knack rank selectors."""
    page.goto(f"{live_server_url}/characters/new")

    page.select_option('select[name="school"]', "mirumoto_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Should have selectors for the 3 school knacks
    assert page.locator('select[name="knack_counterattack"]').is_visible()
    assert page.locator('select[name="knack_double_attack"]').is_visible()
    assert page.locator('select[name="knack_iaijutsu"]').is_visible()


def test_school_techniques_shown(page, live_server_url):
    """School details should show all 5 Dan techniques."""
    page.goto(f"{live_server_url}/characters/new")

    page.select_option('select[name="school"]', "courtier")
    page.wait_for_selector("#school-details :text('Special Ability')")

    details = page.text_content("#school-details")
    assert "1st Dan" in details
    assert "2nd Dan" in details
    assert "3rd Dan" in details
    assert "4th Dan" in details
    assert "5th Dan" in details
