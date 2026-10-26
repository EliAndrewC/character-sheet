"""A PC's attack target and weapon in the group's fight (app/services/combat_targets.py,
the ``/combat/fight`` and ``/combat/weapon`` routes, and the locks in the roll routes)."""

import pytest

from app.models import Encounter
from app.services import combat_targets as ct
from app.services import combat_view as cv
from app.services import npcs
from app.services.combat_actions import tn_to_be_hit
from tests.test_combat_actions import GM, OTHER, PLAYER, _url, world  # noqa: F401
from tests.test_roll_sessions import fresh_limits, scripted  # noqa: F401


@pytest.fixture
def fight(world):
    """``world`` plus a second NPC; the PC can reach only the first."""
    s, g, enc = world["s"], world["g"], world["enc"]
    (far,) = npcs.generate(s, g, enc, GM, [{"npc_type": "wave_man", "count": 1, "earned_xp": 50,
                                            "roll_extra": False, "combat_share": 0.74}])
    far.parry = 4
    world["npc"].parry = 2
    world["pc"].is_published = True  # so another player may test-drive its rolls
    npcs.set_reach(s, enc, world["pc"].id, world["npc"].id, True, [world["pc"].id], [world["npc"].id, far.id])
    s.commit()
    world["far"] = far
    return world


def _targets(fight):
    return {t["id"]: t for t in ct.for_pc(fight["s"], fight["pc"])["targets"]}


def _fight_url(fight, path=""):
    return _url(fight, f"/fight/{fight['pc'].id}{path}")


# ---------------------------------------------------------------------------
# The target list
# ---------------------------------------------------------------------------

def test_targets_say_who_is_in_reach_and_hide_unknown_tns(fight):
    near, far = fight["npc"], fight["far"]
    t = _targets(fight)
    assert list(t) == [near.id, far.id]
    assert t[near.id] == {"id": near.id, "name": near.name, "reachable": True, "tn": None, "athletics_tn": None}
    assert t[far.id]["reachable"] is False and t[far.id]["tn"] is None


def test_a_wounded_or_revealed_npcs_tn_is_listed(fight):
    s, enc, near, far = fight["s"], fight["enc"], fight["npc"], fight["far"]
    near.current_light_wounds = 5
    assert ct.reveal(s, enc, far.id)["tn"] == tn_to_be_hit(far)
    t = _targets(fight)
    assert t[near.id]["tn"] == 15 and t[near.id]["athletics_tn"] == 25
    assert t[far.id]["tn"] == 25 and t[far.id]["athletics_tn"] == 45


def test_only_fighting_npcs_are_targets(fight):
    npcs.set_status(fight["s"], fight["enc"], fight["far"], "unconscious")
    assert list(_targets(fight)) == [fight["npc"].id]


def test_no_fight_for_an_npc_a_hidden_pc_or_a_group_without_one(fight):
    s = fight["s"]
    assert ct.for_pc(s, fight["hidden"]) is None
    assert ct.for_pc(s, fight["npc"]) is None
    npcs.end_encounter(s, fight["enc"])
    assert ct.for_pc(s, fight["pc"]) is None


def test_reveal_is_an_operation_and_needs_a_fighting_npc(fight):
    s, enc, near = fight["s"], fight["enc"], fight["npc"]
    rev = enc.rev
    ct.reveal(s, enc, near.id)
    assert enc.rev == rev + 1
    ct.reveal(s, enc, near.id)  # again: nothing new to show
    assert enc.rev == rev + 1
    for bad in (999, "x", True, fight["pc"].id):
        with pytest.raises(LookupError):
            ct.reveal(s, enc, bad)


def test_players_see_a_revealed_tn_on_the_combat_page(fight):
    s, g, enc, near = fight["s"], fight["g"], fight["enc"], fight["npc"]
    row = lambda: next(n for n in cv.public_state(s, g)["npcs"] if n["id"] == near.id)  # noqa: E731
    assert row()["tn_to_be_hit"] is None
    ct.reveal(s, enc, near.id)
    assert row()["tn_to_be_hit"] == tn_to_be_hit(near)


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------

def test_the_gm_sets_and_clears_a_weapon(fight):
    s, enc, pc = fight["s"], fight["enc"], fight["pc"]
    ct.set_weapon(s, enc, pc.id, 5, 2, [pc.id])
    assert ct.for_pc(s, pc)["weapon"] == [5, 2]
    assert cv.gm_state(s, fight["g"])["pcs"][0]["weapon"] == [5, 2]
    ct.set_weapon(s, enc, pc.id, None, None, [pc.id])
    assert ct.for_pc(s, pc)["weapon"] is None
    assert cv.gm_state(s, fight["g"])["pcs"][0]["weapon"] is None


@pytest.mark.parametrize("pc_id,rolled,kept,match", [
    (999, 4, 2, "not in this fight"), (True, 4, 2, "not in this fight"),
    (None, 11, 2, "rolled"), (None, -1, 2, "rolled"), (None, "4", 2, "rolled"),
    (None, 4, 0, "kept"), (None, 4, True, "kept"),
])
def test_bad_weapons_are_refused(fight, pc_id, rolled, kept, match):
    pc = fight["pc"]
    with pytest.raises(ValueError, match=match):
        ct.set_weapon(fight["s"], fight["enc"], pc.id if pc_id is None else pc_id, rolled, kept, [pc.id])


def test_a_new_fight_starts_with_the_last_fights_weapons(client, fight):
    s, enc, pc = fight["s"], fight["enc"], fight["pc"]
    ct.set_weapon(s, enc, pc.id, 3, 3, [pc.id])
    s.commit()
    assert client.post(_url(fight, "/start"), json={"name": "Again", "replace": True}).status_code == 200
    s.expire_all()
    new = npcs.active_encounter(s, fight["g"].id)
    assert new.id != enc.id and new.weapons == {str(pc.id): [3, 3]}
    assert s.query(Encounter).filter(Encounter.gaming_group_id == fight["g"].id).count() == 2


def test_the_first_fight_starts_with_no_weapons(client, world):
    s = world["s"]
    assert client.post(_url(world, "/start"), json={"replace": True}).status_code == 200
    s.expire_all()
    assert npcs.active_encounter(s, world["g"].id).weapons in ({}, None)


def test_weapon_route(client, fight):
    pc = fight["pc"]
    ok = client.post(_url(fight, "/weapon"), json={"pc_id": pc.id, "rolled": 4, "kept": 3})
    assert ok.status_code == 200
    assert client.post(_url(fight, "/weapon"), json={"pc_id": pc.id, "rolled": 40, "kept": 3}).status_code == 400
    assert client.post(_url(fight, "/weapon"), json={"pc_id": pc.id, "rolled": 4, "kept": 3},
                       headers=PLAYER).status_code == 403
    npcs.end_encounter(fight["s"], fight["enc"])
    fight["s"].commit()
    assert client.post(_url(fight, "/weapon"), json={"pc_id": pc.id, "rolled": 4, "kept": 3}).status_code == 409


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_fight_route_for_the_player_the_gm_and_nobody_else(client, fight):
    mine = client.get(_fight_url(fight), headers=PLAYER).json()["fight"]
    assert mine["group_id"] == fight["g"].id and mine["encounter"] == "Ambush"
    assert [t["reachable"] for t in mine["targets"]] == [True, False]
    assert client.get(_fight_url(fight)).status_code == 200  # the GM
    assert client.get(_fight_url(fight), headers=OTHER).status_code == 403
    assert client.get(_fight_url(fight), headers={"X-Test-User": ""}).status_code == 403
    hidden = client.get(_url(fight, f"/fight/{fight['hidden'].id}"), headers=PLAYER)
    assert hidden.status_code == 404
    assert client.get(f"/groups/999/combat/fight/{fight['pc'].id}").status_code == 404


def test_fight_route_without_a_fight(client, fight):
    npcs.end_encounter(fight["s"], fight["enc"])
    fight["s"].commit()
    assert client.get(_fight_url(fight), headers=PLAYER).json() == {"fight": None}
    r = client.post(_fight_url(fight, "/reveal"), json={"npc_id": fight["npc"].id}, headers=PLAYER)
    assert r.status_code == 409


def test_reveal_route(client, fight):
    near = fight["npc"]
    r = client.post(_fight_url(fight, "/reveal"), json={"npc_id": near.id}, headers=PLAYER)
    assert r.status_code == 200
    assert r.json()["target"] == {"id": near.id, "name": near.name, "tn": 15, "athletics_tn": 25}
    assert client.get(_fight_url(fight), headers=PLAYER).json()["fight"]["targets"][0]["tn"] == 15
    assert client.post(_fight_url(fight, "/reveal"), json={"npc_id": 999}, headers=PLAYER).status_code == 404
    assert client.post(_fight_url(fight, "/reveal"), json={"npc_id": near.id}, headers=OTHER).status_code == 403


# ---------------------------------------------------------------------------
# The locks on the roll routes
# ---------------------------------------------------------------------------

def _attack(client, fight, headers=PLAYER, **body):
    body.setdefault("roll_key", "attack")
    body.setdefault("tn", 5)
    return client.post(f"/characters/{fight['pc'].id}/roll", json=body, headers=headers)


def _act(client, fight, sid, action, headers=PLAYER, **args):
    return client.post(f"/characters/{fight['pc'].id}/roll/{sid}/act",
                       json={"action": action, "args": args}, headers=headers)


def test_a_targeted_attack_uses_the_npcs_real_tn_and_reveals_it(client, fight, scripted):
    s, far = fight["s"], fight["far"]
    data = _attack(client, fight, tn=5, target_id=far.id, headers=scripted("5")).json()
    assert data["attack"]["tn"] == 25 and data["formula"]["attack_tn"] == 25
    assert data["formula"]["attack_target_locked"] is True
    s.expire_all()
    assert npcs.link_for(fight["enc"], far.id).tn_revealed is True


def test_the_server_never_trusts_target_numbers_from_the_browser(client, fight, scripted):
    data = _attack(client, fight, tn=10, target_numbers={"tn": 99, "athletics_tn": 99},
                   headers=scripted("5")).json()
    assert data["attack"]["tn"] == 10 and "attack_target_locked" not in data["formula"]


def test_a_simulated_attack_reveals_nothing(client, fight, scripted):
    s, far = fight["s"], fight["far"]
    data = _attack(client, fight, target_id=far.id, headers=scripted("5", base=OTHER)).json()
    assert data["mode"] == "simulate" and data["attack"]["tn"] == 25
    s.expire_all()
    assert npcs.link_for(fight["enc"], far.id).tn_revealed is False


def test_a_target_outside_the_fight_leaves_the_tn_alone(client, fight, scripted):
    npcs.set_status(fight["s"], fight["enc"], fight["far"], "dead")
    fight["s"].commit()
    data = _attack(client, fight, tn=10, target_id=fight["far"].id, headers=scripted("5")).json()
    assert data["attack"]["tn"] == 10


def test_an_athletics_attack_uses_five_plus_ten_times_parry(client, fight, scripted):
    pc = fight["pc"]
    pc.knacks = dict(pc.knacks, athletics=2)
    fight["s"].commit()
    data = _attack(client, fight, roll_key="athletics:attack", tn=5, target_id=fight["npc"].id,
                   headers=scripted("5")).json()
    assert data["attack"]["tn"] == 25


def test_an_arrow_starts_from_the_npcs_tn(client, fight, scripted):
    data = client.post(f"/characters/{fight['pc'].id}/roll", headers=scripted("5"), json={
        "roll_key": "archery", "target_id": fight["far"].id,
        "archery": {"base_tn": 5, "distance": 1, "evasion": True}}).json()
    parts = {p["label"]: p["amount"] for p in data["formula"]["archery_tn_parts"]}
    assert data["formula"]["attack_target_locked"] is True
    assert sum(parts.values()) == data["attack"]["tn"]
    assert 25 in parts.values()  # the base, then distance and evasion on top
    assert data["attack"]["tn"] > 25


def test_a_locked_tn_cannot_be_corrected_at_damage(client, fight, scripted):
    sid = _attack(client, fight, target_id=fight["npc"].id, headers=scripted("9")).json()["session_id"]
    dmg = _act(client, fight, sid, "damage", tn=500, headers=scripted("5"))
    assert dmg.status_code == 200  # the 500 was ignored: still a hit at 15


def test_an_unlocked_tn_can_still_be_corrected(client, fight, scripted):
    sid = _attack(client, fight, tn=5, headers=scripted("9")).json()["session_id"]
    assert "only a hit" in _act(client, fight, sid, "damage", tn=500).json()["error"]


def test_the_gms_weapon_is_the_damage_rolls_weapon(client, fight, scripted):
    s, pc = fight["s"], fight["pc"]
    ct.set_weapon(s, fight["enc"], pc.id, 1, 1, [pc.id])
    s.commit()
    data = _attack(client, fight, headers=scripted("5")).json()
    dmg = _act(client, fight, data["session_id"], "damage", weapon_rolled=4, weapon_kept=2,
               headers=scripted("5")).json()["damage"]
    fire = pc.ring_fire or 2
    assert dmg["formula"]["rolled"] == 1 + fire + data["attack"]["extra_dice"]
    assert dmg["formula"]["kept"] == 1


def test_without_a_gm_weapon_the_modals_weapon_rolls(client, fight, scripted):
    pc = fight["pc"]
    data = _attack(client, fight, headers=scripted("5")).json()
    dmg = _act(client, fight, data["session_id"], "damage", weapon_rolled=4, weapon_kept=2,
               headers=scripted("5")).json()["damage"]
    assert dmg["formula"]["kept"] == 2
    assert dmg["formula"]["rolled"] == 4 + (pc.ring_fire or 2) + data["attack"]["extra_dice"]


# ---------------------------------------------------------------------------
# Iaijutsu duels
# ---------------------------------------------------------------------------

@pytest.fixture
def duel(fight):
    """The PC is in a duel with ``far`` (Fire 4, 150 + 140 XP: TN 29)."""
    s, far = fight["s"], fight["far"]
    far.ring_fire, far.starting_xp, far.earned_xp = 4, 150, 140
    ct.set_duel(s, fight["enc"], fight["pc"].id, far.id, [fight["pc"].id])
    s.commit()
    return fight


def test_the_duel_tn_is_total_xp_over_ten(duel):
    assert ct.duel_tn(duel["far"]) == 29


@pytest.mark.parametrize("total,fire,tn", [
    (0, {"exact": False, "value": 0}, {"exact": False, "value": 0}),
    (20, {"exact": False, "value": 4}, {"exact": False, "value": 20}),   # 20 / 5 = 4: Fire 4 or more
    (25, {"exact": True, "value": 4}, {"exact": False, "value": 25}),    # 5 exceeds Fire 4
    (29, {"exact": True, "value": 4}, {"exact": False, "value": 29}),    # 29 does not exceed TN 29
    (30, {"exact": True, "value": 4}, {"exact": True, "value": 29}),
    (-3, {"exact": False, "value": 0}, {"exact": False, "value": 0}),
])
def test_what_evaluate_stance_reveals(duel, total, fire, tn):
    assert ct.stance(duel["far"], total) == {"name": duel["far"].name, "fire": fire, "tn": tn}


def test_the_fight_names_the_pcs_duel(duel):
    far = duel["far"]
    assert ct.for_pc(duel["s"], duel["pc"])["duel"] == {"id": far.id, "name": far.name, "tn": 29}
    assert cv.public_state(duel["s"], duel["g"])["duels"] == [[duel["pc"].id, far.id]]
    assert cv.gm_state(duel["s"], duel["g"])["duels"] == [[duel["pc"].id, far.id]]


def test_a_downed_opponent_ends_the_duel(duel):
    npcs.set_status(duel["s"], duel["enc"], duel["far"], "dead")
    assert ct.for_pc(duel["s"], duel["pc"])["duel"] is None
    assert cv.public_state(duel["s"], duel["g"])["duels"] == []


def test_the_gm_clears_a_duel_and_bad_duels_are_refused(duel):
    s, enc, pc = duel["s"], duel["enc"], duel["pc"]
    with pytest.raises(ValueError, match="not in this fight"):
        ct.set_duel(s, enc, 999, duel["far"].id, [pc.id])
    with pytest.raises(ValueError, match="not fighting"):
        ct.set_duel(s, enc, pc.id, 999, [pc.id])
    ct.set_duel(s, enc, pc.id, None, [pc.id])
    assert ct.for_pc(s, pc)["duel"] is None


def test_duel_route(client, duel):
    pc, near = duel["pc"], duel["npc"]
    assert client.post(_url(duel, "/duel"), json={"pc_id": pc.id, "npc_id": near.id}).status_code == 200
    assert client.get(_fight_url(duel), headers=PLAYER).json()["fight"]["duel"]["id"] == near.id
    assert client.post(_url(duel, "/duel"), json={"pc_id": pc.id, "npc_id": 999}).status_code == 400
    assert client.post(_url(duel, "/duel"), json={"pc_id": pc.id, "npc_id": None}, headers=PLAYER).status_code == 403
    npcs.end_encounter(duel["s"], duel["enc"])
    duel["s"].commit()
    assert client.post(_url(duel, "/duel"), json={"pc_id": pc.id, "npc_id": None}).status_code == 409


def _strike(client, duel, headers=PLAYER, **body):
    body.update(roll_key="iaijutsu:strike")
    return client.post(f"/characters/{duel['pc'].id}/roll", json=body, headers=headers)


def test_the_strike_is_judged_against_the_dueled_npcs_tn(client, duel, scripted):
    plain = _strike(client, duel, opponent_tn=5, headers=scripted("5")).json()
    assert plain["formula"]["opponent_tn"] == 29
    focused = _strike(client, duel, opponent_tn=5, opponent_focuses=2, headers=scripted("5")).json()
    assert focused["formula"]["opponent_tn"] == 39
    junk = _strike(client, duel, opponent_tn=5, opponent_focuses="x", headers=scripted("5")).json()
    assert junk["formula"]["opponent_tn"] == 29


def test_without_a_duel_the_strike_takes_the_modals_tn(client, fight, scripted):
    data = _strike(client, fight, opponent_tn=17, headers=scripted("5")).json()
    assert data["formula"]["opponent_tn"] == 17


def _evaluate(client, duel, headers=PLAYER):
    return client.post(f"/characters/{duel['pc'].id}/roll", headers=headers,
                       json={"roll_key": "knack:iaijutsu:evaluate"})


def test_evaluate_stance_answers_what_it_revealed(client, duel, scripted):
    pc = duel["pc"]
    pc.knacks = dict(pc.knacks, iaijutsu=3)
    pc.advantages = ["lucky"]
    duel["s"].commit()
    data = _evaluate(client, duel, headers=scripted("2")).json()
    assert data["stance"] == ct.stance(duel["far"], data["total"])
    # A reroll re-answers it at the new total.
    after = _act(client, duel, data["session_id"], "lucky_reroll", headers=scripted("9")).json()
    assert after["total"] != data["total"]
    assert after["stance"] == ct.stance(duel["far"], after["total"])


def test_evaluate_stance_reveals_nothing_to_a_test_drive_or_without_a_duel(client, duel, scripted):
    duel["pc"].knacks = dict(duel["pc"].knacks, iaijutsu=3)
    duel["s"].commit()
    assert "stance" not in _evaluate(client, duel, headers=scripted("9", base=OTHER)).json()
    ct.set_duel(duel["s"], duel["enc"], duel["pc"].id, None, [duel["pc"].id])
    duel["s"].commit()
    assert "stance" not in _evaluate(client, duel, headers=scripted("9")).json()


def test_stance_is_only_for_the_evaluate_roll(duel):
    result = {"total": 30, "mode": "live"}
    ct.add_stance(duel["s"], duel["pc"], "skill:etiquette", result)
    ct.add_stance(duel["s"], duel["pc"], ct.EVALUATE_STANCE_KEY, {"mode": "live"})
    assert "stance" not in result
