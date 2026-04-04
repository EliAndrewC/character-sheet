"""Smoke test — verify the e2e infrastructure works."""


def test_homepage_loads(page, live_server_url):
    page.goto(live_server_url)
    assert page.title() == "L7R — Characters"
