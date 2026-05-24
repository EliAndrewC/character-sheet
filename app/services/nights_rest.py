"""Night's Rest semantics: SW healing cadence, VP regen, per-day pool refresh.

The two endpoints (``GET /characters/{id}/nights-rest/preview`` and
``POST /characters/{id}/nights-rest``) both call ``compute_nights_rest_plan``;
the POST endpoint then calls ``apply_nights_rest`` to mutate the character.

Quick / Slow Healer rules:

- Quick Healer heals +1 extra SW on the first night after receiving NEW SWs
  (so a base-1 night becomes 2). Re-triggers every time SWs increase, not just
  the initial 0->positive transition.
- Slow Healer SUPPRESSES the first night's heal after becoming injured
  (so a base-1 night becomes 0). Only triggers on the 0->positive transition;
  taking more SWs mid-cadence does NOT re-suppress.
- The two are mutually exclusive (EXCLUSIVE_PAIRS in game_data.py).

Alternating cadence (after the first night): heal 1, 0, 1, 0, ... When SW
returns to 0 the cadence resets so the next first-night-after-injury heals.

The accelerate-cadence toggle inverts the cadence determination for the
current rest: a heal night becomes off, an off night becomes heal. With
Quick Healer's +1 bonus this flips 2 -> 0 (the bonus follows the base).
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.game_data import (
    SCHOOLS,
    void_points_max_shugenja,
    void_regen_per_night,
    void_regen_per_night_shugenja,
)
from app.services.rolls import compute_dan


# Adventure-state keys representing combat-in-progress bonuses that
# don't survive a night of sleep. Mirror of the keys cleared by
# ``resetAdventure()`` in sheet.html.
_COMBAT_IN_PROGRESS_KEYS = (
    "akodo_banked_bonuses",
    "hiruma_banked_attack_bonus",
    "bayushi_banked_feint_raise",
    "banked_wc_excess",
    "matsu_banked_wc_bonus",
    "matsu_banked_wc_bonuses",
    "ide_banked_tn_reduce",
    "hida_banked_wc_bonus",
    "mantis_posture_phase",
    "mantis_posture_history",
    "mantis_offensive_3rd_dan_accum",
    "mantis_defensive_3rd_dan_accum",
    "kakita_5th_dan_used",
)


# ---------------------------------------------------------------------------
# Cadence math (pure-Python, no DB access)
# ---------------------------------------------------------------------------


def compute_sw_heal_amount(
    *,
    old_sw: int,
    has_quick_healer: bool,
    has_slow_healer: bool,
    received_new_since_rest: bool,
    became_injured_since_rest: bool,
    last_rest_was_healing_night: bool,
    accelerate: bool,
) -> int:
    """Compute how many SW a Night's Rest heals from the given state.

    See module docstring for rule explanation. Keyword-only so callers
    can't accidentally transpose the seven booleans.
    """
    assert not (has_quick_healer and has_slow_healer), (
        "Quick Healer and Slow Healer are mutually exclusive"
    )
    if old_sw <= 0:
        return 0

    if received_new_since_rest:
        if has_slow_healer and became_injured_since_rest:
            base = 0
        else:
            base = 2 if has_quick_healer else 1
    else:
        base = 1 if not last_rest_was_healing_night else 0

    if accelerate:
        # Flip the cadence for this rest. The Quick Healer bonus rides
        # on the base, so a 2-heal flips all the way to 0.
        base = 0 if base > 0 else 1

    return min(base, old_sw)


# ---------------------------------------------------------------------------
# Helpers for per-day pool detection and VP regen
# ---------------------------------------------------------------------------


# Display name lookup for the per-day pools surfaced in the modal.
# Kept here rather than pulled from KNACKS / SCHOOLS so the modal copy
# stays stable even if upstream rename a knack.
_PER_DAY_POOL_NAMES = {
    "conviction": "Conviction",
    "absorb_void": "Absorb Void",
    "togashi_daily_athletics_raises": "Daily Athletics Raises",
}


def _per_day_pool_ids(character) -> List[str]:
    """Return the adventure-state pool ids that refresh on a Night's Rest.

    Mirrors the per-day flag logic in ``routes/pages.py`` for the
    per-adventure tracker. Order matches the order they appear in the
    sheet so the modal effects list reads naturally.
    """
    ids: List[str] = []
    knacks = character.knacks or {}
    foreign = character.foreign_knacks or {}
    if "conviction" in knacks or "conviction" in foreign:
        ids.append("conviction")
    if character.school == "isawa_ishi" and (
        "absorb_void" in knacks or "absorb_void" in foreign
    ):
        ids.append("absorb_void")
    if character.school == "togashi_ise_zumi":
        dan = compute_dan(knacks)
        precepts = (character.skills or {}).get("precepts", 0)
        if dan >= 3 and precepts > 0:
            ids.append("togashi_daily_athletics_raises")
    return ids


def _void_regen_amount(character) -> int:
    """How many VP this character regains per Night's Rest before the cap."""
    rings = {
        "Air": character.ring_air,
        "Fire": character.ring_fire,
        "Earth": character.ring_earth,
        "Water": character.ring_water,
        "Void": character.ring_void,
    }
    if character.school in ("shugenja", "isawa_ishi"):
        return void_regen_per_night_shugenja(rings)
    return void_regen_per_night(rings)


def _void_max(character) -> int:
    """Maximum VP this character can hold (mirrors pages.py)."""
    rings = {
        "Air": character.ring_air,
        "Fire": character.ring_fire,
        "Earth": character.ring_earth,
        "Water": character.ring_water,
        "Void": character.ring_void,
    }
    if character.school in ("shugenja", "isawa_ishi"):
        knacks = character.knacks or {}
        school_rank = compute_dan(knacks)
        return void_points_max_shugenja(rings, school_rank)
    return min(rings.values())


def _combat_in_progress_clear_effects(character) -> List[Dict[str, Any]]:
    """Effect-list bullets for combat-state items that will be wiped."""
    effects: List[Dict[str, Any]] = []
    action_dice = character.action_dice or []
    if action_dice:
        n = len(action_dice)
        word = "die" if n == 1 else "dice"
        effects.append({
            "key": "clear_action_dice",
            "label": f"Clear {n} initiative {word}",
        })
    precepts = character.precepts_pool or []
    if precepts:
        n = len(precepts)
        word = "die" if n == 1 else "dice"
        effects.append({
            "key": "clear_precepts_pool",
            "label": f"Clear combat dice pool ({n} {word})",
        })
    state = character.adventure_state or {}
    if (
        state.get("mantis_posture_history")
        or state.get("mantis_posture_phase")
        or state.get("mantis_offensive_3rd_dan_accum")
        or state.get("mantis_defensive_3rd_dan_accum")
    ):
        effects.append({
            "key": "clear_mantis_posture",
            "label": "Clear Mantis posture tracker",
        })
    banked_keys = (
        "akodo_banked_bonuses", "hiruma_banked_attack_bonus",
        "bayushi_banked_feint_raise", "banked_wc_excess",
        "matsu_banked_wc_bonus", "matsu_banked_wc_bonuses",
        "ide_banked_tn_reduce", "hida_banked_wc_bonus",
    )
    banked_count = 0
    for k in banked_keys:
        v = state.get(k)
        if not v:
            continue
        if isinstance(v, list):
            banked_count += len(v)
        else:
            banked_count += 1
    if banked_count:
        word = "bonus" if banked_count == 1 else "bonuses"
        effects.append({
            "key": "clear_banked_bonuses",
            "label": f"Clear {banked_count} banked combat {word}",
        })
    if (character.current_temp_void_points or 0) > 0:
        n = character.current_temp_void_points
        word = "point" if n == 1 else "points"
        effects.append({
            "key": "clear_temp_void",
            "label": f"Clear {n} temporary void {word}",
        })
    if state.get("kakita_5th_dan_used"):
        effects.append({
            "key": "clear_kakita_5th_dan_used",
            "label": "Reset Kakita 5th Dan once-per-round flag",
        })
    return effects


# ---------------------------------------------------------------------------
# Plan computation
# ---------------------------------------------------------------------------


def compute_nights_rest_plan(character, accelerate: bool = False) -> Dict[str, Any]:
    """Compute the preview payload for a Night's Rest on this character.

    Returns a dict matching the GET /nights-rest/preview response shape:
    ``{would_change, effects, sw_remaining_after, alt_effects}``. The
    alt_effects diff is only populated when SW will remain after the
    default heal (so the modal's accelerate checkbox makes sense).
    """
    effects: List[Dict[str, Any]] = []

    # 1. Combat-in-progress clears first - these are the "you slept it off"
    #    items that read most naturally at the top of the bullet list.
    effects.extend(_combat_in_progress_clear_effects(character))

    # 2. Light wounds
    lw = character.current_light_wounds or 0
    if lw > 0:
        word = "wound" if lw == 1 else "wounds"
        effects.append({
            "key": "heal_lw",
            "label": f"Heal {lw} light {word}",
            "amount": lw,
        })

    # 3. Void points
    vp = character.current_void_points or 0
    vmax = _void_max(character)
    if vp < vmax:
        regen = min(_void_regen_amount(character), vmax - vp)
        if regen > 0:
            word = "point" if regen == 1 else "points"
            effects.append({
                "key": "restore_vp",
                "label": f"Restore {regen} void {word}",
                "amount": regen,
            })

    # 4. Per-day pool refreshes
    state = character.adventure_state or {}
    for pool_id in _per_day_pool_ids(character):
        used = state.get(pool_id + "_used", 0)
        if used > 0:
            name = _PER_DAY_POOL_NAMES.get(pool_id, pool_id)
            effects.append({
                "key": f"refresh_{pool_id}",
                "label": f"Refresh {name} (regain {used})",
                "amount": used,
            })

    # 5. SW healing line. Per user decision #1: when SW > 0 we ALWAYS show
    #    this line (even "Heal 0 serious wounds") so the accelerate
    #    checkbox has something to toggle.
    old_sw = character.current_serious_wounds or 0
    heal = compute_sw_heal_amount(
        old_sw=old_sw,
        has_quick_healer="quick_healer" in (character.advantages or []),
        has_slow_healer="slow_healer" in (character.disadvantages or []),
        received_new_since_rest=bool(character.sw_healing_received_new_since_rest),
        became_injured_since_rest=bool(character.sw_healing_became_injured_since_rest),
        last_rest_was_healing_night=bool(character.sw_healing_last_rest_was_healing_night),
        accelerate=accelerate,
    )
    sw_after = max(0, old_sw - heal)
    if old_sw > 0:
        word = "wound" if heal == 1 else "wounds"
        effects.append({
            "key": "heal_sw",
            "label": f"Heal {heal} serious {word}",
            "amount": heal,
        })

    # 6. Alt-effects diff for the accelerate toggle. Only meaningful when
    #    the (default) rest leaves SW > 0.
    alt_effects: List[Dict[str, Any]] = []
    if sw_after > 0:
        alt_heal = compute_sw_heal_amount(
            old_sw=old_sw,
            has_quick_healer="quick_healer" in (character.advantages or []),
            has_slow_healer="slow_healer" in (character.disadvantages or []),
            received_new_since_rest=bool(character.sw_healing_received_new_since_rest),
            became_injured_since_rest=bool(character.sw_healing_became_injured_since_rest),
            last_rest_was_healing_night=bool(character.sw_healing_last_rest_was_healing_night),
            accelerate=not accelerate,
        )
        word = "wound" if alt_heal == 1 else "wounds"
        alt_effects.append({
            "key": "heal_sw",
            "label": f"Heal {alt_heal} serious {word}",
            "amount": alt_heal,
        })

    return {
        "would_change": bool(effects),
        "effects": effects,
        "sw_remaining_after": sw_after,
        "alt_effects": alt_effects,
    }


# ---------------------------------------------------------------------------
# Apply (mutation)
# ---------------------------------------------------------------------------


def apply_nights_rest(character, accelerate: bool = False) -> Dict[str, Any]:
    """Mutate the character to apply a Night's Rest. Returns a summary dict.

    The caller is responsible for ``db.commit()``. Mirrors the effect set
    computed by ``compute_nights_rest_plan`` but ALSO clears combat-in-
    progress state when there isn't anything else to clear (the preview
    won't have shown a bullet for it, but it's still correct to wipe it).
    """
    # SW healing -- compute BEFORE we touch anything, because the
    # post-rest flag updates depend on the heal amount.
    old_sw = character.current_serious_wounds or 0
    heal = compute_sw_heal_amount(
        old_sw=old_sw,
        has_quick_healer="quick_healer" in (character.advantages or []),
        has_slow_healer="slow_healer" in (character.disadvantages or []),
        received_new_since_rest=bool(character.sw_healing_received_new_since_rest),
        became_injured_since_rest=bool(character.sw_healing_became_injured_since_rest),
        last_rest_was_healing_night=bool(character.sw_healing_last_rest_was_healing_night),
        accelerate=accelerate,
    )
    new_sw = max(0, old_sw - heal)
    character.current_serious_wounds = new_sw

    # Cadence flag updates
    if new_sw == 0:
        character.sw_healing_received_new_since_rest = False
        character.sw_healing_became_injured_since_rest = False
        character.sw_healing_last_rest_was_healing_night = False
    else:
        character.sw_healing_last_rest_was_healing_night = heal > 0
        character.sw_healing_received_new_since_rest = False
        character.sw_healing_became_injured_since_rest = False

    # Light wounds
    character.current_light_wounds = 0

    # Void points (regen capped at max)
    vmax = _void_max(character)
    regen = _void_regen_amount(character)
    character.current_void_points = min(
        vmax, (character.current_void_points or 0) + regen
    )

    # Temp VP are per-combat-round; clear on rest.
    character.current_temp_void_points = 0

    # Per-day pool refresh
    # SQLAlchemy doesn't reliably detect in-place dict mutation for a JSON
    # column, so we rebuild the dict and reassign.
    state = dict(character.adventure_state or {})
    for pool_id in _per_day_pool_ids(character):
        state[pool_id + "_used"] = 0

    # Combat-in-progress wipe (banked bonuses, mantis tracker, kakita flag).
    for k in _COMBAT_IN_PROGRESS_KEYS:
        state.pop(k, None)

    character.adventure_state = state

    # Action dice / precepts pool
    character.action_dice = []
    character.precepts_pool = []

    return {
        "sw_healed": heal,
        "sw_remaining": new_sw,
        "lw_healed_to_zero": True,
        "vp_after": character.current_void_points,
    }
