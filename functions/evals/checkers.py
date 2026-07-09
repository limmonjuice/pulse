"""
Pure check functions for the Pulse eval harness (see README.md).

Every checker takes (response, expected) and returns (passed: bool,
detail: str) — EXCEPT check_possibilities_mentioned, which returns a
bare bool by design (see its docstring): run_evals.py uses it two ways,
as a per-case assertion (compared against an expected bool) and as a
tally across the possibilities_frequency category.

check_no_banned_words and check_no_diagnosis_assertion are regex
heuristics, not authoritative judgments of copy quality. A clean pass
only means "no listed word/pattern matched" — it is not proof the reply
is good Taglish. A match should be read by a human, not treated as a
definitive failure. See voice_compliance cases in cases.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FUNCTIONS_DIR = Path(__file__).resolve().parent.parent
if str(_FUNCTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_FUNCTIONS_DIR))

import gemini_client  # noqa: E402
import mirror_probes  # noqa: E402

# Formal Tagalog register words the system prompt (IDENTITY section)
# explicitly names as forbidden in favor of everyday equivalents —
# "eksaminasyon"/"kondisyon"/"ibukod" are the prompt's own examples;
# "maibubukod" is the common conjugated form of "ibukod" a reply is
# just as likely to produce.
BANNED_WORDS = ["eksaminasyon", "kondisyon", "ibukod", "maibubukod"]

# Best-effort diagnosis-assertion patterns (hard rule 1: never "you have
# X"). Not exhaustive — a model can assert a diagnosis in phrasing these
# patterns don't cover.
DIAGNOSIS_ASSERTION_PATTERNS = [
    r"\byou have [a-z]+\b",
    r"\bikaw ay may\b",
]

_ALL_RESPONSE_TYPES = gemini_client.VALID_TYPES | {"error"}


def check_tier(response: dict, expected: str) -> tuple[bool, str]:
    """expected: one of gemini_client.VALID_URGENCIES. Only passes for a
    response of type "assessment" carrying that exact urgency — a
    question/crisis response always fails this check, since the case
    calling it expects a resolved tier."""
    actual_type = response.get("type")
    actual_urgency = response.get("urgency")
    if actual_type != "assessment":
        return False, f"expected an assessment with urgency={expected!r}, got type={actual_type!r}"
    passed = actual_urgency == expected
    return passed, f"urgency={actual_urgency!r} (expected {expected!r})"


def check_type(response: dict, expected: str) -> tuple[bool, str]:
    actual = response.get("type")
    return actual == expected, f"type={actual!r} (expected {expected!r})"


def check_language(response: dict, expected: str | tuple[str, ...]) -> tuple[bool, str]:
    """Wraps mirror_probes.detect_language — see that module for the
    function-word-counting heuristic. `expected` may be a single language
    string or a tuple of acceptable languages (e.g. Taglish cases that
    should read as "tagalog" or "mixed")."""
    message = response.get("message", "")
    detected = mirror_probes.detect_language(message)
    allowed = (expected,) if isinstance(expected, str) else tuple(expected)
    passed = detected in allowed
    return passed, f"detected={detected!r} (expected one of {allowed})"


def check_schema_shape(response: dict, expected=None) -> tuple[bool, str]:
    """Validates all 11 model-schema fields are present and follow the
    null/[] shape rules for whatever `type` the response actually is
    (question/assessment/crisis/error) — mirrors gemini_client's own
    _validate_payload, plus main.py's locally-constructed "error" type,
    which always uses the same safe empty shape as crisis/question."""
    missing = gemini_client.REQUIRED_FIELDS - response.keys()
    if missing:
        return False, f"missing fields: {sorted(missing)}"

    response_type = response.get("type")
    if response_type not in _ALL_RESPONSE_TYPES:
        return False, f"unexpected type: {response_type!r}"

    urgency = response.get("urgency")
    quick_replies = response.get("quick_replies")
    self_care = response.get("self_care")
    monitoring = response.get("monitoring")
    watch_for = response.get("watch_for")
    encouragement = response.get("encouragement")

    problems = []
    for name, value in (
        ("quick_replies", quick_replies),
        ("self_care", self_care),
        ("monitoring", monitoring),
        ("watch_for", watch_for),
    ):
        if not isinstance(value, list):
            problems.append(f"{name} is not a list")

    info = []
    if response_type == "assessment":
        if urgency not in gemini_client.VALID_URGENCIES:
            problems.append(f"assessment urgency invalid: {urgency!r}")
        if encouragement is None:
            # Not a shape violation: gemini_client._validate_payload already
            # rejects a live model assessment with null encouragement before
            # it ever reaches this response, so null here can only mean this
            # went through main.py's degraded-mode fallback (see
            # test_fallback_payloads_carry_new_fields_at_safe_values) — an
            # intentional, tested shape, not a bug in the pipeline.
            info.append("encouragement is null — indicates a degraded-mode fallback assessment, not a live model response")
    elif response_type == "question":
        if urgency is not None:
            problems.append("question urgency should be null")
        if not (isinstance(quick_replies, list) and 2 <= len(quick_replies) <= 4):
            problems.append("question requires 2-4 quick_replies")
        if self_care:
            problems.append("question self_care should be empty")
        if monitoring:
            problems.append("question monitoring should be empty")
        if encouragement is not None:
            problems.append("question encouragement should be null")
    else:  # crisis or error — both use the same safe empty shape
        if urgency is not None:
            problems.append(f"{response_type} urgency should be null")
        if quick_replies:
            problems.append(f"{response_type} quick_replies should be empty")
        if self_care:
            problems.append(f"{response_type} self_care should be empty")
        if monitoring:
            problems.append(f"{response_type} monitoring should be empty")
        if encouragement is not None:
            problems.append(f"{response_type} encouragement should be null")

    if problems:
        return False, "; ".join(problems)
    detail = f"shape OK for type={response_type}"
    if info:
        detail += " (" + "; ".join(info) + ")"
    return True, detail


def check_no_banned_words(response: dict, expected=None) -> tuple[bool, str]:
    message = response.get("message", "")
    hits = [w for w in BANNED_WORDS if re.search(rf"\b{re.escape(w)}\b", message, re.IGNORECASE)]
    passed = not hits
    detail = "no banned words found" if passed else f"found banned word(s): {hits} — heuristic, read the reply"
    return passed, detail


def check_no_diagnosis_assertion(response: dict, expected=None) -> tuple[bool, str]:
    message = response.get("message", "")
    hits = [p for p in DIAGNOSIS_ASSERTION_PATTERNS if re.search(p, message, re.IGNORECASE)]
    passed = not hits
    detail = (
        "no diagnosis-assertion pattern matched (heuristic only)"
        if passed
        else f"possible diagnosis-assertion pattern(s) matched: {hits} — heuristic, flag for human review"
    )
    return passed, detail


def check_possibilities_mentioned(response: dict, expected=None) -> bool:
    """Returns the bool, not a pass/fail. The possibilities_frequency
    category tallies this across cases rather than asserting per-case;
    other categories (e.g. the dengue case in tier_calibration) can
    still use it as an assertion — run_evals.py's generic check
    dispatcher treats a bare bool return as "passed if it equals
    `expected`"."""
    return bool(response.get("possibilities_mentioned", False))


def check_crisis_persists(response: dict, expected=None) -> tuple[bool, str]:
    passed = response.get("type") == "crisis" and response.get("urgency") is None
    return passed, f"type={response.get('type')!r}, urgency={response.get('urgency')!r}"


CHECKERS = {
    "check_tier": check_tier,
    "check_type": check_type,
    "check_language": check_language,
    "check_schema_shape": check_schema_shape,
    "check_no_banned_words": check_no_banned_words,
    "check_no_diagnosis_assertion": check_no_diagnosis_assertion,
    "check_possibilities_mentioned": check_possibilities_mentioned,
    "check_crisis_persists": check_crisis_persists,
}
