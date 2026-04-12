"""Effective status computation for Honor, Rank, Recognition, and Stipend.

Advantages and disadvantages can modify these values in specific contexts.
This module computes the base values and all contextual modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.game_data import CAMPAIGN_STIPEND_RANK, GROUP_EFFECTS
from app.services.rolls import compute_dan


@dataclass
class EffectiveStatus:
    rank: float = 1.0
    recognition: float = 1.0
    honor: float = 1.0
    stipend: int = 0
    rank_modifiers: List[dict] = field(default_factory=list)
    recognition_modifiers: List[dict] = field(default_factory=list)
    honor_modifiers: List[dict] = field(default_factory=list)
    stipend_modifiers: List[dict] = field(default_factory=list)


def compute_effective_status(
    character_data: dict,
    party_members: Optional[List[dict]] = None,
) -> EffectiveStatus:
    """Compute effective status for one character.

    ``party_members`` is an optional list of OTHER characters in the same
    gaming group. Each element is a dict with keys ``name``, ``advantages``,
    ``disadvantages``, ``campaign_advantages``, ``campaign_disadvantages``.
    Group-wide effects from those party members add Rank modifiers to this
    character's status (alongside the character's own modifiers).
    """
    rank = character_data.get("rank", 1.0)
    recognition = character_data.get("recognition", 1.0)
    honor = character_data.get("honor", 1.0)
    advantages = character_data.get("advantages", [])
    disadvantages = character_data.get("disadvantages", [])
    campaign_advantages = character_data.get("campaign_advantages", [])
    school = character_data.get("school", "")

    status = EffectiveStatus(rank=rank, recognition=recognition, honor=honor)

    # --- Stipend calculation (Wasp campaign rules) ---
    stipend_rank = CAMPAIGN_STIPEND_RANK
    status.stipend_modifiers.append({
        "source": "Wasp campaign base",
        "detail": f"considered {CAMPAIGN_STIPEND_RANK}th rank",
    })

    if "household_wealth" in campaign_advantages:
        stipend_rank = 10
        status.stipend_modifiers.append({
            "source": "Household Wealth",
            "detail": "base stipend rank 10",
        })

    knacks = character_data.get("knacks", {}) or {}
    dan = compute_dan(knacks) if knacks else 0
    if school in ("merchant", "shosuro_actor") and dan >= 4:
        stipend_rank += 5
        school_name = "Merchant" if school == "merchant" else "Shosuro Actor"
        status.stipend_modifiers.append({
            "source": f"{school_name} (4th Dan)",
            "detail": "+5 stipend rank",
        })

    status.stipend = int(stipend_rank) ** 2

    # --- GM-awarded reputations (from rank_recognition_awards) ---
    awards = character_data.get("rank_recognition_awards") or []
    for award in awards:
        award_type = award.get("type", "rank_recognition")
        source_text = award.get("source") or "unknown"
        if award_type == "good_reputation":
            status.recognition_modifiers.append({
                "field": "recognition",
                "context": "for identification",
                "value": 1.0,
                "source": f"Good Reputation ({source_text})",
            })
            status.rank_modifiers.append({
                "field": "rank",
                "context": "with those familiar with your reputation",
                "value": 2.0,
                "source": f"Good Reputation ({source_text})",
            })
        elif award_type == "bad_reputation":
            status.recognition_modifiers.append({
                "field": "recognition",
                "context": "for identification",
                "value": 1.0,
                "source": f"Bad Reputation ({source_text})",
            })
            status.rank_modifiers.append({
                "field": "rank",
                "context": "with those aware of your reputation",
                "value": -1.5,
                "source": f"Bad Reputation ({source_text})",
            })

    # --- Advantages ---
    if "good_reputation" in advantages:
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "for identification",
            "value": 1.0,
            "source": "Good Reputation",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "with those familiar with your reputation",
            "value": 2.0,
            "source": "Good Reputation",
        })

    if "imperial_favor" in advantages:
        status.rank_modifiers.append({
            "field": "rank",
            "context": "with Imperial family members",
            "value": 3.0,
            "source": "Imperial Favor",
        })
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "with Imperial family members",
            "value": 3.0,
            "source": "Imperial Favor",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "with Imperial post holders",
            "value": 1.0,
            "source": "Imperial Favor",
        })
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "with Imperial post holders",
            "value": 1.0,
            "source": "Imperial Favor",
        })

    # --- Disadvantages ---
    if "bad_reputation" in disadvantages:
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "for identification",
            "value": 1.0,
            "source": "Bad Reputation",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "with those aware of your reputation",
            "value": -1.5,
            "source": "Bad Reputation",
        })

    # --- Party-wide Rank modifiers (self + other members in the group) ---
    # These effects apply to the ENTIRE party, including the character who
    # has the advantage/disadvantage. We check the character's own IDs first,
    # then loop over other party members.
    self_name = character_data.get("name", "you")
    all_self_ids = advantages + disadvantages + campaign_advantages + (
        character_data.get("campaign_disadvantages") or []
    )
    for effect_id in all_self_ids:
        effect = GROUP_EFFECTS.get(effect_id)
        if not effect or "rank_modifier" not in effect:
            continue
        delta, context_template = effect["rank_modifier"]
        status.rank_modifiers.append({
            "field": "rank",
            "context": context_template.format(name=self_name),
            "value": delta,
            "source": effect["name"],
        })

    if party_members:
        for member in party_members:
            member_ids = (
                (member.get("advantages") or [])
                + (member.get("disadvantages") or [])
                + (member.get("campaign_advantages") or [])
                + (member.get("campaign_disadvantages") or [])
            )
            for effect_id in member_ids:
                effect = GROUP_EFFECTS.get(effect_id)
                if not effect or "rank_modifier" not in effect:
                    continue
                delta, context_template = effect["rank_modifier"]
                member_name = member.get("name", "a party member")
                status.rank_modifiers.append({
                    "field": "rank",
                    "context": context_template.format(name=member_name),
                    "value": delta,
                    "source": f"{member_name}'s {effect['name']}",
                })

    return status
