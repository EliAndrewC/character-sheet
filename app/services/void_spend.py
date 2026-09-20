"""Void-point spending as a server-side operation.

Until the Discord roll commands needed it, spending a void point existed only
in the browser: the allocation order lived in ``roll_math.js``, the deduction
and its school consequences in the sheet's ``deductVoidPoints``, and the
per-roll cap was assembled inline in the View Sheet route. This module is the
one server-side home for all of it:

- ``void_limits`` - the void-point maximum, the per-roll spend cap and the
  Worldliness allowance. ``pages.py`` renders the sheet from this same call,
  so the page and any other caller cannot disagree about a character's cap.
- ``spend_consequences`` - what a school does when a point is spent. Same
  arrangement: the sheet's ``school_abilities`` flags are built from it.
- ``allocate_void_spend`` - the draw order (temporary, then regular, then
  Worldliness). The JS copy in ``roll_math.js`` has to exist because the
  sheet builds its spend menu without a round trip, so the two are pinned to
  one table of cases, ``tests/shared/void_spend_cases.json``, which both
  ``tests/test_void_spend.py`` and ``tests/js/shared_cases.test.js`` run.
- ``plan_void_spend`` / ``apply_void_spend`` - check, then mutate. Split so a
  caller can refuse BEFORE rolling any dice: a refusal must leave no trace.

Nothing here commits. The caller owns the transaction, which is what makes
"the roll is made and the points are gone, or nothing happens" achievable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.game_data import SCHOOLS, void_points_max_shugenja


#: Schools that spend void as shugenja do: a larger pool, a tighter cap.
_SHUGENJA_SCHOOLS = ("shugenja", "isawa_ishi")


class VoidSpendRefused(Exception):
    """The character cannot make this spend. ``str()`` is player-facing."""


@dataclass(frozen=True)
class VoidAllocation:
    """Where the points of one spend come from."""

    from_temp: int = 0
    from_regular: int = 0
    from_worldliness: int = 0

    @property
    def total(self) -> int:
        return self.from_temp + self.from_regular + self.from_worldliness

    def __add__(self, other: "VoidAllocation") -> "VoidAllocation":
        return VoidAllocation(
            self.from_temp + other.from_temp,
            self.from_regular + other.from_regular,
            self.from_worldliness + other.from_worldliness,
        )


@dataclass(frozen=True)
class VoidSpendPlan:
    """A checked spend, ready to apply. ``activation`` is the price of making
    the roll at all (Commune); ``optional`` is the +1k1-per-point spend."""

    activation: VoidAllocation
    optional: VoidAllocation

    @property
    def combined(self) -> VoidAllocation:
        return self.activation + self.optional


def _school_knack_ranks(character_data: Dict[str, Any]) -> Dict[str, int]:
    """Rank of each of the character's OWN school knacks (free rank 1)."""
    school = SCHOOLS.get(character_data.get("school") or "")
    if not school:
        return {}
    knacks = character_data.get("knacks") or {}
    return {k: knacks.get(k, 1) for k in school.school_knacks}


def school_dan(character_data: Dict[str, Any]) -> int:
    ranks = _school_knack_ranks(character_data)
    return min(ranks.values()) if ranks else 0


def void_limits(character_data: Dict[str, Any]) -> Dict[str, int]:
    """``{"void_max", "cap", "worldliness_max"}`` for a character.

    ``cap`` is the most void a single roll may take: the lowest ring, or the
    lowest ring minus one for a shugenja. ``worldliness_max`` is the
    per-adventure allowance of extra points from the Worldliness knack,
    whether it is a school knack or a foreign one.
    """
    rings = character_data.get("rings") or {}
    ring_vals = [rings.get(r, 2) for r in ("Air", "Fire", "Earth", "Water", "Void")]
    school_ranks = _school_knack_ranks(character_data)
    if character_data.get("school") in _SHUGENJA_SCHOOLS:
        void_max = void_points_max_shugenja(rings, school_dan(character_data))
        cap = min(ring_vals) - 1  # lowest ring - 1
    else:
        void_max = min(ring_vals)
        cap = void_max
    if "worldliness" in school_ranks:
        worldliness_max = school_ranks["worldliness"]
    else:
        worldliness_max = (character_data.get("foreign_knacks") or {}).get(
            "worldliness", 0
        )
    return {
        "void_max": void_max,
        "cap": max(0, cap),
        "worldliness_max": worldliness_max,
    }


def spend_consequences(character_data: Dict[str, Any]) -> Dict[str, Any]:
    """What this character's school does whenever they spend void.

    Keys match the sheet's ``school_abilities`` flags, which are built from
    this dict, so the browser and the server apply the same set.
    """
    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    attack = character_data.get("attack", 1)
    yogo = school == "yogo_warden" and dan >= 3
    matsu = school == "matsu_bushi" and dan >= 3
    return {
        # Ide 5th Dan: gain temp VP when spending non-technique VP
        "ide_temp_vp_on_spend": school == "ide_diplomat" and dan >= 5,
        # Yogo Warden 3rd Dan: each VP spent reduces light wounds by 2*attack
        "yogo_vp_heals_lw": yogo,
        "yogo_vp_heal_amount": 2 * attack if yogo else 0,
        # Matsu 3rd Dan: spend VP to bank 3*attack for future wound check bonus
        "matsu_vp_wc_bonus": matsu,
        "matsu_vp_wc_amount": 3 * attack if matsu else 0,
    }


def allocate_void_spend(
    count: Any, temp_avail: Any, regular_avail: Any, worldliness_avail: Any,
) -> Dict[str, Any]:
    """Draw ``count`` points: temporary first (they evaporate), then regular,
    then Worldliness. Mirror of ``L7RRollMath.allocateVoidSpend``, return
    shape included; ``short`` is true when the pools ran dry."""

    def _n(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    want = _n(count)
    from_temp = min(want, _n(temp_avail))
    rem = want - from_temp
    from_regular = min(rem, _n(regular_avail))
    rem -= from_regular
    from_worldliness = min(rem, _n(worldliness_avail))
    allocated = from_temp + from_regular + from_worldliness
    return {
        "fromTemp": from_temp,
        "fromRegular": from_regular,
        "fromWorldliness": from_worldliness,
        "allocated": allocated,
        "short": allocated < want,
    }


def void_pools(character: Any, limits: Dict[str, int]) -> Dict[str, int]:
    """The three pools a spend draws on, as the sheet's ``voidPools`` has them."""
    w_max = limits.get("worldliness_max") or 0
    w_used = int((character.adventure_state or {}).get("worldliness_used") or 0)
    temp = max(0, character.current_temp_void_points or 0)
    regular = max(0, character.current_void_points or 0)
    worldliness = max(0, w_max - w_used) if w_max > 0 else 0
    return {
        "temp": temp,
        "regular": regular,
        "worldliness": worldliness,
        "total": temp + regular + worldliness,
    }


def _points(n: int) -> str:
    return f"{n} void point{'' if n == 1 else 's'}"


def plan_void_spend(
    character: Any, count: int = 0, activation_cost: int = 0,
    roll_label: str = "this roll",
) -> VoidSpendPlan:
    """Check a spend against the character's pools and per-roll cap.

    Mutates nothing. Raises ``VoidSpendRefused`` - naming the number that
    stopped it - if the spend cannot be made in full.
    """
    limits = void_limits(character.to_dict())
    pools = void_pools(character, limits)
    count = max(0, int(count or 0))
    activation_cost = max(0, int(activation_cost or 0))

    # The activation point comes FIRST (Commune: "Spend a void point and roll
    # this knack"). It is drawn off the top, and the optional +1k1 spend is
    # then checked against what REMAINS - it does not lower the per-roll cap,
    # it lowers how many points are left to put against that cap. So a
    # character whose cap is 3 but who holds 2 points can put exactly 1 into
    # a Commune roll. Same order as the sheet's computeVoidOptions(reserve);
    # do not fold the two draws into one check against ``count + cost``.
    act = allocate_void_spend(
        activation_cost, pools["temp"], pools["regular"], pools["worldliness"],
    )
    if act["short"]:
        raise VoidSpendRefused(
            f"{roll_label} costs {_points(activation_cost)} to make, and "
            f"{character.name} has {pools['total']}."
        )
    temp = pools["temp"] - act["fromTemp"]
    regular = pools["regular"] - act["fromRegular"]
    worldliness = pools["worldliness"] - act["fromWorldliness"]
    remaining = temp + regular + worldliness

    if count > limits["cap"]:
        raise VoidSpendRefused(
            f"{character.name} can spend at most {_points(limits['cap'])} on "
            f"a single roll, so {count} is too many."
        )
    opt = allocate_void_spend(count, temp, regular, worldliness)
    if opt["short"]:
        if activation_cost:
            raise VoidSpendRefused(
                f"{character.name} has {_points(pools['total'])}; after the "
                f"{activation_cost} it costs to make {roll_label}, only "
                f"{remaining} can go into the roll, not {count}."
            )
        raise VoidSpendRefused(
            f"{character.name} has {_points(pools['total'])}, not {count}."
        )
    return VoidSpendPlan(
        activation=VoidAllocation(
            act["fromTemp"], act["fromRegular"], act["fromWorldliness"]),
        optional=VoidAllocation(
            opt["fromTemp"], opt["fromRegular"], opt["fromWorldliness"]),
    )


def apply_void_spend(character: Any, plan: VoidSpendPlan) -> None:
    """Deduct a planned spend and apply the school's consequences.

    The Python counterpart of the sheet's ``deductVoidPoints``; both read
    their school flags from ``spend_consequences``. Does not commit.
    """
    spend = plan.combined
    if spend.total <= 0:
        return
    non_temp = spend.from_regular + spend.from_worldliness
    character.current_temp_void_points = (
        (character.current_temp_void_points or 0) - spend.from_temp
    )
    character.current_void_points = (
        (character.current_void_points or 0) - spend.from_regular
    )
    # JSON columns are reassigned, never mutated in place, so SQLAlchemy sees
    # the change (and the tracking revision moves with it).
    state = dict(character.adventure_state or {})
    if spend.from_worldliness:
        state["worldliness_used"] = (
            int(state.get("worldliness_used") or 0) + spend.from_worldliness
        )

    effects = spend_consequences(character.to_dict())
    if effects["ide_temp_vp_on_spend"] and non_temp > 0:
        character.current_temp_void_points += non_temp
    if effects["yogo_vp_heal_amount"]:
        character.current_light_wounds = max(
            0,
            (character.current_light_wounds or 0)
            - spend.total * effects["yogo_vp_heal_amount"],
        )
    if effects["matsu_vp_wc_bonus"]:
        banked = state.get("matsu_banked_wc_bonuses")
        banked = list(banked) if isinstance(banked, list) else []
        banked.extend([effects["matsu_vp_wc_amount"]] * spend.total)
        state["matsu_banked_wc_bonuses"] = banked
    character.adventure_state = state
