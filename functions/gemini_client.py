"""
Gemini API client for Pulse.

The ONLY place in the entire codebase allowed to call the Gemini API —
never from the Flutter client, under any circumstance. The API key lives
only in this Cloud Function's environment config / Secret Manager, never
hardcoded or committed to git; genai.Client() picks it up from the
GEMINI_API_KEY environment variable (see functions/.env locally, Secret
Manager in production) — this module never reads or logs the key itself.

Uses the google.genai SDK (the successor to the now fully deprecated
google.generativeai package — see the migration note in requirements.txt).

This module is pure Python + the Gemini SDK: no Firebase imports, so it
is unit-testable in isolation with a mocked SDK (see test_gemini_client.py).
main.py is the only intended caller.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

from google import genai
from google.genai import types

from wire_contract import VALID_CARD_ACTIONS, VALID_CHANGE_TYPES, VALID_INTENTS

# Structured fields only — never the message text, the payload, or the key.
# This module is the ONLY place that can see why an attempt was rejected:
# the raw reply and its ValueError never leave _call_gemini_with_retry, and
# a retry that SUCCEEDS never reaches main.py's exception handlers at all.
# Before 2026-07-26 that made the single most common failure mode — a
# first-attempt schema rejection — completely invisible in production.
logger = logging.getLogger("pulse.gemini_client")

# gemini-flash-lite is the free-tier model as of this writing. This is a
# cost/quota decision, not a capability one — revisit if free-tier terms
# or model availability change. Pinned to a specific version (not the
# floating gemini-flash-lite-latest alias) so the model can't drift out
# from under the prompt/eval calibration.
MODEL_NAME = "gemini-3.1-flash-lite"

# Changing MODEL_NAME without adding an entry here fails the pytest
# suite (see test_gemini_client.py's model-changelog guard). A model
# swap silently invalidates every eval baseline in evals/results/ —
# calibration and behavior (e.g. language mirroring) are per-model, not
# per-prompt — so every swap must record the date, the reason, and
# whether the evals were actually re-run on the new model. "no" is an
# honest interim answer, never a free pass: the 2026-07-13 swap below
# shipped with evals un-rerun and the language-mirroring regression it
# hid reached the deployed function.
MODEL_CHANGELOG = [
    {
        "model": "gemini-2.5-flash-lite",
        "date": "2026-07-09",
        "reason": (
            "Original model choice: free-tier availability at MVP scale "
            "(cost/quota decision, not a capability one)."
        ),
        "evals_rerun": "yes — baselines in evals/results/ through prompt 1.5.0",
    },
    {
        "model": "gemini-3.1-flash-lite",
        "date": "2026-07-13",
        "reason": (
            "Google closed gemini-2.5-flash-lite to new API users — "
            "generateContent began returning 404 NOT_FOUND."
        ),
        "evals_rerun": (
            "no at swap time — the language_mirroring regression went out "
            "undetected; partial re-runs 2026-07-13 (language_mirroring on "
            "prompts 1.5.1 [3/5] and 1.5.2 [4/5], targeted 1.5.3 probes — "
            "one English dengue-advisory shape still mirrored wrong); "
            "prompt 1.5.4 (Taglish dengue example removed, owner decision) "
            "NOT yet live-verified — quota exhausted; full category run + "
            "re-baseline needed on next quota. UPDATE 2026-07-26: the "
            "language_mirroring category DID run on fresh quota against "
            "prompt 2.1.0 and reported 9/9, but that green was not a "
            "verification — a retry-induced turn-type change collapsed the "
            "multi-turn cases and one check scored a Pulse-constructed "
            "fallback. Still NOT live-verified; see LAUNCH_BLOCKERS.md"
        ),
    },
]

# Calibration over creativity: a low, narrow temperature keeps urgency
# tagging consistent across near-identical symptom descriptions.
GENERATION_TEMPERATURE = 0.3

REQUIRED_FIELDS = frozenset(
    {
        "type",
        "message",
        "quick_replies",
        "urgency",
        "explanation",
        "watch_for",
        "next_step",
        "possibilities_mentioned",
        "self_care",
        "monitoring",
        "encouragement",
        # v2 proposal fields (conversation engine — spec §5). The model
        # proposes; safety_engine.py disposes. Vocabulary lives in
        # wire_contract.py so prompt text and validation can't drift.
        "intents",
        "requires_clinical_reassessment",
        "change_type",
        "reassessment_reason",
        "proposed_card_action",
        "findings",
    }
)
VALID_TYPES = frozenset({"question", "assessment", "crisis", "conversation"})
# The model only ever emits these four types. main.py adds a 5th,
# locally-constructed "error" type for its own degraded-mode responses —
# that type must never come from the model itself.
VALID_URGENCIES = frozenset({"monitor_at_home", "see_doctor_soon", "seek_care_now"})

# Schema repair rides in the SYSTEM-INSTRUCTION position, never in the
# conversation. The previous design appended the malformed reply plus a
# corrective USER turn to `contents`, so the model read it as the user
# complaining about a broken response and apologised in user-facing copy
# ("I apologize for that error...", "Pasensya na kung nagkaroon ng error
# sa format" — both observed live 2026-07-26 in the language_mirroring
# sweep). The conversation the model sees on retry is now byte-identical
# to the first attempt: as far as the dialogue is concerned, nothing ever
# went wrong. Costs one prompt-cache miss on the retry only (the system
# instruction changes), which is the right trade for never leaking
# repair internals into the product voice.
_CORRECTIVE_SYSTEM_DIRECTIVE = (
    "\n\n---\n"
    "INTERNAL RETRY DIRECTIVE — SYSTEM USE ONLY.\n"
    "Your previous reply was rejected before it reached the user because "
    "it did not match the required JSON schema.\n"
    "Rejection reason: {reason}\n"
    "Answer the SAME last user message again, returning ONLY the JSON "
    "object.\n"
    "The user never saw the rejected reply and does not know anything went "
    "wrong. Do NOT apologise. Do NOT mention an error, a mistake, a format "
    "or formatting problem, JSON, or the schema anywhere in `message` or "
    "any other user-visible field. Write `message` exactly as if you were "
    "answering for the first time."
)

# Belt-and-suspenders behind the directive above: enforcement, not
# advice. Same pattern as _TIER_LANGUAGE_BLOCKLIST — a match is a
# ValueError subclass, so _call_gemini_with_retry treats it exactly like
# a schema failure and retries once. This also covers a case the
# directive cannot: a conversation whose HISTORY already contains a
# degraded-mode turn ("Something's not working right on my end"), which
# can prompt an unsolicited apology on a perfectly ordinary first
# attempt.
#
# Deliberately NOT matching bare "sorry"/"pasensya": "I'm sorry to hear
# that happened" is real shipped Pulse voice (it opened the dog-bite
# assessment in the same sweep). Every pattern here requires a
# malfunction referent, not just contrition.
_ERROR_LANGUAGE_PATTERNS = (
    # Catches the EN leak and both TL forms ("may error", "error sa
    # format", "nagkaroon ng error") in one rule.
    r"\berrors?\b",
    r"\bjson\b",
    r"\bschema\b",
    r"\bmalformed\b",
    r"\bformatting\b",
    r"\btamang format\b",
    r"\bi apologi[sz]e for\b",
    r"\bprevious (?:reply|response|message)\b",
    r"\bmy last (?:reply|response|message)\b",
    r"\bsomething went wrong\b",
    r"\bnagkaroon ng problema\b",
)

_ERROR_LANGUAGE_RE = tuple(re.compile(p, re.IGNORECASE) for p in _ERROR_LANGUAGE_PATTERNS)

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

# Maps history turn roles (as sent by the client) to Gemini's own role
# vocabulary, which only knows "user" and "model".
_ROLE_MAP = {"user": "user", "assistant": "model", "model": "model"}


class ModelResponseError(Exception):
    """Raised when the model's reply still fails schema validation after
    one corrective retry. Callers must never surface a malformed payload —
    this is the signal to fall back to degraded mode instead."""


class ErrorLanguageDetectedError(ValueError):
    """Raised when a user-visible field references an error, a formatting
    problem, or apologises for a malfunction — schema-repair internals
    leaking into the product voice. A ValueError subclass so
    _call_gemini_with_retry retries it like any other validation failure;
    if the retry leaks too, the caller's degraded-mode fallback (reviewed
    copy) is strictly better than shipping the apology."""


class TierLanguageDetectedError(ValueError):
    """Raised by _validate_visit_summary_payload when the model's own
    text states or implies an urgency tier — a ValueError subclass so
    _call_gemini_with_retry's existing retry-on-ValueError mechanism
    treats it identically to a schema failure, while callers can still
    distinguish the cause after a ModelResponseError via
    exc.__cause__ (see run_visit_summary_pipeline's structured logging
    in main.py)."""


def _reject_error_language(*fields: object) -> None:
    """Guard every user-visible text field against schema-repair leakage.
    Shared by _validate_payload and _validate_visit_summary_payload —
    both go through _call_gemini_with_retry, so both had the same leak."""
    for field in fields:
        if not isinstance(field, str):
            continue
        for pattern in _ERROR_LANGUAGE_RE:
            match = pattern.search(field)
            if match:
                raise ErrorLanguageDetectedError(
                    f"error/repair language in user-visible copy: {match.group()!r}"
                )


def _strip_markdown_fences(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def _validate_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("response is not a JSON object")

    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        raise ValueError(f"missing required fields: {sorted(missing)}")

    response_type = payload["type"]
    if response_type not in VALID_TYPES:
        raise ValueError(f"invalid type: {response_type!r}")

    urgency = payload["urgency"]
    if urgency is not None and urgency not in VALID_URGENCIES:
        raise ValueError(f"invalid urgency: {urgency!r}")

    if response_type == "assessment" and urgency is None:
        raise ValueError("assessment responses require a non-null urgency")
    if response_type == "crisis" and urgency is not None:
        raise ValueError("crisis responses require a null urgency")
    if response_type == "question":
        quick_replies = payload["quick_replies"]
        if not isinstance(quick_replies, list) or not (2 <= len(quick_replies) <= 4):
            raise ValueError("question responses require 2-4 quick_replies")
    if response_type == "conversation":
        quick_replies = payload["quick_replies"]
        if not isinstance(quick_replies, list) or len(quick_replies) > 4:
            raise ValueError("conversation responses allow at most 4 quick_replies")
        if urgency is not None:
            raise ValueError("conversation responses require a null urgency")
        if payload["explanation"] is not None:
            raise ValueError("conversation responses require a null explanation")
        if payload["next_step"] is not None:
            raise ValueError("conversation responses require a null next_step")

    self_care = payload["self_care"]
    monitoring = payload["monitoring"]
    encouragement = payload["encouragement"]
    if not isinstance(self_care, list):
        raise ValueError("self_care must be an array")
    if not isinstance(monitoring, list):
        raise ValueError("monitoring must be an array")
    if encouragement is not None and not isinstance(encouragement, str):
        raise ValueError("encouragement must be a string or null")

    if response_type in ("question", "crisis", "conversation"):
        if self_care:
            raise ValueError(f"{response_type} responses require an empty self_care")
        if monitoring:
            raise ValueError(f"{response_type} responses require an empty monitoring")
        if encouragement is not None:
            raise ValueError(f"{response_type} responses require a null encouragement")
    elif encouragement is None:  # response_type == "assessment"
        raise ValueError("assessment responses require a non-null encouragement")

    # v2 proposal fields (spec §5). reassessment_reason's conditional
    # non-null rule is NOT checked here — it needs current_urgency, which
    # this stateless validator doesn't have; safety_engine's clamp gate
    # enforces it by rejecting the de-escalation instead (never a retry).
    intents = payload["intents"]
    if (not isinstance(intents, list) or not (1 <= len(intents) <= 3)
            or not all(i in VALID_INTENTS for i in intents)):
        raise ValueError("intents must be 1-3 values from the intent vocabulary")
    if not isinstance(payload["requires_clinical_reassessment"], bool):
        raise ValueError("requires_clinical_reassessment must be a boolean")
    if payload["change_type"] not in VALID_CHANGE_TYPES:
        raise ValueError(f"invalid change_type: {payload['change_type']!r}")
    reason = payload["reassessment_reason"]
    if reason is not None and not isinstance(reason, str):
        raise ValueError("reassessment_reason must be a string or null")
    if payload["proposed_card_action"] not in VALID_CARD_ACTIONS:
        raise ValueError(
            f"invalid proposed_card_action: {payload['proposed_card_action']!r}"
        )
    findings = payload["findings"]
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings):
        raise ValueError("findings must be an array of strings")
    if response_type != "assessment" and findings:
        raise ValueError(f"{response_type} responses require empty findings")

    _reject_error_language(payload["message"])

    return payload


def _parse_json(raw_text: str) -> object:
    stripped = _strip_markdown_fences(raw_text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc


def _build_contents(history: list[dict], user_message: str) -> list[types.Content]:
    contents = [
        types.Content(
            role=_ROLE_MAP.get(turn.get("role"), "user"),
            parts=[types.Part(text=turn.get("content", ""))],
        )
        for turn in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    return contents


def _call_gemini_with_retry(
    system_prompt: str,
    contents: list[types.Content],
    validator: "Callable[[dict], dict]",
) -> dict:
    """Calls Gemini, parses+validates the response, retries once with a
    corrective suffix on failure, raises ModelResponseError if the retry
    also fails. Shared by get_assessment and get_visit_summary — the
    retry/parsing mechanism is identical; only the schema differs.

    Sets result["_retry_used"] on the returned dict — main.py's
    run_pipeline pops this for structured logging
    (test_logging_reports_retry_used_true_when_the_client_retried in
    test_main.py pins this), so it is not dropped in this extraction.
    """
    client = genai.Client()

    def _config(system_instruction: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=GENERATION_TEMPERATURE,
            response_mime_type="application/json",
        )

    def _generate(config: types.GenerateContentConfig, *, attempt: int):
        """Log-and-re-raise wrapper. Transport failures (429
        RESOURCE_EXHAUSTED / quota, 503 UNAVAILABLE, auth) are NOT
        ValueErrors, so they fly straight past the validation handling
        below and out to main.py's degraded-mode fallback. Logging them
        HERE is what keeps "you have hit your quota" readable in the logs
        instead of only surfacing as a friendly fallback message the user
        sees and the developer can't explain."""
        try:
            return client.models.generate_content(
                model=MODEL_NAME, contents=contents, config=config
            )
        except Exception as exc:
            logger.error(
                "Gemini API call failed on attempt %d: %s: %s",
                attempt, type(exc).__name__, exc,
                extra={
                    "gemini_error_type": type(exc).__name__,
                    "gemini_error_detail": str(exc),
                    "attempt": attempt,
                    "model_name": MODEL_NAME,
                },
            )
            raise

    response = _generate(_config(system_prompt), attempt=1)

    try:
        result = validator(_parse_json(response.text))
        result["_retry_used"] = False
        return result
    except ValueError as exc:
        # The specific rejection reason is far more actionable than the
        # old "not valid JSON" blanket, and unlike the raw rejected reply
        # it cannot re-prime the model with the bad copy it just wrote.
        reason = str(exc)
        # A retry that SUCCEEDS is invisible to every caller — main.py only
        # ever learns `retry_used=True`, never why. This is the only place
        # the reason exists, so it is the only place that can report it.
        logger.warning(
            "Gemini response rejected on attempt 1, retrying: %s",
            reason,
            extra={
                "rejection_reason": reason,
                "rejection_type": type(exc).__name__,
                "attempt": 1,
                "model_name": MODEL_NAME,
            },
        )

    # Same `contents` — the conversation is re-sent untouched, and only
    # the system instruction knows a retry is happening.
    retry_response = _generate(
        _config(system_prompt + _CORRECTIVE_SYSTEM_DIRECTIVE.format(reason=reason)),
        attempt=2,
    )
    try:
        result = validator(_parse_json(retry_response.text))
        result["_retry_used"] = True
        return result
    except ValueError as exc:
        logger.error(
            "Gemini response rejected twice, degrading. first=%s second=%s",
            reason, exc,
            extra={
                "rejection_reason_first": reason,
                "rejection_reason_second": str(exc),
                "rejection_type": type(exc).__name__,
                "model_name": MODEL_NAME,
            },
        )
        # Both reasons travel in the message so main.py's handler — which
        # only sees the exception — can report the whole story in one line.
        raise ModelResponseError(
            f"model response failed schema validation twice "
            f"(attempt 1: {reason}; attempt 2: {exc})"
        ) from exc


def get_assessment(system_prompt: str, history: list[dict], user_message: str) -> dict:
    """Call Gemini and return a validated 8-field assessment payload.

    Retries once with a corrective suffix if the response fails schema
    validation; raises ModelResponseError if the retry also fails. Never
    returns malformed data.
    """
    contents = _build_contents(history, user_message)
    return _call_gemini_with_retry(system_prompt, contents, _validate_payload)


REQUIRED_VISIT_SUMMARY_FIELDS = frozenset({"summary", "questions_for_doctor"})

# v1 ships EN + Taglish phrases active only (design spec §4.4). Ilocano
# entries are drafted separately and held out of this list until they've
# had the same clinician review other Ilocano copy in this project gets
# — an enforcement mechanism is the wrong place for unreviewed phrasing.
_TIER_LANGUAGE_BLOCKLIST = (
    "monitor at home",
    "see a doctor soon",
    "seek care now",
    "seek care immediately",
    "seek immediate care",
    "go to the er",
    "go to the emergency room",
    "go to the hospital immediately",
    "you should see a doctor",
    "you should seek care",
    "kailangan mo nang pumunta sa doktor",
    "pumunta ka na sa ospital",
    "puntahan mo agad ang ospital",
    "magpatingin ka na",
    "magpatingin ka na agad",
    "kumonsulta ka agad",
    "dalhin sa ospital",
)

# Word-boundary guard: plain substring matching on short phrases like
# "go to the er" would false-positive inside ordinary words ("errand",
# "era") — a wasted retry against Gemini's free-tier quota, and a hard
# failure if the retry also trips it. Requiring the phrase not be
# immediately followed by a lowercase letter stops that without touching
# the whitespace/punctuation-normalization gap (an accepted v1 tradeoff).
_TIER_LANGUAGE_BLOCKLIST_PATTERNS = tuple(
    re.compile(re.escape(phrase) + r"(?![a-z])") for phrase in _TIER_LANGUAGE_BLOCKLIST
)


def _validate_visit_summary_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("response is not a JSON object")
    missing = REQUIRED_VISIT_SUMMARY_FIELDS - payload.keys()
    if missing:
        raise ValueError(f"missing required fields: {sorted(missing)}")

    summary = payload["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be a non-empty string")

    questions = payload["questions_for_doctor"]
    if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
        raise ValueError("questions_for_doctor must be an array of strings")

    _reject_error_language(summary, *questions)

    haystack = " ".join([summary, *questions]).lower()
    for pattern in _TIER_LANGUAGE_BLOCKLIST_PATTERNS:
        match = pattern.search(haystack)
        if match:
            raise TierLanguageDetectedError(
                f"tier-recommendation language detected: {match.group()!r}"
            )

    return {"summary": summary, "questions_for_doctor": questions}


def _build_visit_summary_contents(history: list[dict]) -> list[types.Content]:
    """No trailing 'new message' — unlike _build_contents, this is a
    retrospective summary over a whole transcript, not a reply to the
    newest turn."""
    return [
        types.Content(
            role=_ROLE_MAP.get(turn.get("role"), "user"),
            parts=[types.Part(text=turn.get("content", ""))],
        )
        for turn in history
    ]


def get_visit_summary(system_prompt: str, history: list[dict]) -> dict:
    """Call Gemini for a retrospective visit-summary recap + doctor
    questions. Retries once on schema/blocklist failure via
    _call_gemini_with_retry; raises ModelResponseError if the retry also
    fails. Never returns malformed data or tier-recommendation language."""
    contents = _build_visit_summary_contents(history)
    return _call_gemini_with_retry(system_prompt, contents, _validate_visit_summary_payload)
