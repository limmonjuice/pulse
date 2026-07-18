"""
Owner-approved degraded-mode/floor fallback copy and payload builders.
Moved from main.py 2026-07-14 so safety_engine.py can import them without
a circular import. Copy is owner-approved (2026-07-08) — do not edit
wording here without the owner.
"""

from __future__ import annotations

import re

# Owner-approved copy (2026-07-08) for the floor-must-reach-the-user
# fallback (used both by the merge table's question->assessment override
# and by degraded mode). Every fallback below has an EN and TL variant —
# see message_signals_tagalog for why: Gemini itself, the thing that
# normally mirrors the user's language, is exactly what's unavailable in
# this path, so a cheap heuristic on the user's own words is the only
# signal left for picking between them.
STATIC_SEEK_CARE_FALLBACK_EN = (
    "Based on what you've described, it's safer to get checked right now — "
    "let's not wait. Go to the nearest hospital or ER."
)
STATIC_SEEK_CARE_FALLBACK_TL = (
    "Base sa sinabi mo, mas ligtas na magpa-check ka na ngayon mismo — hindi na "
    "natin hihintayin pa. Pumunta na sa pinakamalapit na ospital o ER."
)

FRIENDLY_DEGRADED_ERROR_MESSAGE_EN = "Something's not working right on my end. I'm still here — try sending that again in a bit?"
FRIENDLY_DEGRADED_ERROR_MESSAGE_TL = "Hindi ko ma-process ngayon, subukan ulit."

# FLAGGED FOR MENTAL-HEALTH REVIEW (see the matching flag in
# system_prompt.py's crisis example): owner-approved copy for degraded
# mode specifically during a crisis/self-harm turn — used instead of
# the STATIC_SEEK_CARE_FALLBACK_* copy so a person in crisis isn't pointed at an ER
# when Gemini itself is unavailable.
CRISIS_DEGRADED_FALLBACK_EN = (
    "I'm still here, but I'm having trouble responding right now. The numbers "
    "below are people ready to listen to you right now. They won't leave you."
)
CRISIS_DEGRADED_FALLBACK_TL = (
    "Nandito pa rin ako, pero nagka-problema ako sa pag-sagot ngayon. Yung "
    "mga numero sa baba — mga taong handang makinig sa'yo ngayon mismo. "
    "Hindi ka nila iiwan."
)

# Function words/particles with low collision risk against English, used
# only to pick between the EN/TL fallback copy above. Optimized for
# precision over recall — default to English unless a clearly Filipino
# word is present, so a plain English message never gets an unreadable
# reply (the bug this heuristic exists to fix).
_TAGALOG_MARKER_WORDS = frozenset({
    "ako", "ikaw", "siya", "kami", "tayo", "kayo", "sila",
    "ko", "mo", "niya", "namin", "natin", "ninyo", "nila",
    "ang", "mga", "yung", "yun", "ito", "iyon", "niyan", "nito",
    "hindi", "wala", "meron", "mayroon",
    "ba", "naman", "lang", "din", "rin", "po", "opo",
    "paano", "bakit", "saan", "kailan", "sino", "kasi", "tapos",
    "kanina", "kagabi", "bukas", "kahapon",
})
_WORD_RE = re.compile(r"[A-Za-z']+")


def message_signals_tagalog(message: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(message)}
    return not _TAGALOG_MARKER_WORDS.isdisjoint(words)


def _pick_fallback_copy(message: str, *, en: str, tl: str) -> str:
    return tl if message_signals_tagalog(message) else en


def static_fallback_assessment(message: str) -> dict:
    return {
        "type": "assessment",
        "message": _pick_fallback_copy(
            message, en=STATIC_SEEK_CARE_FALLBACK_EN, tl=STATIC_SEEK_CARE_FALLBACK_TL
        ),
        "quick_replies": [],
        "urgency": "seek_care_now",
        "explanation": None,
        "watch_for": [],
        "next_step": None,
        "possibilities_mentioned": False,
        "self_care": [],
        "monitoring": [],
        "encouragement": None,
        "intents": ["reporting_new_symptom"],
        "requires_clinical_reassessment": False,
        "change_type": "none",
        "reassessment_reason": None,
        "proposed_card_action": "keep",
        "findings": [],
    }


def crisis_fallback_payload(message: str) -> dict:
    return {
        "type": "crisis",
        "message": _pick_fallback_copy(
            message, en=CRISIS_DEGRADED_FALLBACK_EN, tl=CRISIS_DEGRADED_FALLBACK_TL
        ),
        "quick_replies": [],
        "urgency": None,
        "explanation": None,
        "watch_for": [],
        "next_step": None,
        "possibilities_mentioned": False,
        "self_care": [],
        "monitoring": [],
        "encouragement": None,
        "intents": ["emotional_support"],
        "requires_clinical_reassessment": False,
        "change_type": "none",
        "reassessment_reason": None,
        "proposed_card_action": "keep",
        "findings": [],
    }


def degraded_error_payload(message: str) -> dict:
    return {
        "type": "error",
        "message": _pick_fallback_copy(
            message, en=FRIENDLY_DEGRADED_ERROR_MESSAGE_EN, tl=FRIENDLY_DEGRADED_ERROR_MESSAGE_TL
        ),
        "quick_replies": [],
        "urgency": None,
        "explanation": None,
        "watch_for": [],
        "next_step": None,
        "possibilities_mentioned": False,
        "self_care": [],
        "monitoring": [],
        "encouragement": None,
        "intents": ["off_topic"],
        "requires_clinical_reassessment": False,
        "change_type": "none",
        "reassessment_reason": None,
        "proposed_card_action": "keep",
        "findings": [],
    }


# AGENT-DRAFTED — PENDING OWNER READ-ALOUD (design spec
# 2026-07-17-visit-summary-design.md §6): NOT yet owner-approved, unlike
# every other string in this file. Used only when a visit-summary
# conversation consisted solely of a crisis exchange — nothing else to
# summarize (run_visit_summary_pipeline's degenerate case, main.py).
VISIT_SUMMARY_NO_CONTENT_EN = "No other symptoms were discussed in this conversation."
VISIT_SUMMARY_NO_CONTENT_TL = "Wala nang ibang sintomas na napag-usapan sa kausapang ito."


def visit_summary_no_content_payload(*, tagalog: bool) -> dict:
    return {
        "type": "visit_summary",
        "summary": VISIT_SUMMARY_NO_CONTENT_TL if tagalog else VISIT_SUMMARY_NO_CONTENT_EN,
        "questions_for_doctor": [],
    }
