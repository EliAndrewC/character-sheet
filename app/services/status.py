"""Effective status computation for Honor, Rank, Recognition, and Stipend.

Advantages and disadvantages can modify these values in specific contexts.
This module computes the base values and all contextual modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.game_data import CAMPAIGN_STIPEND_RANK


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


def compute_effective_status(character_data: dict) -> EffectiveStatus:
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

    if school in ("merchant", "shosuro_actor"):
        stipend_rank += 5
        school_name = "Merchant" if school == "merchant" else "Shosuro Actor"
        status.stipend_modifiers.append({
            "source": school_name,
            "detail": "+5 stipend rank",
        })

    status.stipend = int(stipend_rank) ** 2

    # --- Advantages ---
    if "good_reputation" in advantages:
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "identification",
            "value": 1.0,
            "source": "Good Reputation",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "those familiar with your reputation",
            "value": 2.0,
            "source": "Good Reputation",
        })

    if "imperial_favor" in advantages:
        status.rank_modifiers.append({
            "field": "rank",
            "context": "Imperial family members",
            "value": 3.0,
            "source": "Imperial Favor",
        })
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "Imperial family members",
            "value": 3.0,
            "source": "Imperial Favor",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "Imperial post holders",
            "value": 1.0,
            "source": "Imperial Favor",
        })
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "Imperial post holders",
            "value": 1.0,
            "source": "Imperial Favor",
        })

    # --- Disadvantages ---
    if "bad_reputation" in disadvantages:
        status.recognition_modifiers.append({
            "field": "recognition",
            "context": "identification",
            "value": 1.0,
            "source": "Bad Reputation",
        })
        status.rank_modifiers.append({
            "field": "rank",
            "context": "those aware of your reputation",
            "value": -1.5,
            "source": "Bad Reputation",
        })

    return status
