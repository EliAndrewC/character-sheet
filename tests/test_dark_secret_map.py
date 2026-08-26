"""Dark Secret map: layout computation + the GM-only page route."""

import math

from app.models import Character, GamingGroup, User
from app.services.dark_secret import DARK_SECRET_ID
from app.services.dark_secret_map import (
    CIRCLE_CX, CIRCLE_CY, CIRCLE_R, HALO_COLUMN_X, NODE_CLEARANCE,
    arrow_path, build_dark_secret_map,
)

ADMIN = "183026066498125825"
P1, P2, P3 = "player_1", "player_2", "player_3"
NONADMIN_HEADERS = {"X-Test-User": f"{P1}:Player One"}


class _Char:
    def __init__(self, id, name, owner, secret_known_by=None, has_secret=False):
        self.id = id
        self.name = name
        self.owner_discord_id = owner
        self.disadvantages = ["dark_secret"] if has_secret else []
        self.advantage_details = (
            {DARK_SECRET_ID: {"text": "s", "player": secret_known_by or ""}}
            if has_secret else {}
        )


def _no_art(_c):
    return None


class TestArrowPath:
    def test_trimmed_to_clear_both_nodes(self):
        src, dst = (0.0, 0.0), (400.0, 0.0)
        geom = arrow_path(src, dst)
        parts = geom["d"].split()
        sx, sy = float(parts[1]), float(parts[2])
        ex, ey = float(parts[-2]), float(parts[-1])
        assert math.hypot(sx - src[0], sy - src[1]) >= NODE_CLEARANCE - 1
        assert math.hypot(ex - dst[0], ey - dst[1]) >= NODE_CLEARANCE + 10
        assert 100 < geom["label_x"] < 300

    def test_reverse_arrows_bend_opposite_ways(self):
        a = arrow_path((0.0, 0.0), (400.0, 0.0))
        b = arrow_path((400.0, 0.0), (0.0, 0.0))
        assert (a["label_y"] > 0) != (b["label_y"] > 0)

    def test_overlapping_nodes_fall_back_to_stub(self):
        # Nodes closer than the two clearances: the trim points cross, so
        # the arrow collapses to a short stub around the midpoint.
        geom = arrow_path((0.0, 0.0), (100.0, 0.0))
        assert geom["d"].startswith("M ")
        assert 40 <= geom["label_x"] <= 60
        # Practically coincident nodes: neither trim triggers, whole curve kept.
        geom2 = arrow_path((0.0, 0.0), (10.0, 0.0))
        assert geom2["d"].startswith("M 0.0 0.0")


class TestBuildMap:
    def test_holders_and_knowers_on_circle_others_haloed(self):
        chars = [
            _Char(1, "Alice", P1, has_secret=True, secret_known_by=P2),
            _Char(2, "Bob", P2, has_secret=True, secret_known_by=P1),
            _Char(3, "Carol", P3),
        ]
        m = build_dark_secret_map(chars, {}, _no_art)
        nodes = {n["id"]: n for n in m["nodes"]}
        assert not nodes[1]["halo"] and not nodes[2]["halo"]
        assert nodes[3]["halo"] and nodes[3]["x"] == HALO_COLUMN_X
        for nid in (1, 2):
            r = math.hypot(nodes[nid]["x"] - CIRCLE_CX, nodes[nid]["y"] - CIRCLE_CY)
            assert abs(r - CIRCLE_R) < 1
        pairs = {(a["from"], a["to"]) for a in m["arrows"]}
        assert pairs == {(2, 1), (1, 2)}
        arrow = next(a for a in m["arrows"] if a["from"] == 2)
        assert arrow["holder_name"] == "Alice" and arrow["knower_name"] == "Bob"
        assert arrow["ghost"] is False
        assert m["holder_count"] == 2

    def test_knower_without_character_becomes_ghost_node(self):
        chars = [_Char(1, "Alice", P1, has_secret=True, secret_known_by=P3)]
        m = build_dark_secret_map(chars, {P3: "Phil"}, _no_art)
        ghost = next(n for n in m["nodes"] if n["kind"] == "player")
        assert ghost["name"] == "Phil" and ghost["id"] == f"player:{P3}"
        assert m["arrows"][0]["ghost"] is True
        assert m["arrows"][0]["knower_name"] == "Phil"
        # Unknown player id falls back to the raw id.
        m2 = build_dark_secret_map(chars, {}, _no_art)
        assert next(n for n in m2["nodes"] if n["kind"] == "player")["name"] == P3

    def test_unchosen_knower_flagged_and_no_arrow(self):
        chars = [_Char(1, "Alice", P1, has_secret=True)]
        m = build_dark_secret_map(chars, {}, _no_art)
        assert m["arrows"] == []
        assert m["nodes"][0]["knower_unchosen"] is True
        assert m["nodes"][0]["holds_secret"] is True
        # Single ring node sits at the centre.
        assert (m["nodes"][0]["x"], m["nodes"][0]["y"]) == (CIRCLE_CX, CIRCLE_CY)

    def test_knowing_player_with_two_characters_gets_two_arrows(self):
        chars = [
            _Char(1, "Alice", P1, has_secret=True, secret_known_by=P2),
            _Char(2, "Bob", P2),
            _Char(3, "Bobby", P2),
        ]
        m = build_dark_secret_map(chars, {}, _no_art)
        assert {a["from"] for a in m["arrows"]} == {2, 3}
        assert all(not n["halo"] for n in m["nodes"])

    def test_halo_column_spacing_and_unnamed_fallback(self):
        chars = [_Char(1, "", P1), _Char(2, "Zed", P2), _Char(3, "Yan", P3)]
        m = build_dark_secret_map(chars, {}, _no_art)
        ys = [n["y"] for n in m["nodes"]]
        assert ys == sorted(ys) and len(set(ys)) == 3
        assert m["nodes"][0]["name"] == "Character #1"
        assert m["arrows"] == []

    def test_headshot_resolver_used(self):
        chars = [_Char(1, "Alice", P1)]
        m = build_dark_secret_map(chars, {}, lambda c: f"/art/{c.id}.webp")
        assert m["nodes"][0]["headshot_url"] == "/art/1.webp"


def _seed_group(client):
    sess = client._test_session_factory()
    for did, name in ((P1, "Player One"), (P2, "Player Two"), (P3, "Player Three")):
        sess.add(User(discord_id=did, discord_name=name, display_name=name))
    g = GamingGroup(name="Tuesday")
    sess.add(g)
    sess.commit()
    chars = [
        Character(name="Alice", school="akodo_bushi", owner_discord_id=P1, gaming_group_id=g.id,
                  is_published=True, disadvantages=["dark_secret"],
                  advantage_details={DARK_SECRET_ID: {"text": "the-secret-text", "player": P2}}),
        Character(name="Bob", school="akodo_bushi", owner_discord_id=P2, gaming_group_id=g.id,
                  is_published=True),
        Character(name="Carol", school="akodo_bushi", owner_discord_id=P3, gaming_group_id=g.id,
                  is_published=True),
        Character(name="Hidden", school="akodo_bushi", owner_discord_id=P3, gaming_group_id=g.id,
                  is_published=True, is_hidden=True),
    ]
    sess.add_all(chars)
    sess.commit()
    return g.id


class TestMapRoute:
    def test_admin_gets_map(self, client):
        gid = _seed_group(client)
        resp = client.get(f"/groups/{gid}/dark-secrets")
        assert resp.status_code == 200
        body = resp.text
        assert "Alice's dark secret is known by Bob" in body.replace("&#39;", "'")
        assert "knows the secret of" in body
        assert 'data-testid="ds-halo"' in body
        assert "Carol has no dark secret and knows no dark secrets" in body
        assert "Hidden" not in body.split("ds-map")[1]
        # The secret text itself is not part of the map.
        assert "the-secret-text" not in body

    def test_non_admin_forbidden(self, client):
        gid = _seed_group(client)
        assert client.get(f"/groups/{gid}/dark-secrets", headers=NONADMIN_HEADERS).status_code == 403
        client.headers.pop("X-Test-User", None)
        assert client.get(f"/groups/{gid}/dark-secrets").status_code == 403

    def test_unknown_or_empty_group_404(self, client):
        assert client.get("/groups/999/dark-secrets").status_code == 404
        sess = client._test_session_factory()
        g = GamingGroup(name="Empty")
        sess.add(g)
        sess.commit()
        assert client.get(f"/groups/{g.id}/dark-secrets").status_code == 404

    def test_group_summary_chip_links_for_admin_only(self, client):
        gid = _seed_group(client)
        admin_page = client.get(f"/groups/{gid}").text
        assert f'href="/groups/{gid}/dark-secrets"' in admin_page
        assert 'data-testid="dark-secret-map-link"' in admin_page
        player_page = client.get(f"/groups/{gid}", headers=NONADMIN_HEADERS).text
        assert "/dark-secrets" not in player_page
        assert 'data-dis-id="dark_secret"' in player_page
