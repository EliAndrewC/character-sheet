"""Tests for account-level access grants."""

from app.models import User
from app.services.auth import can_view_drafts, can_edit_character


class TestAccountLevelAccess:
    def test_owner_can_view_own_drafts(self):
        assert can_view_drafts(
            viewer_discord_id="111",
            owner_discord_id="111",
            owner_granted_ids=[],
            admin_ids=["999"],
        )

    def test_admin_can_view_anyone_drafts(self):
        assert can_view_drafts(
            viewer_discord_id="999",
            owner_discord_id="111",
            owner_granted_ids=[],
            admin_ids=["999"],
        )

    def test_granted_user_can_view_drafts(self):
        assert can_view_drafts(
            viewer_discord_id="222",
            owner_discord_id="111",
            owner_granted_ids=["222", "333"],
            admin_ids=["999"],
        )

    def test_random_user_cannot_view_drafts(self):
        assert not can_view_drafts(
            viewer_discord_id="444",
            owner_discord_id="111",
            owner_granted_ids=["222"],
            admin_ids=["999"],
        )

    def test_none_user_cannot_view_drafts(self):
        assert not can_view_drafts(
            viewer_discord_id=None,
            owner_discord_id="111",
            owner_granted_ids=[],
            admin_ids=["999"],
        )


class TestUserGrantedAccounts:
    def test_user_has_granted_ids(self, db):
        user = User(discord_id="111", discord_name="test",
                    granted_account_ids=["222", "333"])
        db.add(user)
        db.flush()
        assert "222" in user.granted_account_ids
        assert "333" in user.granted_account_ids

    def test_user_granted_ids_default_empty(self, db):
        user = User(discord_id="111", discord_name="test")
        db.add(user)
        db.flush()
        assert user.granted_account_ids == [] or user.granted_account_ids is None
