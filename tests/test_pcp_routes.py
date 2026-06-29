"""Tests for the Player Character Point spend / undo routes."""

from app.models import Character, CharacterVersion


OWNER = "183026066498125825"  # default test user (admin + owner)
NONEDITOR = {"X-Test-User": "999000111:Stranger"}


def _seed_clean_published(client, **kwargs):
    """Insert a published + clean character (publish_status == 'published')."""
    session = client._test_session_factory()
    defaults = dict(
        name="Test Samurai",
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=OWNER,
        is_published=True,
    )
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.flush()
    c.published_state = c.to_dict()  # clean: draft == published
    session.commit()
    assert c.publish_status == "published"
    return c.id


def _versions(client, char_id):
    return (
        client._test_session_factory()
        .query(CharacterVersion)
        .filter(CharacterVersion.character_id == char_id)
        .count()
    )


def _char(client, char_id):
    return (
        client._test_session_factory()
        .query(Character)
        .filter(Character.id == char_id)
        .first()
    )


class TestSpendPcp:
    def test_first_spend_reroll(self, client):
        cid = _seed_clean_published(client)
        before = _versions(client, cid)
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "reroll"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "spent"
        assert data["use"] == "reroll"
        assert data["pcp_count"] == 1
        assert data["pcp_total_cost"] == 1
        assert data["pcp_next_cost"] == 2
        assert _char(client, cid).pcp_count == 1
        # A new version was persisted immediately.
        assert _versions(client, cid) == before + 1

    def test_second_spend_escalates_cost(self, client):
        cid = _seed_clean_published(client, pcp_count=1)
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "free_raise"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pcp_count"] == 2
        assert data["pcp_total_cost"] == 3  # 1 + 2
        assert data["pcp_next_cost"] == 3

    def test_void_refresh_regains_a_void_point(self, client):
        cid = _seed_clean_published(client, current_void_points=0)
        resp = client.post(
            f"/characters/{cid}/spend-pcp", json={"use": "void_refresh"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pcp_count"] == 1
        assert data["void_max"] == 2  # all rings 2 except Water 3 -> min 2
        assert data["current_void_points"] == 1
        assert _char(client, cid).current_void_points == 1

    def test_void_refresh_caps_at_void_max(self, client):
        cid = _seed_clean_published(client, current_void_points=2)
        resp = client.post(
            f"/characters/{cid}/spend-pcp", json={"use": "void_refresh"}
        )
        assert resp.status_code == 200
        # Already at max (2); stays at max, but the PCP is still spent.
        assert resp.json()["current_void_points"] == 2
        assert _char(client, cid).pcp_count == 1

    def test_non_void_use_does_not_touch_void(self, client):
        cid = _seed_clean_published(client, current_void_points=1)
        client.post(f"/characters/{cid}/spend-pcp", json={"use": "reroll_tens"})
        assert _char(client, cid).current_void_points == 1

    def test_invalid_use_rejected(self, client):
        cid = _seed_clean_published(client)
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "bogus"})
        assert resp.status_code == 400
        assert _char(client, cid).pcp_count == 0

    def test_missing_use_rejected(self, client):
        cid = _seed_clean_published(client)
        resp = client.post(f"/characters/{cid}/spend-pcp", json={})
        assert resp.status_code == 400

    def test_malformed_json_body_rejected(self, client):
        cid = _seed_clean_published(client)
        resp = client.post(
            f"/characters/{cid}/spend-pcp", content="not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert _char(client, cid).pcp_count == 0

    def test_gate_rejects_modified_character(self, client):
        cid = _seed_clean_published(client)
        session = client._test_session_factory()
        ch = session.query(Character).filter(Character.id == cid).first()
        ch.honor = 4.0  # pending draft edit -> "modified"
        session.commit()
        assert _char(client, cid).publish_status == "modified"
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "reroll"})
        assert resp.status_code == 409
        assert _char(client, cid).pcp_count == 0

    def test_gate_rejects_unpublished_character(self, client):
        cid = _seed_clean_published(client)
        session = client._test_session_factory()
        ch = session.query(Character).filter(Character.id == cid).first()
        ch.is_published = False
        session.commit()
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "reroll"})
        assert resp.status_code == 409

    def test_non_editor_forbidden(self, client):
        cid = _seed_clean_published(client)
        resp = client.post(
            f"/characters/{cid}/spend-pcp", json={"use": "reroll"},
            headers=NONEDITOR,
        )
        assert resp.status_code == 403
        assert _char(client, cid).pcp_count == 0

    def test_unauthenticated_rejected(self, client):
        cid = _seed_clean_published(client)
        client.headers.pop("X-Test-User", None)
        resp = client.post(f"/characters/{cid}/spend-pcp", json={"use": "reroll"})
        assert resp.status_code == 401

    def test_not_found(self, client):
        resp = client.post("/characters/999999/spend-pcp", json={"use": "reroll"})
        assert resp.status_code == 404


class TestUndoPcp:
    def test_undo_decrements_and_publishes_permanently(self, client):
        cid = _seed_clean_published(client, pcp_count=2)
        before = _versions(client, cid)
        resp = client.post(f"/characters/{cid}/undo-pcp")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pcp_count"] == 1
        assert data["pcp_total_cost"] == 1   # cost dropped from 3 to 1
        assert data["pcp_next_cost"] == 2
        ch = _char(client, cid)
        assert ch.pcp_count == 1
        # Undo immediately publishes a version and leaves the character clean
        # (so the cost reduction is permanent and a later Discard can't restore
        # the higher count) - the bug from character 21.
        assert _versions(client, cid) == before + 1
        assert ch.publish_status == "published"
        assert ch.published_state["pcp_count"] == 1

    def test_undo_cannot_be_reverted_by_discard(self, client):
        """Regression for char 21: undo must survive a Discard (it's published,
        not a draft), so the lowered cost sticks."""
        from app.services.versions import discard_draft_changes
        cid = _seed_clean_published(client, pcp_count=3)
        client.post(f"/characters/{cid}/undo-pcp")           # 3 -> 2, published
        session = client._test_session_factory()
        ch = session.query(Character).filter(Character.id == cid).first()
        # A Discard now (no pending changes) must NOT bring the count back up.
        discard_draft_changes(ch, session)
        session.commit()
        assert _char(client, cid).pcp_count == 2

    def test_undo_blocked_when_modified(self, client):
        cid = _seed_clean_published(client, pcp_count=2)
        session = client._test_session_factory()
        ch = session.query(Character).filter(Character.id == cid).first()
        ch.honor = 4.0  # pending draft edit -> "modified"
        session.commit()
        resp = client.post(f"/characters/{cid}/undo-pcp")
        assert resp.status_code == 409
        assert _char(client, cid).pcp_count == 2  # unchanged

    def test_undo_with_no_spends_rejected(self, client):
        cid = _seed_clean_published(client, pcp_count=0)
        resp = client.post(f"/characters/{cid}/undo-pcp")
        assert resp.status_code == 409

    def test_undo_non_editor_forbidden(self, client):
        cid = _seed_clean_published(client, pcp_count=1)
        resp = client.post(f"/characters/{cid}/undo-pcp", headers=NONEDITOR)
        assert resp.status_code == 403

    def test_undo_unauthenticated_rejected(self, client):
        cid = _seed_clean_published(client, pcp_count=1)
        client.headers.pop("X-Test-User", None)
        resp = client.post(f"/characters/{cid}/undo-pcp")
        assert resp.status_code == 401

    def test_undo_not_found(self, client):
        resp = client.post("/characters/999999/undo-pcp")
        assert resp.status_code == 404


class TestPcpInEditorXpEndpoint:
    def test_xp_endpoint_returns_pcp_fields_from_body(self, client):
        cid = _seed_clean_published(client, pcp_count=2)
        resp = client.post(f"/characters/{cid}/xp", json={"pcp_count": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pcp_count"] == 2
        assert data["pcp_cost"] == 3
        assert data["pcp_next_cost"] == 3

    def test_xp_endpoint_falls_back_to_persisted_pcp_count(self, client):
        cid = _seed_clean_published(client, pcp_count=3)
        # Body omits pcp_count -> use the persisted value (3 -> cost 6).
        resp = client.post(f"/characters/{cid}/xp", json={})
        assert resp.json()["pcp_cost"] == 6


class TestPcpAutosave:
    def test_autosave_persists_pcp_decrement_as_draft_change(self, client):
        cid = _seed_clean_published(client, pcp_count=2)
        # Re-publish clean at count 2.
        session = client._test_session_factory()
        ch = session.query(Character).filter(Character.id == cid).first()
        ch.published_state = ch.to_dict()
        session.commit()
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"pcp_count": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["has_unpublished_changes"] is True
        assert _char(client, cid).pcp_count == 1

    def test_autosave_clamps_negative_pcp_count(self, client):
        cid = _seed_clean_published(client, pcp_count=0)
        client.post(f"/characters/{cid}/autosave", json={"pcp_count": -5})
        assert _char(client, cid).pcp_count == 0


class TestPcpSheetRender:
    """The View Sheet must render with the PCP confirmation modal + summary
    wiring (catches Jinja/context errors before the clicktests run)."""

    def test_sheet_renders_with_pcp_context(self, client):
        cid = _seed_clean_published(client, pcp_count=2)
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # Confirmation modal + summary card markup is shipped.
        assert 'data-modal="pcp-confirm"' in resp.text
        assert 'Spend a Player Character Point?' in resp.text
        assert 'data-xp-card="pcp"' in resp.text
        # Editor sees the void-refresh entry point and the undo control.
        assert 'data-action="pcp-void-refresh"' in resp.text
        assert 'data-action="pcp-undo"' in resp.text
        # Every roll-result panel carries its PCP options (rules/10).
        for action in (
            "pcp-reroll-attack", "pcp-raise-attack", "pcp-reroll-tens-attack",
            "pcp-reroll-damage",
            "pcp-reroll-wc", "pcp-raise-wc",
            "pcp-reroll-duel-contested", "pcp-raise-duel-contested",
            "pcp-reroll-tens-duel-contested",
            "pcp-reroll-duel-strike", "pcp-raise-duel-strike",
            "pcp-reroll-duel-damage",
        ):
            assert f'data-action="{action}"' in resp.text, action
        # The PCP free-raise +5 is listed in every panel's bonus breakdown.
        for testid in (
            "pcp-raise-line", "pcp-raise-line-attack", "pcp-raise-line-wc",
            "pcp-raise-line-duel-contested", "pcp-raise-line-duel-strike",
        ):
            assert f'data-testid="{testid}"' in resp.text, testid

    def test_sheet_renders_for_non_editor_without_undo(self, client):
        cid = _seed_clean_published(client, pcp_count=1)
        resp = client.get(f"/characters/{cid}", headers=NONEDITOR)
        assert resp.status_code == 200
        # Read-only viewers still get the confirm modal (walk-through) but no
        # editor-only controls.
        assert 'data-modal="pcp-confirm"' in resp.text
        assert 'data-action="pcp-undo"' not in resp.text
        assert 'data-action="pcp-void-refresh"' not in resp.text

    def test_edit_page_renders_pcp_undo_line(self, client):
        cid = _seed_clean_published(client, pcp_count=3)
        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200
        assert 'data-testid="pcp-editor-line"' in resp.text
        assert 'pcpCount: 3' in resp.text
