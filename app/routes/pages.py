"""Page routes — serve full HTML pages via Jinja2 templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES,
    ADVANTAGE_DETAIL_FIELDS,
    EXCLUSIVE_PAIRS,
    SCHOOLS,
    SCHOOLS_BUSHI_NONBUSHI,
    SCHOOLS_WITH_TEMP_VOID,
    SCHOOL_RING_OPTIONS,
    SCHOOL_TECHNIQUE_BONUSES,
    SKILLS,
    SCHOOL_KNACKS,
    SPELLS_BY_ELEMENT,
    Ring,
)
from app.models import Character, CharacterVersion, GamingGroup, User as UserModel
from app.services.auth import can_view_drafts, get_admin_ids, is_admin, can_edit_character, format_editor_list_text
from app.services.dice import build_all_roll_formulas, is_impaired
from app.services.rolls import compute_skill_roll
from app.services.status import compute_effective_status
from app.services.xp import calculate_total_xp, calculate_xp_breakdown, validate_character

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return _templates().TemplateResponse(request=request, name="terms.html")


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return _templates().TemplateResponse(request=request, name="privacy.html")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    user_id = user["discord_id"] if user else None

    all_characters = db.query(Character).order_by(Character.updated_at.desc()).all()
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

    # Cluster characters by gaming group; omit empty groups; trailing "not assigned"
    grouped: list = []
    for group in all_groups:
        chars_in_group = [c for c in all_characters if c.gaming_group_id == group.id]
        if chars_in_group:
            grouped.append((group.name, chars_in_group))
    unassigned = [c for c in all_characters if c.gaming_group_id is None]
    if unassigned:
        grouped.append(("Not assigned to a group", unassigned))

    # Build owner display name lookup
    owner_ids = {c.owner_discord_id for c in all_characters if c.owner_discord_id}
    owners = db.query(UserModel).filter(UserModel.discord_id.in_(owner_ids)).all() if owner_ids else []
    owner_names = {u.discord_id: u.display_name or u.discord_name for u in owners}

    return _templates().TemplateResponse(
        request=request,
        name="index.html",
        context={
            "characters": all_characters,
            "grouped": grouped,
            "owner_names": owner_names,
        },
    )


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request):
    """Redirect to POST — new character creation is done via POST /characters."""
    return RedirectResponse("/", status_code=303)


@router.get("/characters/{char_id}", response_class=HTMLResponse)
def view_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    user = getattr(request.state, "user", None)
    user_id = user["discord_id"] if user else None

    # Determine if viewer can edit
    from app.services.auth import can_view_drafts
    from app.models import User as UserModel
    owner = db.query(UserModel).filter(UserModel.discord_id == character.owner_discord_id).first()
    owner_granted = owner.granted_account_ids or [] if owner else []
    viewer_can_edit = can_view_drafts(user_id, character.owner_discord_id, owner_granted)

    # Everyone sees the current draft state
    char_dict = character.to_dict()

    xp_breakdown = calculate_xp_breakdown(char_dict)
    errors = validate_character(char_dict)
    school = SCHOOLS.get(character.school)

    # Build the knack list for this character's school
    char_knacks = {}
    if school:
        for knack_id in school.school_knacks:
            knack_data = SCHOOL_KNACKS.get(knack_id)
            rank = character.knacks.get(knack_id, 1) if character.knacks else 1
            char_knacks[knack_id] = {"data": knack_data, "rank": rank}

    # Dan = lowest school knack
    knack_ranks = [char_knacks[k]["rank"] for k in char_knacks] if char_knacks else [0]
    dan = min(knack_ranks) if knack_ranks else 0

    # Load party members in the same gaming group, if any.
    party_members_data: list = []
    daidoji_counterattack_party: list = []  # party members with Daidoji 3rd Dan counterattack raises
    if character.gaming_group_id:
        party_chars = (
            db.query(Character)
            .filter(
                Character.gaming_group_id == character.gaming_group_id,
                Character.id != char_id,
            )
            .all()
        )
        for p in party_chars:
            party_members_data.append({
                "name": p.name,
                "advantages": p.advantages or [],
                "disadvantages": p.disadvantages or [],
                "campaign_advantages": p.campaign_advantages or [],
                "campaign_disadvantages": p.campaign_disadvantages or [],
            })
            # Check if this party member is a Daidoji with 3rd Dan counterattack raises
            if p.school == "daidoji_yojimbo":
                p_school = SCHOOLS.get(p.school)
                if p_school:
                    p_knack_ranks = [
                        (p.knacks or {}).get(k, 1) for k in p_school.school_knacks
                    ]
                    p_dan = min(p_knack_ranks) if p_knack_ranks else 0
                    if p_dan >= 3:
                        p_attack = (p.skills or {}).get("attack", 1)
                        daidoji_counterattack_party.append({
                            "name": p.name,
                            "raises": p_attack,
                            "bonus": p_attack * 5,
                        })

    effective = compute_effective_status(char_dict, party_members=party_members_data)
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

    # Pre-compute every roll formula needed by the click-to-roll UI on the sheet.
    roll_formulas = build_all_roll_formulas(char_dict)
    is_impaired_now = is_impaired(char_dict)

    # Viewer's dice preferences (default both on if missing)
    viewer = db.query(UserModel).filter(UserModel.discord_id == user_id).first() if user_id else None
    viewer_prefs = (viewer.preferences or {}) if viewer else {}
    user_prefs = {
        "dice_animation_enabled": viewer_prefs.get("dice_animation_enabled", True),
        "dice_sound_enabled": viewer_prefs.get("dice_sound_enabled", True),
    }

    # Compute roll info for each skill. Party members are passed in so that
    # group-wide disadvantage notes (e.g. Thoughtless) surface inline on the
    # affected skills (just Tact for Thoughtless) instead of as a separate
    # Party Effects section.
    skill_rolls = {}
    for sid in (char_dict.get("skills") or {}):
        roll = compute_skill_roll(sid, char_dict, party_members=party_members_data)
        if roll.rolled > 0:
            skill_rolls[sid] = roll

    # Compute per-adventure abilities
    per_adventure = []
    advantages = character.advantages or []
    disadvantages = character.disadvantages or []

    # 3rd Dan free raises
    tech_bonuses = SCHOOL_TECHNIQUE_BONUSES.get(character.school, {})
    if dan >= 3 and tech_bonuses.get("third_dan"):
        t3 = tech_bonuses["third_dan"]
        source_skill = t3["source_skill"]
        source_rank = (character.skills or {}).get(source_skill, 0)
        if source_rank > 0:
            skill_name = SKILLS[source_skill].name if source_skill in SKILLS else source_skill
            per_adventure.append({
                "id": "adventure_raises",
                "name": f"3rd Dan Free Raises ({skill_name})",
                "type": "counter",
                "max": 2 * source_rank,
            })

    # Lucky / Unlucky
    if "lucky" in advantages:
        per_adventure.append({"id": "lucky_used", "name": "Lucky (re-roll)", "type": "toggle"})
    if "unlucky" in disadvantages:
        per_adventure.append({"id": "unlucky_used", "name": "Unlucky (GM penalty)", "type": "toggle"})

    # Spendable knacks: conviction, otherworldliness, worldliness
    for knack_id in ("conviction", "otherworldliness", "worldliness"):
        if knack_id in char_knacks:
            knack_rank = char_knacks[knack_id]["rank"]
            knack_name = char_knacks[knack_id]["data"].name
            pool_max = knack_rank * 2 if knack_id == "otherworldliness" else knack_rank
            per_adventure.append({
                "id": knack_id,
                "name": knack_name,
                "type": "counter",
                "max": pool_max,
            })

    # Compute void points max and void-spend config
    ring_vals = [char_dict["rings"].get(r, 2) for r in ("Air", "Fire", "Earth", "Water", "Void")]
    if character.school in ("shugenja", "isawa_ishi"):
        from app.game_data import void_points_max_shugenja
        school_rank = min(char_knacks[k]["rank"] for k in char_knacks) if char_knacks else 0
        void_max = void_points_max_shugenja(
            char_dict["rings"], school_rank
        )
        void_spend_cap = min(ring_vals) - 1  # lowest ring - 1
    else:
        void_max = min(ring_vals)
        void_spend_cap = void_max
    worldliness_max = char_knacks["worldliness"]["rank"] if "worldliness" in char_knacks else 0
    # Mirumoto 5th Dan: VP provides +10 on combat rolls (in addition to +1k1)
    mirumoto_5th_dan_bonus = 10 if character.school == "mirumoto_bushi" and dan >= 5 else 0
    # Akodo 4th Dan: VP on wound checks also gives a free raise (+5 each)
    akodo_4th_dan_wc_raise = character.school == "akodo_bushi" and dan >= 4
    # Yogo Warden 4th Dan: VP on wound checks also gives a free raise (+5 each)
    yogo_4th_dan_wc_raise = character.school == "yogo_warden" and dan >= 4

    attack_skill = char_dict.get("attack", 1)
    void_spend_config = {
        "cap": max(0, void_spend_cap),
        "worldliness_max": worldliness_max,
        "combat_vp_flat_bonus": mirumoto_5th_dan_bonus,
        "wc_vp_free_raise": akodo_4th_dan_wc_raise or yogo_4th_dan_wc_raise,
    }

    # School-specific ability flags for client-side conditional UI
    school_abilities = {
        # Togashi 5th Dan: spend 1 VP to heal 2 serious wounds
        "togashi_heal_sw": character.school == "togashi_ise_zumi" and dan >= 5,
        # Hida 4th Dan: trade 2 SW to reset light wounds to 0
        "hida_trade_sw": character.school == "hida_bushi" and dan >= 4,
        # Ide 5th Dan: gain temp VP when spending non-technique VP
        "ide_temp_vp_on_spend": character.school == "ide_diplomat" and dan >= 5,
        # Yogo Warden 3rd Dan: each VP spent reduces light wounds by 2*attack
        "yogo_vp_heals_lw": character.school == "yogo_warden" and dan >= 3,
        "yogo_vp_heal_amount": 2 * attack_skill if character.school == "yogo_warden" and dan >= 3 else 0,
        # Matsu 3rd Dan: spend VP to bank 3*attack for future wound check bonus
        "matsu_vp_wc_bonus": character.school == "matsu_bushi" and dan >= 3,
        "matsu_vp_wc_amount": 3 * attack_skill if character.school == "matsu_bushi" and dan >= 3 else 0,
        # Matsu 5th Dan: defender LW reset to 15 after dealing serious wounds
        "matsu_lw_reset_15": character.school == "matsu_bushi" and dan >= 5,
        # Akodo 5th Dan: spend VP after damage to deal 10 LW per VP back
        "akodo_reflect_damage": character.school == "akodo_bushi" and dan >= 5,
        # Isawa Duelist 3rd Dan: trade -5 TN for +3*attack on attack
        "isawa_tn_trade": character.school == "isawa_duelist" and dan >= 3,
        "isawa_tn_trade_bonus": 3 * attack_skill if character.school == "isawa_duelist" and dan >= 3 else 0,
        # Otaku 4th Dan: lunge always rolls extra damage die even if parried
        "otaku_lunge_extra_die": character.school == "otaku_bushi" and dan >= 4,
        # Brotherhood 3rd Dan: adventure raises can lower action die by 5
        "brotherhood_lower_action_die": character.school == "brotherhood_of_shinsei_monk" and dan >= 3,
        # Shosuro 5th Dan: add lowest 3 dice to result on TN/contested rolls
        "shosuro_add_lowest_3": character.school == "shosuro_actor" and dan >= 5,
        # Matsu 4th Dan: miss by <20 on double attack = hit with no extra damage
        "matsu_near_miss": character.school == "matsu_bushi" and dan >= 4,
        # Ide 4th Dan: +1 VP nightly regen (display only)
        "ide_extra_vp_regen": character.school == "ide_diplomat" and dan >= 4,
        # Brotherhood 4th Dan: failed parries don't lower rolled damage dice
        "brotherhood_parry_no_reduce": character.school == "brotherhood_of_shinsei_monk" and dan >= 4,
        # Yogo Warden Special: gain temp VP when taking serious wounds
        "yogo_temp_vp_on_sw": character.school == "yogo_warden",
        # Mirumoto Special: gain temp VP after any parry roll
        "mirumoto_temp_vp_on_parry": character.school == "mirumoto_bushi",
        # Akodo Special: gain 4 temp VP on successful feint, 1 on unsuccessful
        "akodo_temp_vp_on_feint": character.school == "akodo_bushi",
        # Bayushi 4th Dan: free raise on future attack after any feint
        "bayushi_post_feint_raise": character.school == "bayushi_bushi" and dan >= 4,
        # Otaku 5th Dan: trade 10 rolled damage dice for 1 auto serious wound
        "otaku_trade_dice_for_sw": character.school == "otaku_bushi" and dan >= 5,
        # Ikoma 4th Dan: 10-dice floor on damage for unparried attacks without extra kept
        "ikoma_10_dice_floor": character.school == "ikoma_bard" and dan >= 4,
        # Mirumoto 4th Dan: failed parries vs double attacks preserve auto SW; vs regular halve reduction
        "mirumoto_parry_modifier": character.school == "mirumoto_bushi" and dan >= 4,
        # Isawa Duelist 5th Dan: bank wound check excess for future wound check
        "isawa_bank_wc_excess": character.school == "isawa_duelist" and dan >= 5,
        # Shinjo 5th Dan: bank parry excess for future wound check
        "shinjo_bank_parry_excess": character.school == "shinjo_bushi" and dan >= 5,
        # Bayushi Special: +1k1 per VP spent on attack damage
        "bayushi_vp_damage": character.school == "bayushi_bushi",
        # Feint knack: 1 temp VP on successful feint (non-Akodo feint schools)
        "feint_temp_vp": character.school in ("bayushi_bushi", "yogo_warden", "hiruma_scout", "ide_diplomat"),
        # Hiruma 3rd Dan: bank +2*attack for next attack and damage after parry
        "hiruma_post_parry_bonus": character.school == "hiruma_scout" and dan >= 3,
        "hiruma_post_parry_amount": 2 * attack_skill if character.school == "hiruma_scout" and dan >= 3 else 0,
        # Akodo 3rd Dan: bank wound check excess * attack for attack bonus
        "akodo_wc_attack_bonus": character.school == "akodo_bushi" and dan >= 3,
        "akodo_attack_skill": attack_skill if character.school == "akodo_bushi" and dan >= 3 else 0,
        # Courtier 4th Dan: temp VP after successful attack or manipulation
        "courtier_temp_vp_on_hit": character.school == "courtier" and dan >= 4,
        # Togashi 4th Dan: reroll any contested roll after seeing result
        "togashi_reroll_contested": character.school == "togashi_ise_zumi" and dan >= 4,
        # Ide Special: feint -> lower target TN by 10
        "ide_feint_tn_reduce": character.school == "ide_diplomat",
        # Hiruma 5th Dan: attacker deals 10 fewer LW after parry (display note)
        "hiruma_parry_reduce_lw": character.school == "hiruma_scout" and dan >= 5,
        # Bayushi 3rd Dan: feints deal Xk1 damage
        "bayushi_feint_damage": character.school == "bayushi_bushi" and dan >= 3,
        "bayushi_feint_damage_rolled": attack_skill if character.school == "bayushi_bushi" and dan >= 3 else 0,
        # Shiba 3rd Dan: parries deal (2X)k1 damage
        "shiba_parry_damage": character.school == "shiba_bushi" and dan >= 3,
        "shiba_parry_damage_rolled": 2 * attack_skill if character.school == "shiba_bushi" and dan >= 3 else 0,
        # Daidoji 3rd Dan: X free raises to wound check from counterattack
        "daidoji_counterattack_raises": character.school == "daidoji_yojimbo" and dan >= 3,
        "daidoji_counterattack_raises_amount": attack_skill if character.school == "daidoji_yojimbo" and dan >= 3 else 0,
        # Hida 3rd Dan: reroll 2X on counterattack, X on other attacks
        "hida_reroll": character.school == "hida_bushi" and dan >= 3,
        "hida_reroll_x": attack_skill if character.school == "hida_bushi" and dan >= 3 else 0,
        # Togashi 3rd Dan: 4X daily athletics raises (X = precepts skill)
        "togashi_daily_athletics_raises": character.school == "togashi_ise_zumi" and dan >= 3,
        "togashi_daily_raises_max": 4 * (char_dict.get("skills") or {}).get("precepts", 0) if character.school == "togashi_ise_zumi" and dan >= 3 else 0,
        "togashi_daily_raises_per_roll": (char_dict.get("skills") or {}).get("precepts", 0) if character.school == "togashi_ise_zumi" and dan >= 3 else 0,
        # Merchant Special: spend VP after seeing roll
        "merchant_post_roll_vp": character.school == "merchant",
        # Shiba 5th Dan: lower opponent TN after parry (display note)
        "shiba_parry_lower_tn": character.school == "shiba_bushi" and dan >= 5,
        # Daidoji 5th Dan: lower attacker TN after wound check (display note)
        "daidoji_wc_lower_tn": character.school == "daidoji_yojimbo" and dan >= 5,
        # Kitsuki 5th Dan: reduce target rings (display note)
        "kitsuki_reduce_rings": character.school == "kitsuki_magistrate" and dan >= 5,
        # Mirumoto 3rd Dan: 2X points per round
        "mirumoto_round_points": character.school == "mirumoto_bushi" and dan >= 3,
        "mirumoto_round_points_max": 2 * attack_skill if character.school == "mirumoto_bushi" and dan >= 3 else 0,
        # Ide Diplomat 3rd Dan: spend VP to subtract Xk1 from someone's roll
        "ide_subtract_roll": character.school == "ide_diplomat" and dan >= 3,
        "ide_subtract_x": (char_dict.get("skills") or {}).get("tact", 0) if character.school == "ide_diplomat" and dan >= 3 else 0,
        # Isawa Ishi 3rd Dan: spend VP to add Xk1 to someone's roll
        "ishi_add_roll": character.school == "isawa_ishi" and dan >= 3,
        "ishi_add_x": (char_dict.get("skills") or {}).get("precepts", 0) if character.school == "isawa_ishi" and dan >= 3 else 0,
        # Kuni Witch Hunter 5th Dan: reflect damage
        "kuni_reflect_damage": character.school == "kuni_witch_hunter" and dan >= 5,
        # Hida 5th Dan: bank counterattack excess for wound check bonus
        "hida_counterattack_wc_bonus": character.school == "hida_bushi" and dan >= 5,
    }

    # Compute wound check probability slice for client-side display.
    # We pre-compute prob[reroll][rolled,kept,X] for X=0..150 at each void
    # spending level so the client can show a probability table without
    # downloading the full ~720KB probability tables.
    from app.data import prob as _prob_table
    wc_formula = roll_formulas.get("wound_check", {})
    wc_base_rolled = wc_formula.get("rolled", 3)
    wc_base_kept = wc_formula.get("kept", 2)
    wc_flat = wc_formula.get("flat", 0)
    wc_probs = {"flat": wc_flat, "void_cap": void_spend_cap}
    max_target = 151
    # Probability slices for reroll=True (normal) at each void level
    wc_probs["probs"] = {}
    for v in range(void_spend_cap + 1):
        r, k = wc_base_rolled + v, wc_base_kept + v
        # Apply 10k10 caps
        if r > 10:
            k += r - 10
            r = 10
        if k > 10:
            k = 10
        key = f"{r},{k}"
        if key not in wc_probs["probs"]:
            wc_probs["probs"][key] = [
                round(_prob_table[True][r, k, x], 4) for x in range(max_target)
            ]
    # Also include a no-reroll slice for iaijutsu strike wound checks (base only)
    r, k = wc_base_rolled, wc_base_kept
    wc_probs["probs_no_reroll"] = {
        f"{r},{k}": [
            round(_prob_table[False][r, k, x], 4) for x in range(max_target)
        ]
    }
    # Map void count -> rolled,kept key (after caps)
    wc_probs["void_keys"] = {}
    for v in range(void_spend_cap + 1):
        r, k = wc_base_rolled + v, wc_base_kept + v
        if r > 10: k += r - 10; r = 10
        if k > 10: k = 10
        wc_probs["void_keys"][str(v)] = f"{r},{k}"

    # Compute attack probability slices for each attack-type formula
    attack_probs = {}
    reroll_for_attack = not is_impaired_now
    for key, formula in roll_formulas.items():
        if not formula.get("is_attack_type"):
            continue
        base_r = formula["rolled"]
        base_k = formula["kept"]
        flat = formula.get("flat", 0)
        ap = {"flat": flat, "void_cap": void_spend_cap}
        ap["probs"] = {}
        ap["avgs"] = {}
        ap["void_keys"] = {}
        for v in range(void_spend_cap + 1):
            r, k = base_r + v, base_k + v
            if r > 10: k += r - 10; r = 10
            if k > 10: k = 10
            rk = f"{r},{k}"
            ap["void_keys"][str(v)] = rk
            if rk not in ap["probs"]:
                ap["probs"][rk] = [
                    round(_prob_table[reroll_for_attack][r, k, x], 4)
                    for x in range(151)
                ]
                ap["avgs"][rk] = round(_prob_table[reroll_for_attack].get((r, k), 0), 2)
        attack_probs[key] = ap

    # Damage average lookup table: avg of NkM with reroll-10s for reasonable combos
    damage_avgs = {}
    for r in range(1, 16):
        for k in range(1, min(r + 1, 11)):
            damage_avgs[f"{r},{k}"] = round(_prob_table[True].get((r, k), 0), 2)

    # Get version history
    versions = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == char_id)
        .order_by(CharacterVersion.version_number.desc())
        .all()
    )

    return _templates().TemplateResponse(
        request=request,
        name="character/sheet.html",
        context={
            "character": character,
            "char_dict": char_dict,
            "school": school,
            "xp_breakdown": xp_breakdown,
            "errors": errors,
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "campaign_advantages": CAMPAIGN_ADVANTAGES,
            "campaign_disadvantages": CAMPAIGN_DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
            "char_knacks": char_knacks,
            "dan": dan,
            "spells_by_element": SPELLS_BY_ELEMENT,
            "effective": effective,
            "skill_rolls": skill_rolls,
            "viewer_can_edit": viewer_can_edit,
            "versions": versions,
            "owner_display_name": (owner.display_name or owner.discord_name) if owner else character.player_name,
            "advantage_detail_fields": ADVANTAGE_DETAIL_FIELDS,
            "advantage_details": character.advantage_details or {},
            "player_names": {u.discord_id: u.display_name or u.discord_name
                             for u in db.query(UserModel).all()},
            "per_adventure": per_adventure,
            "void_max": void_max,
            "adventure_state": character.adventure_state or {},
            "all_groups": all_groups,
            "roll_formulas": roll_formulas,
            "is_impaired_now": is_impaired_now,
            "user_prefs": user_prefs,
            "void_spend_config": void_spend_config,
            "wound_check_probs": wc_probs,
            "attack_probs": attack_probs,
            "damage_avgs": damage_avgs,
            "has_temp_void": character.school in SCHOOLS_WITH_TEMP_VOID,
            "school_abilities": school_abilities,
            "daidoji_counterattack_party": daidoji_counterattack_party,
        },
    )


@router.get("/characters/{char_id}/edit", response_class=HTMLResponse)
def edit_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    from app.models import User as UserModel
    from app.services.auth import get_all_editors
    owner = db.query(UserModel).filter(UserModel.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return HTMLResponse("You don't have permission to edit this character.", status_code=403)

    char_dict = character.to_dict()
    xp_breakdown = calculate_total_xp(char_dict)
    school = SCHOOLS.get(character.school)

    # Build knacks dict for the school_info partial
    knacks = {}
    if school:
        knacks = {kid: SCHOOL_KNACKS.get(kid) for kid in school.school_knacks}

    viewer_is_admin = is_admin(user["discord_id"])
    all_players = db.query(UserModel).order_by(UserModel.display_name).all()
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

    name_by_id = {p.discord_id: (p.display_name or p.discord_name) for p in all_players}
    editor_list_text = format_editor_list_text(
        viewer_id=user["discord_id"],
        all_editors=all_editors,
        admin_ids=get_admin_ids(),
        resolve_name=lambda _id: name_by_id.get(_id, ""),
    )

    return _templates().TemplateResponse(
        request=request,
        name="character/edit.html",
        context={
            "character": character,
            "char_dict": char_dict,
            "school": school,
            "xp": xp_breakdown,
            "schools": SCHOOLS,
            "schools_by_category": SCHOOLS_BUSHI_NONBUSHI,
            "rings": [r.value for r in Ring],
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
            "knacks": knacks,
            "technique_bonuses": SCHOOL_TECHNIQUE_BONUSES,
            "campaign_advantages": CAMPAIGN_ADVANTAGES,
            "campaign_disadvantages": CAMPAIGN_DISADVANTAGES,
            "school_ring_options": SCHOOL_RING_OPTIONS,
            "viewer_is_admin": viewer_is_admin,
            "all_players": all_players,
            "all_groups": all_groups,
            "exclusive_pairs": EXCLUSIVE_PAIRS,
            "advantage_detail_fields": ADVANTAGE_DETAIL_FIELDS,
            "is_first_version": not character.is_published,
            "editor_list_text": editor_list_text,
        },
    )


# ---------------------------------------------------------------------------
# Profile & Account Access
# ---------------------------------------------------------------------------


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    user_obj = db.query(UserModel).filter(
        UserModel.discord_id == user["discord_id"]
    ).first()

    # All other registered users (for grant/revoke UI)
    all_users = db.query(UserModel).order_by(UserModel.discord_name).all()
    other_users = [u for u in all_users if u.discord_id != user["discord_id"]]

    admin_ids = get_admin_ids()
    granted_ids = set(user_obj.granted_account_ids or [])

    return _templates().TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "user_obj": user_obj,
            "other_users": other_users,
            "admin_ids": admin_ids,
            "granted_ids": granted_ids,
        },
    )


@router.post("/profile", response_class=HTMLResponse)
async def update_profile(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    user_obj = db.query(UserModel).filter(
        UserModel.discord_id == user["discord_id"]
    ).first()

    form = await request.form()
    new_name = form.get("display_name", "").strip()
    if new_name:
        user_obj.display_name = new_name

    # Parse dice roll preference checkboxes
    prefs = dict(user_obj.preferences or {})
    prefs["dice_animation_enabled"] = form.get("dice_animation") == "on"
    prefs["dice_sound_enabled"] = form.get("dice_sound") == "on"
    user_obj.preferences = prefs

    # Parse granted account checkboxes
    admin_ids = get_admin_ids()
    all_users = db.query(UserModel).filter(
        UserModel.discord_id != user["discord_id"]
    ).all()
    granted = []
    for u in all_users:
        # Admins always have access — don't store them in the list
        if u.discord_id in admin_ids:
            continue
        if form.get(f"grant_{u.discord_id}") == "on":
            granted.append(u.discord_id)
    user_obj.granted_account_ids = granted

    db.commit()

    return RedirectResponse("/profile", status_code=303)


# ---------------------------------------------------------------------------
# Admin: Manage Gaming Groups
# ---------------------------------------------------------------------------


def _require_admin(request: Request):
    """Return None if request is from an admin, else an HTMLResponse to return."""
    user = getattr(request.state, "user", None)
    if not user or not is_admin(user["discord_id"]):
        return HTMLResponse("Admin access required", status_code=403)
    return None


@router.get("/admin/groups", response_class=HTMLResponse)
def admin_groups(request: Request, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    groups = db.query(GamingGroup).order_by(GamingGroup.name).all()
    counts = {
        g.id: db.query(Character).filter(Character.gaming_group_id == g.id).count()
        for g in groups
    }
    return _templates().TemplateResponse(
        request=request,
        name="admin/groups.html",
        context={"groups": groups, "counts": counts},
    )


@router.post("/admin/groups/new")
async def admin_groups_create(request: Request, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return RedirectResponse("/admin/groups", status_code=303)
    existing = db.query(GamingGroup).filter(GamingGroup.name == name).first()
    if existing is None:
        db.add(GamingGroup(name=name))
        db.commit()
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/admin/groups/{group_id}/rename")
async def admin_groups_rename(request: Request, group_id: int, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    form = await request.form()
    new_name = (form.get("name") or "").strip()
    group = db.query(GamingGroup).filter(GamingGroup.id == group_id).first()
    if group and new_name:
        # Avoid duplicate-name collisions
        clash = db.query(GamingGroup).filter(
            GamingGroup.name == new_name, GamingGroup.id != group_id
        ).first()
        if clash is None:
            group.name = new_name
            db.commit()
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/admin/groups/{group_id}/delete")
async def admin_groups_delete(request: Request, group_id: int, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    group = db.query(GamingGroup).filter(GamingGroup.id == group_id).first()
    if group:
        # SQLite ON DELETE SET NULL requires PRAGMA foreign_keys=ON, which we
        # don't enable. Manually unassign characters first to be safe.
        db.query(Character).filter(
            Character.gaming_group_id == group_id
        ).update({Character.gaming_group_id: None}, synchronize_session=False)
        db.delete(group)
        db.commit()
    return RedirectResponse("/admin/groups", status_code=303)
