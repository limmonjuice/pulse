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
import re
from typing import Callable

from google import genai
from google.genai import types

from wire_contract import VALID_CARD_ACTIONS, VALID_CHANGE_TYPES, VALID_INTENTS

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
            "re-baseline needed on next quota"
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

_CORRECTIVE_SUFFIX = (
    "Your previous reply was not valid JSON matching the schema. "
    "Return ONLY the JSON object."
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

# Maps history turn roles (as sent by the client) to Gemini's own role
# vocabulary, which only knows "user" and "model".
_ROLE_MAP = {"user": "user", "assistant": "model", "model": "model"}


class ModelResponseError(Exception):
    """Raised when the model's reply still fails schema validation after
    one corrective retry. Callers must never surface a malformed payload —
    this is the signal to fall back to degraded mode instead."""


class TierLanguageDetectedError(ValueError):
    """Raised by _validate_visit_summary_payload when the model's own
    text states or implies an urgency tier — a ValueError subclass so
    _call_gemini_with_retry's existing retry-on-ValueError mechanism
    treats it identically to a schema failure, while callers can still
    distinguish the cause after a ModelResponseError via
    exc.__cause__ (see run_visit_summary_pipeline's structured logging
    in main.py)."""


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
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=GENERATION_TEMPERATURE,
        response_mime_type="application/json",
    )

    response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=config)

    try:
        result = validator(_parse_json(response.text))
        result["_retry_used"] = False
        return result
    except ValueError:
        pass  # fall through to the one allowed retry

    retry_contents = contents + [
        types.Content(role="model", parts=[types.Part(text=response.text)]),
        types.Content(role="user", parts=[types.Part(text=_CORRECTIVE_SUFFIX)]),
    ]
    retry_response = client.models.generate_content(
        model=MODEL_NAME, contents=retry_contents, config=config
    )
    try:
        result = validator(_parse_json(retry_response.text))
        result["_retry_used"] = True
        return result
    except ValueError as exc:
        raise ModelResponseError(
            "model response failed schema validation twice"
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

    haystack = " ".join([summary, *questions]).lower()
    for phrase in _TIER_LANGUAGE_BLOCKLIST:
        if phrase in haystack:
            raise TierLanguageDetectedError(
                f"tier-recommendation language detected: {phrase!r}"
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
