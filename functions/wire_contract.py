"""
Shared vocabulary for the conversation engine v2 wire contract
(spec: docs/superpowers/specs/2026-07-13-conversation-engine-design.md §5).

Stdlib-only ON PURPOSE: system_prompt.py (pure by charter) and
gemini_client.py both import this, so the intent/change-type vocabulary
has exactly one home — prompt text and schema validation can never
drift apart.
"""

from __future__ import annotations

URGENCY_TIERS = ("monitor_at_home", "see_doctor_soon", "seek_care_now")


def max_urgency(a: str | None, b: str) -> str:
    """Higher-tier-wins; `b` wins on a tie or when `a` isn't a tier.
    (Moved from main.py's _max_urgency — same semantics.)"""
    if a not in URGENCY_TIERS:
        return b
    return a if URGENCY_TIERS.index(a) >= URGENCY_TIERS.index(b) else b


def urgency_lt(a: str, b: str) -> bool:
    """True when `a` is a strictly lower tier than `b` (both must be tiers)."""
    return URGENCY_TIERS.index(a) < URGENCY_TIERS.index(b)


# Spec §7 vocabulary, grouped for readability only — the model sees the
# same grouping in the prompt, the validator sees the flat set.
VALID_INTENTS = frozenset({
    # medical assessment
    "reporting_new_symptom", "reporting_worsening", "reporting_improvement",
    "answering_question", "medication_question", "exposure_history",
    # medical conversation
    "asking_why", "reassurance_seeking", "emotional_support",
    "asking_next_steps", "asking_about_recommendation",
    "asking_about_causes", "clarification",
    # general conversation
    "greeting", "thanking", "joke", "testing_system", "correction",
    "casual_chat", "off_topic",
    # administrative
    "start_new_assessment", "change_language", "feedback",
})

VALID_CHANGE_TYPES = frozenset({
    "new_symptom", "resolved_symptom", "worsening",
    "new_history", "treatment_update", "none",
})

VALID_CARD_ACTIONS = frozenset({"new", "update", "keep", "clear"})

# The intents that may open the reset gate (spec §6 gate 4).
RESET_INTENTS = frozenset({"testing_system", "correction", "start_new_assessment"})

# The one change type eligible to lower urgency (spec §12 decision 10).
DEESCALATION_CHANGE_TYPES = frozenset({"resolved_symptom"})
