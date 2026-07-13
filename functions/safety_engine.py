"""
Safety Engine (spec §6): the deterministic gates between the model's
proposals and what the client renders. Pure functions — no I/O, no SDK.
Gate order matters and is load-bearing: crisis → clamp →
floor-newly-raised guard → reset gate → card matrix (the matrix's first
row consumes the reset outcome).

Scaffolding fields (EpisodeState.active_findings / last_assessment) are
deliberately never read here — see the trust-zone note in episode_state.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import fallbacks
from episode_state import EpisodeState
from wire_contract import (
    DEESCALATION_CHANGE_TYPES, RESET_INTENTS, URGENCY_TIERS,
    max_urgency, urgency_lt,
)


@dataclass
class GateResult:
    payload: dict
    card_action: str
    card_reason: str
    assessment_cleared: bool = False
    demoted: bool = False
    reset_accepted: bool = False
    deescalation_accepted: bool = False
    final_urgency: str | None = None


def _force_crisis(payload: dict) -> dict:
    return {**payload, "type": "crisis", "urgency": None}


def _demote(payload: dict) -> dict:
    return {
        **payload, "type": "conversation", "urgency": None,
        "explanation": None, "watch_for": [], "next_step": None,
        "self_care": [], "monitoring": [], "encouragement": None,
        "findings": [],
    }


def apply_gates(*, state: EpisodeState, message: str,
                current_match_rule_ids: list[str], force_crisis: bool,
                model_result: dict) -> GateResult:
    # Gate 1: crisis outranks everything (unchanged semantics).
    if force_crisis or model_result.get("type") == "crisis":
        return GateResult(
            payload=_force_crisis(model_result), card_action="keep",
            card_reason="none", final_urgency=None,
        )

    non_self_harm_now = [r for r in current_match_rule_ids if r != "self_harm_risk"]
    floor = state.min_safe_urgency
    if non_self_harm_now:
        floor = max_urgency(floor, "seek_care_now")
    new_rule_ids = [
        r for r in non_self_harm_now if r not in state.latched_rule_ids
    ]

    payload = model_result
    deescalation_accepted = False
    final_urgency = state.current_urgency

    # Gate 2: urgency clamp (assessment turns only).
    if payload.get("type") == "assessment":
        proposed = payload.get("urgency")
        final_urgency = max_urgency(proposed, floor) if floor else proposed
        current = state.current_urgency
        if (current in URGENCY_TIERS and proposed in URGENCY_TIERS
                and urgency_lt(proposed, current)):
            eligible = (
                payload.get("requires_clinical_reassessment") is True
                and payload.get("change_type") in DEESCALATION_CHANGE_TYPES
                and isinstance(payload.get("reassessment_reason"), str)
                and (floor is None or not urgency_lt(proposed, floor))
            )
            if eligible:
                deescalation_accepted = True
                final_urgency = proposed
            else:
                final_urgency = max_urgency(current, floor) if floor else current
        payload = {**payload, "urgency": final_urgency}

    # Gate 3: floor newly raised above the active card — the model's turn
    # must be an assessment at >= floor, or the owner-approved static
    # fallback replaces it (generalizes the old question->assessment row).
    if floor is not None:
        floor_above_current = (
            state.current_urgency not in URGENCY_TIERS
            or urgency_lt(state.current_urgency, floor)
        )
        turn_meets_floor = (
            payload.get("type") == "assessment"
            and payload.get("urgency") in URGENCY_TIERS
            and not urgency_lt(payload["urgency"], floor)
        )
        if floor_above_current and not turn_meets_floor:
            payload = fallbacks.static_fallback_assessment(message)
            final_urgency = payload["urgency"]

    # Gate 4: reset gate.
    reset_accepted = (
        payload.get("type") == "conversation"
        and payload.get("proposed_card_action") == "clear"
        and bool(RESET_INTENTS.intersection(payload.get("intents") or []))
        and not current_match_rule_ids
        and state.phase != "crisis"
    )

    # Gate 5: card directive matrix (first matching row wins — spec §6).
    demoted = False
    if reset_accepted:
        action, reason = "clear", "reset"
    elif payload.get("type") != "assessment":
        action, reason = "keep", "none"
    elif state.current_urgency is None:
        action, reason = "new", "first_assessment"
    elif payload["urgency"] != state.current_urgency:
        action = "update"
        reason = ("urgency_lowered"
                  if urgency_lt(payload["urgency"], state.current_urgency)
                  else "urgency_raised")
    elif new_rule_ids:
        action, reason = "update", "new_red_flag"
    elif (payload.get("requires_clinical_reassessment") is True
          and payload.get("change_type") != "none"):
        action, reason = "update", "clinical_change"
    else:
        payload = _demote(payload)
        demoted = True
        action, reason = "keep", "none"
        final_urgency = state.current_urgency

    return GateResult(
        payload=payload, card_action=action, card_reason=reason,
        assessment_cleared=reset_accepted, demoted=demoted,
        reset_accepted=reset_accepted,
        deescalation_accepted=deescalation_accepted,
        final_urgency=final_urgency if payload.get("type") == "assessment"
        else state.current_urgency if not reset_accepted else None,
    )
