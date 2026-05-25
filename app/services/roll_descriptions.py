"""Server-side resolver: roll_key -> {title, body} explainer.

Each row on the Roll History page (and the readonly modal) shows the
underlying mechanic's name + canonical rules text as a tooltip. The
lookup is a pure function of ``roll_key``; the page renders the
resolved dicts inline so the client doesn't need a JS lookup table.
"""

from __future__ import annotations

from typing import Dict, Optional

from app.game_data import RING_NAMES, SCHOOL_KNACKS, SCHOOLS, SKILLS


_RING_NAMES = set(RING_NAMES)


_HARDCODED: Dict[str, Dict[str, str]] = {
    "attack": {
        "title": "Attack",
        "body": (
            "Roll Attack + Fire to hit. TN to hit = 5 + 5 * defender's "
            "Parry skill. Extra damage die for every 5 points exceeding the TN."
        ),
    },
    "parry": {
        "title": "Parry",
        "body": (
            "Roll Parry + Air to deflect an attack. TN = attacker's roll "
            "result. Your TN to be hit = 5 + 5 * Parry. Declaring parry "
            "before the attack roll grants a free raise."
        ),
    },
    "wound_check": {
        "title": "Wound Check",
        "body": (
            "When you take light wounds, roll Earth (with bonuses) keeping "
            "Earth. TN = current light wounds. Failure margin determines "
            "the number of serious wounds taken."
        ),
    },
    "initiative": {
        "title": "Initiative",
        "body": (
            "At the start of each combat round, roll Reflexes + Insight to "
            "produce action dice. Each die's face value is the phase on "
            "which you may take an action."
        ),
    },
    "initiative:athletics": {
        "title": "Initiative (Athletics)",
        "body": (
            "Togashi Ise Zumi special ability: include an additional "
            "athletics-only action die in your initiative roll. The bonus "
            "die may only be spent on athletics actions."
        ),
    },
    "bless": {
        "title": "Bless (Priest ritual)",
        "body": (
            "A Priest ritual. Roll 2k1 and add the result to a target's "
            "next applicable roll. The exact effect depends on which "
            "Bless ritual was invoked (Research, Conversation, etc.)."
        ),
    },
    "freeform": {
        "title": "Freeform Roll",
        "body": (
            "A manually-specified XkY roll outside of any standard skill "
            "or combat formula. Used for ad-hoc rolls the GM calls for."
        ),
    },
    "spend_vp_xk1": {
        "title": "Spent Void Point (Xk1)",
        "body": (
            "Some abilities (e.g. Isawa Ishi 3rd Dan) let you spend a "
            "void point to roll Xk1 and add the result to another "
            "character's roll. X varies by the source ability."
        ),
    },
    "iaijutsu:contested": {
        "title": "Iaijutsu Contested Roll",
        "body": (
            "Opening contested roll of an iaijutsu duel: both duellists "
            "roll iaijutsu + insight. The higher result determines who "
            "strikes first and sets the TN for the strike roll."
        ),
    },
    "iaijutsu:strike": {
        "title": "Iaijutsu Strike",
        "body": (
            "Iaijutsu strike: the winner of the contested roll rolls "
            "iaijutsu + Fire keeping Fire. TN = the loser's contested "
            "roll. Hitting damages; failing gives the opponent a free "
            "raise on their attack."
        ),
    },
    "iaijutsu:damage": {
        "title": "Iaijutsu Damage",
        "body": (
            "Damage roll from a successful iaijutsu strike. Damage dice "
            "are the weapon's base damage plus any free raises for "
            "excess attack-roll margin."
        ),
    },
    "kakita_5th_dan": {
        "title": "Kakita 5th Dan technique",
        "body": (
            "Kakita Bushi 5th Dan: once per combat round you may make a "
            "contested iaijutsu roll against a target who is about to "
            "attack you. On success you strike first; on failure they "
            "still get to make their attack at +5 per raise of margin."
        ),
    },
}


def label_for_roll(
    roll_key: Optional[str], payload: Optional[Dict] = None
) -> str:
    """Return the short display label for a roll (the "Type of Roll" column).

    The label is NOT stored on the row; it is the title captured in the roll's
    payload at roll time (``payload['title']``), which every roller records and
    which used to be duplicated into the dropped ``roll_label`` column. For the
    rare/defensive case of a payload with no title, fall back to the explainer
    title for the key, then the raw key, then a generic "Roll".
    """
    title = (payload or {}).get("title")
    if title:
        return str(title)
    if roll_key:
        # describe_roll's title is a reasonable last-resort label (it carries
        # decorations like "(skill)", but this path only fires for a malformed
        # payload, which no real roller produces).
        return describe_roll(roll_key).get("title") or roll_key
    return "Roll"


def describe_roll(roll_key: Optional[str]) -> Dict[str, str]:
    """Return ``{'title': str, 'body': str}`` for a roll_key.

    Falls back to ``{'title': roll_key or 'Roll', 'body': ''}`` for any
    key the resolver doesn't recognise. The UI handles an empty body
    gracefully (renders the title only).
    """
    if not roll_key:
        return {"title": "Roll", "body": ""}

    if roll_key in _HARDCODED:
        return dict(_HARDCODED[roll_key])

    # ``<attack-key>:damage`` is the follow-on damage roll for any attack
    # (regular attack, iaijutsu strike, etc.). Resolve the parent attack
    # for the title prefix; the body is the canonical damage explainer.
    if roll_key.endswith(":damage"):
        parent_key = roll_key[: -len(":damage")]
        parent = describe_roll(parent_key)
        return {
            "title": f"Damage ({parent['title']})",
            "body": (
                "Damage roll from a successful hit. Damage dice are the "
                "weapon's base damage plus extra dice for each full 5 "
                "points of attack-roll margin past the TN."
            ),
        }

    if roll_key.startswith("skill:"):
        sid = roll_key.split(":", 1)[1]
        skill = SKILLS.get(sid)
        if skill is not None:
            return {
                "title": f"{skill.name} (skill)",
                "body": skill.rules_text or skill.description or "",
            }
        return {"title": sid, "body": ""}

    if roll_key.startswith("knack:"):
        # Variants like "knack:iaijutsu:strike" - strip the suffix for
        # the SCHOOL_KNACKS lookup but keep it in the title.
        rest = roll_key.split(":", 1)[1]
        parts = rest.split(":")
        kid = parts[0]
        variant = parts[1] if len(parts) > 1 else None
        knack = SCHOOL_KNACKS.get(kid)
        if knack is not None:
            title = f"{knack.name} (knack)"
            if variant:
                title += f" - {variant}"
            return {
                "title": title,
                "body": knack.rules_text or knack.description or "",
            }
        return {"title": rest, "body": ""}

    if roll_key.startswith("ring:"):
        ring = roll_key.split(":", 1)[1]
        if ring in _RING_NAMES:
            return {
                "title": f"{ring} ring roll",
                "body": (
                    f"A raw {ring} ring roll - the rolled and kept dice "
                    f"both default to the character's {ring} value."
                ),
            }
        return {"title": roll_key, "body": ""}

    if roll_key.startswith("athletics:"):
        ring = roll_key.split(":", 1)[1]
        return {
            "title": f"Athletics ({ring})",
            "body": (
                f"An athletics action keyed off the {ring} ring. Used "
                "for movement, jumping, climbing, and dodging."
            ),
        }

    if roll_key.startswith("spend_vp_xk1:"):
        # "spend_vp_xk1:<school_id>" - the Ide Diplomat / Isawa Ishi style 3rd
        # Dan "spend a VP to add/subtract Xk1 from a roll" technique. Show that
        # school's actual 3rd Dan rules text; fall back to the generic blurb if
        # the school is unknown or has no 3rd Dan text recorded. (A bare
        # "spend_vp_xk1" key from before this was school-aware is handled by the
        # _HARDCODED lookup above.)
        school_id = roll_key.split(":", 1)[1]
        school = SCHOOLS.get(school_id)
        if school is not None and 3 in school.techniques:
            return {
                "title": f"{school.name} 3rd Dan technique",
                "body": school.techniques[3] or "",
            }
        return dict(_HARDCODED["spend_vp_xk1"])

    if roll_key.startswith("school:"):
        # Format: "school:<school_id>:<dan>" or "school:<school_id>:special"
        parts = roll_key.split(":")
        if len(parts) >= 3:
            school_id = parts[1]
            dan_or_kind = parts[2]
            school = SCHOOLS.get(school_id)
            if school is not None:
                if dan_or_kind == "special":
                    return {
                        "title": f"{school.name} special ability",
                        "body": school.special_ability or "",
                    }
                try:
                    dan = int(dan_or_kind.rstrip("dthrnst"))
                except ValueError:
                    dan = None
                if dan and dan in school.techniques:
                    return {
                        "title": f"{school.name} {dan}{_ord(dan)} Dan technique",
                        "body": school.techniques[dan] or "",
                    }
        return {"title": roll_key, "body": ""}

    return {"title": roll_key, "body": ""}


def _ord(n: int) -> str:
    return {1: "st", 2: "nd", 3: "rd"}.get(n, "th")
