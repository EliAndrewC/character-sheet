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
    assert t[near.id] == {"id": near.id, "name": near.name, "reachable": True, "tn": None, "athletics_tn": None,
                       "next_phase": None}
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


# ---------------------------------------------------------------------------
# The phase
# ---------------------------------------------------------------------------

def test_the_gm_moves_the_phase_within_0_to_10_and_a_new_round_starts_at_0(fight):
    from app.services import combat_actions as ca
    from tests.test_combat_actions import ConstRng

    s, enc = fight["s"], fight["enc"]
    assert enc.current_phase == 0
    assert ct.set_phase(s, enc, 1) == 1
    assert ct.set_phase(s, enc, -5) == 0
    assert ct.set_phase(s, enc, 40) == 10
    for bad in ("1", True, None, 1.5):
        with pytest.raises(ValueError):
            ct.set_phase(s, enc, bad)
    enc.phase_choices = {"1": {"10": "parry"}}
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    assert enc.current_phase == 0 and enc.phase_choices == {}


def test_phase_route_is_the_gms(client, fight):
    r = client.post(_url(fight, "/phase"), json={"delta": 1})
    assert r.status_code == 200 and r.json() == {"phase": 1}
    assert client.post(_url(fight, "/phase"), json={"delta": "x"}).status_code == 400
    assert client.post(_url(fight, "/phase"), json={"delta": 1}, headers=PLAYER).status_code == 403
    state = client.get(_url(fight, "/state"), headers=PLAYER).json()
    assert state["encounter"]["phase"] == 1
    assert client.get(_fight_url(fight), headers=PLAYER).json()["fight"]["phase"] == 1
    npcs.end_encounter(fight["s"], fight["enc"])
    fight["s"].commit()
    assert client.post(_url(fight, "/phase"), json={"delta": 1}).status_code == 409


def test_next_phase_is_the_lowest_unspent_die_never_before_now(fight):
    npc = fight["npc"]
    npc.action_dice = [{"value": 3, "spent": True}, {"value": 7, "spent": False}, {"value": 5, "spent": False}]
    assert ct.next_phase(npc, 2) == 5
    assert ct.next_phase(npc, 6) == 6  # a held die can be used now
    npc.action_dice = [{"value": 3, "spent": True}]
    assert ct.next_phase(npc, 2) == ct.NO_ACTION_PHASE


def _school(pc, school, dan):
    from app.game_data import SCHOOLS

    pc.school = school
    pc.knacks = {k: dan for k in SCHOOLS[school].school_knacks}


def test_a_kakita_3rd_dan_knows_when_targets_in_reach_act_next(fight):
    s, pc, near, far = fight["s"], fight["pc"], fight["npc"], fight["far"]
    near.action_dice = [{"value": 7, "spent": False}]
    far.action_dice = [{"value": 4, "spent": False}]
    assert _targets(fight)[near.id]["next_phase"] is None  # an Akodo does not
    _school(pc, "kakita_duelist", 3)
    t = _targets(fight)
    assert t[near.id]["next_phase"] == 7
    assert t[far.id]["next_phase"] is None  # out of striking range
    assert t[far.id]["tn"] is None
    _school(pc, "kakita_duelist", 2)
    assert _targets(fight)[near.id]["next_phase"] is None


def test_a_kitsuki_4th_dan_knows_everyones_next_action_and_tn(fight):
    pc, far = fight["pc"], fight["far"]
    far.action_dice = [{"value": 4, "spent": False}]
    _school(pc, "kitsuki_magistrate", 4)
    t = _targets(fight)[far.id]
    assert t["next_phase"] == 4 and t["tn"] == tn_to_be_hit(far)
    _school(pc, "kitsuki_magistrate", 3)
    assert _targets(fight)[far.id]["tn"] is None


def test_a_kakitas_attack_counts_from_the_fights_phase_and_the_targets_next_action(client, fight, scripted):
    s, pc, near = fight["s"], fight["pc"], fight["npc"]
    _school(pc, "kakita_duelist", 3)
    pc.attack = 3
    pc.action_dice = [{"value": 2, "spent": False}]
    near.action_dice = [{"value": 8, "spent": False}]
    fight["enc"].current_phase = 5
    s.commit()
    data = _attack(client, fight, target_id=near.id, die_value=2, kakita_defender_phase=1,
                   headers=scripted("5")).json()
    f = data["formula"]
    assert f["kakita_3rd_dan_attacker_phase"] == 5 and f["kakita_3rd_dan_defender_phase"] == 8
    assert f["kakita_3rd_dan_bonus"] == 3 * (8 - 5)
    assert any(b["label"].startswith("Kakita 3rd Dan (phase 5") for b in f["bonuses"])
    # The phase 0 interrupt names its phase, which stands.
    zero = _attack(client, fight, target_id=near.id, die_value=2, attacker_phase=0,
                   headers=scripted("5")).json()["formula"]
    assert zero["kakita_3rd_dan_attacker_phase"] == 0
    assert any(b["label"].startswith("Kakita 3rd Dan (die 0") for b in zero["bonuses"])


def test_no_remaining_actions_counts_as_phase_11(client, fight, scripted):
    pc, near = fight["pc"], fight["npc"]
    _school(pc, "kakita_duelist", 3)
    pc.attack = 2
    near.action_dice = []
    fight["enc"].current_phase = 4
    fight["s"].commit()
    f = _attack(client, fight, target_id=near.id, headers=scripted("5")).json()["formula"]
    assert f["kakita_3rd_dan_defender_phase"] == 11 and f["kakita_3rd_dan_bonus"] == 2 * (11 - 4)


def test_outside_a_fight_the_modals_phases_stand(client, fight, scripted):
    pc = fight["pc"]
    _school(pc, "kakita_duelist", 3)
    pc.attack = 2
    npcs.end_encounter(fight["s"], fight["enc"])
    fight["s"].commit()
    f = _attack(client, fight, die_value=3, kakita_defender_phase=11, attacker_phase_from_fight=True,
                headers=scripted("5")).json()["formula"]
    assert f["kakita_3rd_dan_attacker_phase"] == 3 and f["kakita_3rd_dan_bonus"] == 2 * 8
    assert any(b["label"].startswith("Kakita 3rd Dan (die 3") for b in f["bonuses"])


def test_shinjo_doji_and_arrows_use_the_fights_phase(client, fight, scripted):
    from app.services.attack_rolls import build_attack

    s, pc = fight["s"], fight["pc"]
    fight["enc"].current_phase = 6
    s.commit()
    body = {"die_value": 2, "shinjo_phase": 9, "doji_phase": 3, "archery": {"phase": 1}}
    ct.lock_phase(s, pc, body)
    assert body["shinjo_phase"] == 6 and body["doji_phase"] == 6 and body["archery"]["phase"] == 6
    unticked = {"doji_phase": 0}
    ct.lock_phase(s, pc, unticked)
    assert unticked["doji_phase"] == 0  # Doji 4th Dan's box was not ticked
    # An arrow: the held die counts to the fight's phase.
    pc.action_dice = [{"value": 2, "spent": False}]
    s.commit()
    data = client.post(f"/characters/{pc.id}/roll", headers=scripted("5"), json={
        "roll_key": "archery", "archery": {"base_tn": 20, "phase": 3, "die_index": 0}}).json()
    held = [b for b in data["formula"]["bonuses"] if b["label"].startswith("held")]
    assert held and held[0]["amount"] == 4  # phase 6 - die 2


# ---------------------------------------------------------------------------
# Per-phase abilities: Mantis posture, Priest blessing
# ---------------------------------------------------------------------------

def test_a_mantis_posture_waits_for_the_fights_phase(client, fight):
    s, pc = fight["s"], fight["pc"]
    _school(pc, "mantis_wave_treader", 1)
    s.commit()

    def posture():
        return client.post(f"/characters/{pc.id}/track/op", headers=PLAYER,
                           json={"op": "mantis_posture", "args": {"type": "offensive"}})

    refused = posture()
    assert refused.status_code == 400 and "phase 0" in refused.json()["error"]
    assert "tracking" in refused.json()
    client.post(_url(fight, "/phase"), json={"delta": 1})
    assert posture().status_code == 200
    assert "phase 2" in posture().json()["error"]
    s.expire_all()
    assert cv.public_state(s, fight["g"])["pcs"][0]["phase_abilities"] == [
        {"kind": "posture", "label": "Posture", "choice": "offensive"}]
    client.post(_url(fight, "/phase"), json={"delta": 1})
    s.expire_all()
    assert cv.gm_state(s, fight["g"])["pcs"][0]["phase_abilities"][0]["choice"] is None
    npcs.end_encounter(s, fight["enc"])
    s.commit()
    assert posture().status_code == 200  # outside a fight: as before


def test_no_mantis_posture_at_phase_0_and_nothing_for_other_schools(fight):
    s, pc, enc = fight["s"], fight["pc"], fight["enc"]
    assert ct.phase_abilities(enc, pc) == []
    _school(pc, "mantis_wave_treader", 1)
    assert ct.phase_abilities(enc, pc) == []  # phase 0 has no posture
    assert ct.phase_abilities(None, pc) == []


def test_a_priests_blessing_is_kept_per_phase(client, fight):
    s, pc, enc = fight["s"], fight["pc"], fight["enc"]
    _school(pc, "priest", 1)
    s.commit()
    url = _fight_url(fight, "/blessing")
    assert ct.phase_abilities(enc, pc) == [
        {"kind": "blessing", "label": "Blessing", "choice": None, "value": None}]
    assert client.post(url, json={"kind": "wound_check"}, headers=PLAYER).status_code == 200
    s.expire_all()
    assert cv.public_state(s, fight["g"])["pcs"][0]["phase_abilities"] == [
        {"kind": "blessing", "label": "Blessing", "choice": "wound checks", "value": "wound_check"}]
    client.post(_url(fight, "/phase"), json={"delta": 1})
    s.expire_all()
    assert ct.phase_abilities(fight["enc"], pc)[0]["choice"] is None  # a new phase, a new pick
    client.post(_url(fight, "/phase"), json={"delta": -1})
    s.expire_all()
    assert ct.phase_abilities(fight["enc"], pc)[0]["value"] == "wound_check"
    # Taken back.
    assert client.post(url, json={"kind": None}, headers=PLAYER).status_code == 200
    s.expire_all()
    assert ct.phase_abilities(fight["enc"], pc)[0]["value"] is None
    assert client.post(url, json={"kind": "luck"}, headers=PLAYER).status_code == 400
    assert client.post(url, json={"kind": "attack"}, headers=OTHER).status_code == 403
    npcs.end_encounter(s, fight["enc"])
    s.commit()
    assert client.post(url, json={"kind": "attack"}, headers=PLAYER).status_code == 409


def test_only_a_priest_or_a_holder_of_the_ritual_blesses_a_phase(fight):
    s, pc, enc = fight["s"], fight["pc"], fight["enc"]
    with pytest.raises(ValueError, match="cannot bless"):
        ct.set_blessing(s, enc, pc, "attack")
    pc.school, pc.knacks, pc.profession = "", {}, "profession"
    pc.profession_abilities = {ct.BLESSING_ABILITY: 1}
    ct.set_blessing(s, enc, pc, "parry")
    assert ct.phase_abilities(enc, pc)[0]["choice"] == "parries"


# ---------------------------------------------------------------------------
# Kitsune Warden 3rd Dan: priest rituals for a free raise
# ---------------------------------------------------------------------------

def _kitsune(pc, dan=3, precepts=2):
    _school(pc, "kitsune_warden", dan)
    pc.skills = {"precepts": precepts}  # 2 x precepts free raises
    pc.adventure_state = {}


def _raises_used(fight):
    fight["s"].expire_all()
    return int((fight["pc"].adventure_state or {}).get("adventure_raises_used", 0))


def test_a_kitsunes_phase_blessing_is_optional_and_costs_a_free_raise(client, fight):
    s, pc, enc = fight["s"], fight["pc"], fight["enc"]
    _kitsune(pc)
    s.commit()
    url = _fight_url(fight, "/blessing")
    assert ct.phase_abilities(enc, pc) == [
        {"kind": "blessing", "label": "Blessing", "choice": None, "value": None, "optional": True}]
    r = client.post(url, json={"kind": "damage"}, headers=PLAYER).json()
    assert r["phase"] == 0 and r["kind"] == "damage"
    assert r["tracking"]["adventure_state"]["adventure_raises_used"] == 1
    client.post(url, json={"kind": "attack"}, headers=PLAYER)  # a change: no second raise
    assert _raises_used(fight) == 1
    client.post(url, json={"kind": None}, headers=PLAYER)  # taken back: the raise returns
    assert _raises_used(fight) == 0
    client.post(url, json={"kind": None}, headers=PLAYER)  # nothing to take back
    assert _raises_used(fight) == 0


def test_a_kitsune_with_no_free_raise_left_cannot_bless(client, fight):
    s, pc = fight["s"], fight["pc"]
    _kitsune(pc, precepts=1)
    pc.adventure_state = {"adventure_raises_used": 2}
    s.commit()
    r = client.post(_fight_url(fight, "/blessing"), json={"kind": "parry"}, headers=PLAYER)
    assert r.status_code == 400 and "no 3rd Dan free raise left" in r.json()["error"]


def test_a_kitsune_below_3rd_dan_has_no_rituals(fight):
    from app.services import special_rolls

    _kitsune(fight["pc"], dan=2)
    assert not ct.can_bless_phase(fight["pc"])
    assert not special_rolls.can_bless(fight["pc"], "topic")


def test_a_priest_blesses_for_free(client, fight):
    s, pc = fight["s"], fight["pc"]
    _school(pc, "priest", 3)
    pc.skills = {"precepts": 2}
    s.commit()
    client.post(_fight_url(fight, "/blessing"), json={"kind": "damage"}, headers=PLAYER)
    assert _raises_used(fight) == 0
    assert "optional" not in ct.phase_abilities(fight["enc"], pc)[0]


def _bless(client, fight, ritual, headers=PLAYER):
    return client.post(f"/characters/{fight['pc'].id}/roll", headers=headers,
                       json={"roll_key": "bless", "ritual": ritual})


def test_a_kitsunes_bless_roll_spends_a_free_raise(client, fight, scripted):
    s, pc = fight["s"], fight["pc"]
    _kitsune(pc, precepts=1)
    s.commit()
    first = _bless(client, fight, "topic", headers=scripted("5"))
    assert first.status_code == 200 and first.json()["formula"]["ritual_raise_cost"] == 1
    assert _raises_used(fight) == 1
    assert _bless(client, fight, "research", headers=scripted("5", base=OTHER)).json()["mode"] == "simulate"
    assert _raises_used(fight) == 1  # a test-drive spends nothing
    _bless(client, fight, "research", headers=scripted("5"))
    assert _raises_used(fight) == 2
    refused = _bless(client, fight, "topic", headers=scripted("5"))
    assert refused.status_code == 400 and "no 3rd Dan free raise left" in refused.json()["error"]


def test_a_priests_bless_roll_costs_nothing(client, fight, scripted):
    s, pc = fight["s"], fight["pc"]
    _school(pc, "priest", 1)
    s.commit()
    data = _bless(client, fight, "topic", headers=scripted("5")).json()
    assert "ritual_raise_cost" not in data["formula"]


def test_a_shinjos_parry_phase_is_the_fights(client, fight, scripted):
    s, pc = fight["s"], fight["pc"]
    _school(pc, "shinjo_bushi", 1)
    pc.skills = {"parry": 2}
    fight["enc"].current_phase = 7
    s.commit()
    sid = client.post(f"/characters/{pc.id}/roll", headers=scripted("5"),
                      json={"roll_key": "parry"}).json()["session_id"]
    total = _act(client, fight, sid, "shinjo_phase", phase=3, die_value=2).json()["total"]
    base = _act(client, fight, sid, "shinjo_phase", phase=0, die_value=7).json()["total"]
    assert total - base == 2 * (7 - 2)  # held from 2 to the fight's 7, whatever was sent
    args = {"phase": 4}
    ct.lock_act_phase(s, pc, "raise", args)
    assert args == {"phase": 4}


def test_a_kitsune_without_precepts_has_no_raises_to_spend(fight):
    from app.services import special_rolls

    _kitsune(fight["pc"], precepts=0)
    assert special_rolls.ritual_raises_left(fight["pc"]) == 0
    with pytest.raises(ValueError, match="no 3rd Dan free raise left"):
        ct.set_blessing(fight["s"], fight["enc"], fight["pc"], "attack")
