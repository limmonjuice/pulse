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

from google import genai
from google.genai import types

# gemini-flash-lite is the free-tier model as of this writing. This is a
# cost/quota decision, not a capability one — revisit if free-tier terms
# or model availability change.
MODEL_NAME = "gemini-2.5-flash-lite"

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
    }
)
VALID_TYPES = frozenset({"question", "assessment", "crisis"})
# The model only ever emits these three types. main.py adds a 4th,
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

    self_care = payload["self_care"]
    monitoring = payload["monitoring"]
    encouragement = payload["encouragement"]
    if not isinstance(self_care, list):
        raise ValueError("self_care must be an array")
    if not isinstance(monitoring, list):
        raise ValueError("monitoring must be an array")
    if encouragement is not None and not isinstance(encouragement, str):
        raise ValueError("encouragement must be a string or null")

    if response_type in ("question", "crisis"):
        if self_care:
            raise ValueError(f"{response_type} responses require an empty self_care")
        if monitoring:
            raise ValueError(f"{response_type} responses require an empty monitoring")
        if encouragement is not None:
            raise ValueError(f"{response_type} responses require a null encouragement")
    elif encouragement is None:  # response_type == "assessment"
        raise ValueError("assessment responses require a non-null encouragement")

    return payload


def _parse_and_validate(raw_text: str) -> dict:
    stripped = _strip_markdown_fences(raw_text)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return _validate_payload(payload)


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


def get_assessment(system_prompt: str, history: list[dict], user_message: str) -> dict:
    """Call Gemini and return a validated 8-field assessment payload.

    Retries once with a corrective suffix if the response fails schema
    validation; raises ModelResponseError if the retry also fails. Never
    returns malformed data.
    """
    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=GENERATION_TEMPERATURE,
        response_mime_type="application/json",
    )

    contents = _build_contents(history, user_message)
    response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=config)

    try:
        result = _parse_and_validate(response.text)
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
        result = _parse_and_validate(retry_response.text)
        result["_retry_used"] = True
        return result
    except ValueError as exc:
        raise ModelResponseError(
            "model response failed schema validation twice"
        ) from exc
