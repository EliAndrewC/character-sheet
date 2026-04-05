"""Effective status computation for Honor, Rank, Recognition, and Stipend.

Advantages and disadvantages can modify these values in specific contexts.
This module computes the base values and all contextual modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class EffectiveStatus:
    rank: float = 1.0
    recognition: float = 1.0
    honor: float = 1.0
    stipend: float = 1.0
    rank_modifiers: List[dict] = field(default_factory=list)
    recognition_modifiers: List[dict] = field(default_factory=list)
    honor_modifiers: List[dict] = field(default_factory=list)


def compute_effective_status(character_data: dict) -> EffectiveStatus:
    rank = character_data.get("rank", 1.0)
    recognition = character_data.get("recognition", 1.0)
    honor = character_data.get("honor", 1.0)
    advantages = character_data.get("advantages", [])
    disadvantages = character_data.get("disadvantages", [])

    status = EffectiveStatus(rank=rank, recognition=recognition, honor=honor)

    stipend_rank = rank

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

    if "wealthy" in advantages:
        stipend_rank += 3.0

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

    if "poor" in disadvantages:
        stipend_rank = stipend_rank / 2.0

    status.stipend = stipend_rank ** 2

    return status
