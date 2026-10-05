"""Rolls made with the sheet's own roller for an NPC in a fight are logged
as fight actions (app/services/fight_log.py), so the public combat view
shows them exactly as it showed the combat page's old quick actions."""

import uuid

import pytest

from app.models import Character, EncounterAction
from app.services import combat_view as cv
from app.services import npcs

from tests.test_combat_actions import GM, PLAYER, world  # noqa: F401  (fixture)


def _rid():
    return uuid.uuid4().hex


def _roll(client, npc, dice="5,5,5,5,5,5,5,5,5,5", **body):
    return client.post(f"/characters/{npc.id}/roll", json={"request_id": _rid(), **body},
                       headers={"X-Test-Dice": dice})


def _actions(world):
    s = world["s"]
    s.expire_all()
    return s.query(EncounterAction).filter_by(encounter_id=world["enc"].id).order_by(EncounterAction.id).all()


def _arm(world, values=(3, 7)):
    s, npc = world["s"], world["npc"]
    npc.action_dice = [{"value": v, "spent": False} for v in values]
    s.commit()


def test_an_attack_is_logged_with_its_target_and_outcome(client, world):
    _arm(world)
    pc, npc = world["pc"], world["npc"]
    out = _roll(client, npc, roll_key="attack", tn=5, target_id=pc.id).json()
    assert out["attack"]["hit"] is True
    (a,) = _actions(world)
    assert a.kind == "attack" and a.total == out["total"] and a.target_character_id == pc.id
    assert a.detail["outcome"] == "hit" and a.detail["session_id"] == out["session_id"]
    assert a.round == world["enc"].current_round
    public = cv.public_state(world["s"], world["g"])["npcs"][0]["actions_this_round"]
    assert public[0]["target"] == "Yudai" and public[0]["outcome"] == "hit"


def test_a_missed_attack_then_damage_on_a_hit(client, world):
    _arm(world)
    npc = world["npc"]
    miss = _roll(client, npc, roll_key="attack", tn=200).json()
    assert miss["attack"]["hit"] is False
    hit = _roll(client, npc, roll_key="attack", tn=5).json()
    dmg = client.post(f"/characters/{npc.id}/roll/{hit['session_id']}/act",
                      json={"action": "damage", "args": {"tn": 5}},
                      headers={"X-Test-Dice": "5,5,5,5,5,5,5,5,5,5"}).json()
    first, second = _actions(world)
    assert first.detail["outcome"] == "missed" and "damage" not in first.detail
    assert second.detail["damage"] == dmg["damage"]["total"]


def test_a_target_outside_the_fight_is_not_named(client, world):
    _arm(world)
    out = _roll(client, world["npc"], roll_key="attack", tn=5, target_id=world["hidden"].id)
    assert out.status_code == 200
    (a,) = _actions(world)
    assert a.target_character_id is None


def test_a_parry_is_logged_with_its_outcome_when_the_attack_total_is_given(client, world):
    _arm(world)
    npc = world["npc"]
    out = _roll(client, npc, roll_key="parry", tn=5).json()
    _roll(client, npc, roll_key="parry", tn=999)
    _roll(client, npc, roll_key="parry")
    made, failed, unknown = _actions(world)
    assert made.kind == "parry" and made.total == out["total"] and made.detail["outcome"] == "parried"
    assert failed.detail["outcome"] == "failed"
    assert "outcome" not in unknown.detail


def test_a_feint_is_logged(client, world):
    s, npc = world["s"], world["npc"]
    npc.school, npc.profession = "akodo_bushi", ""
    npc.school_ring_choice = "Water"
    npc.knacks = {"double_attack": 1, "feint": 1, "iaijutsu": 1}
    _arm(world)
    out = _roll(client, npc, roll_key="knack:feint", tn=5, die_index=0).json()
    (a,) = _actions(world)
    assert a.kind == "feint" and a.total == out["total"]
    assert a.detail["outcome"] == ("succeeded" if out["feint"]["success"] else "failed")


def test_other_rolls_and_a_pc_or_an_npc_outside_a_fight_log_nothing(client, world):
    _arm(world)
    s, npc, pc = world["s"], world["npc"], world["pc"]
    _roll(client, npc, roll_key="wound_check")
    assert _actions(world) == []
    pc_roll = client.post(f"/characters/{pc.id}/roll",
                          json={"request_id": _rid(), "roll_key": "attack", "tn": 5},
                          headers={**PLAYER, "X-Test-Dice": "5,5,5,5,5,5,5,5,5,5"})
    assert pc_roll.status_code == 200 and _actions(world) == []
    npcs.end_encounter(s, world["enc"])
    s.commit()
    _roll(client, npc, roll_key="attack", tn=5)
    assert _actions(world) == []


def test_marking_a_die_spent_by_hand_logs_an_action(client, world):
    _arm(world)
    npc = world["npc"]
    r = client.post(f"/characters/{npc.id}/track/op",
                    json={"op": "action_die", "args": {"index": 0, "action": "spend"}})
    assert r.status_code == 200
    (a,) = _actions(world)
    assert a.kind == "other" and a.label == "Action" and a.detail == {"die": 3}
    # A die the roller spends carries a label ("Attack (rolling...)"): not an extra action.
    client.post(f"/characters/{npc.id}/track/op",
                json={"op": "action_die", "args": {"index": 1, "action": "spend", "label": "Attack (rolling...)"}})
    assert len(_actions(world)) == 1


def test_the_hooks_ignore_what_is_not_theirs(client, world):
    from app.services import fight_log

    _arm(world)
    s, npc, pc = world["s"], world["npc"], world["pc"]
    out = _roll(client, npc, roll_key="attack", tn=5).json()
    fight_log.record_act(s, npc, out["session_id"], "damage", {})
    fight_log.record_act(s, npc, out["session_id"], "raise", {"damage": {"total": 9}})
    fight_log.record_act(s, pc, out["session_id"], "damage", {"damage": {"total": 9}})
    fight_log.record_act(s, npc, "no-such-session", "damage", {"damage": {"total": 9}})
    fight_log.record_op(s, npc, "action_die", {"action": "spend", "index": 7})
    fight_log.record_op(s, pc, "action_die", {"action": "spend", "index": 0})
    fight_log.record_op(s, npc, "light_wounds", {"mode": "add", "value": 3})
    (a,) = _actions(world)
    assert "damage" not in a.detail


def test_a_post_roll_rescore_moves_the_total_and_outcome(client, world):
    from app.services import fight_log

    _arm(world)
    s, npc = world["s"], world["npc"]
    parry = _roll(client, npc, roll_key="parry", tn=999).json()
    attack = _roll(client, npc, roll_key="attack", tn=999).json()
    fight_log.record_act(s, npc, parry["session_id"], "raise", {"total": 1000})
    fight_log.record_act(s, npc, attack["session_id"], "raise", {"total": 1000, "attack": {"hit": True}})
    p, a = _actions(world)
    assert p.total == 1000 and p.detail["outcome"] == "parried"
    assert a.total == 1000 and a.detail["outcome"] == "hit"
    plain = _roll(client, npc, roll_key="parry").json()
    fight_log.record_act(s, npc, plain["session_id"], "raise", {"total": 50})
    assert _actions(world)[-1].total == 50 and "outcome" not in _actions(world)[-1].detail
