"""
State Builder for the conversation engine v2 (spec §4): derives
EpisodeState from client-echoed history as a pure function — same trust
model as main.py's crisis lock, extended.

Two trust zones (see the dataclass): everything above the scaffolding
marker derives from the user's own words (red_flags re-run per user
turn) or deterministic turn-type counting — the Safety Engine may
consume it. active_findings/last_assessment originate from MODEL output
echoed through history: prompt scaffolding only, never gate input.

Fail-closed rule: if check_red_flags raises while scanning a history
turn, we cannot rule an emergency out for that turn, so the latch floor
engages ("history_scan_failed") — but unlike main.py's current-message
crash path, the model still runs; the clamp enforces the floor.

self_harm_risk is the one rule_id that, like an assistant "crisis" turn,
is scanned over the FULL history — a reset marker must not un-flag a
prior suicidal statement. Every OTHER rule_id (and history_scan_failed
itself) stays scoped to turns after the reset marker, since those
legitimately reset along with the rest of the floor bookkeeping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import red_flags
from wire_contract import URGENCY_TIERS

logger = logging.getLogger("pulse.episode_state")

HISTORY_SCAN_FAILED_RULE_ID = "history_scan_failed"


@dataclass
class EpisodeState:
    phase: str = "idle"                 # idle | assessing | guidance | crisis
    current_urgency: str | None = None
    min_safe_urgency: str | None = None
    latched_rule_ids: list[str] = field(default_factory=list)
    questions_used: int = 0
    reset_index: int = -1
    # --- prompt scaffolding only; model-proposed; NEVER gate input ---
    active_findings: list[str] = field(default_factory=list)
    last_assessment: dict | None = None


def _is_assistant(turn: object) -> bool:
    return isinstance(turn, dict) and turn.get("role") in ("assistant", "model")


def _string_list(raw: object) -> list[str]:
    if isinstance(raw, list) and all(isinstance(i, str) for i in raw):
        return raw
    return []


def _str_or_none(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def derive_episode_state(history: list | None, profile: dict | None) -> EpisodeState:
    history = history or []
    state = EpisodeState()

    # Crisis lock scans the FULL history — a reset never clears crisis
    # (spec §6 gate 1). Mirrors main._history_has_crisis_lock.
    crisis_locked = any(
        _is_assistant(t) and t.get("type") == "crisis" for t in history
    )

    for i, turn in enumerate(history):
        if _is_assistant(turn) and turn.get("assessment_cleared") is True:
            state.reset_index = i
    effective = history[state.reset_index + 1:]

    self_harm_seen_full_history = False
    for i, turn in enumerate(history):
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        pre_reset = i <= state.reset_index
        try:
            result = red_flags.check_red_flags(content, profile)
        except Exception:
            if pre_reset:
                # history_scan_failed is floor-scoped to post-reset turns
                # only — a crash on a pre-reset turn just gets logged; it
                # cannot flip self_harm_seen_full_history either way, so
                # there's nothing to fail closed about here.
                logger.exception(
                    "episode_state: red-flag scan raised on a pre-reset history "
                    "turn (self-harm check) — not latching history_scan_failed"
                )
            else:
                logger.exception(
                    "episode_state: red-flag scan raised on a history turn — latching fail-closed"
                )
                if HISTORY_SCAN_FAILED_RULE_ID not in state.latched_rule_ids:
                    state.latched_rule_ids.append(HISTORY_SCAN_FAILED_RULE_ID)
            continue
        if not result.matched:
            continue
        if pre_reset:
            if "self_harm_risk" in result.rule_ids:
                self_harm_seen_full_history = True
        else:
            for rule_id in result.rule_ids:
                if rule_id not in state.latched_rule_ids:
                    state.latched_rule_ids.append(rule_id)

    if self_harm_seen_full_history or "self_harm_risk" in state.latched_rule_ids:
        crisis_locked = True  # sticky, same rank as a crisis assistant turn

    non_self_harm = [r for r in state.latched_rule_ids if r != "self_harm_risk"]
    if non_self_harm:
        state.min_safe_urgency = "seek_care_now"

    last_assistant_type: str | None = None
    questions_since_anchor = 0
    for turn in effective:
        if not _is_assistant(turn):
            continue
        turn_type = turn.get("type")
        last_assistant_type = turn_type if isinstance(turn_type, str) else None
        if turn_type == "question":
            questions_since_anchor += 1
        elif turn_type == "assessment":
            questions_since_anchor = 0  # budget anchor: card landed (spec §8)
            urgency = turn.get("urgency")
            if urgency in URGENCY_TIERS:
                state.current_urgency = urgency
                state.active_findings = _string_list(turn.get("findings"))
                state.last_assessment = {
                    "findings": state.active_findings,
                    "explanation": _str_or_none(turn.get("explanation")),
                    "next_step": _str_or_none(turn.get("next_step")),
                    "urgency": urgency,
                }
    state.questions_used = questions_since_anchor

    if crisis_locked:
        state.phase = "crisis"
    elif state.current_urgency is not None:
        state.phase = "guidance"
    elif last_assistant_type == "question":
        state.phase = "assessing"
    else:
        state.phase = "idle"
    return state
