"""
Cloud Functions entry point for Pulse.

Defines the one Callable Function the Flutter client invokes via the
`cloud_functions` package (never raw HTTP): `assess_symptoms`. This is the
only layer allowed to orchestrate a Gemini call — it runs the
deterministic red-flag check (red_flags.py) before or alongside the
Gemini call (gemini_client.py), merges the two per the truth table in
`_merge_with_red_flags`, and returns a plain-language insight + urgency
tag + next step — never a confirmed single diagnosis. The AI never gets
the final say on emergencies; this module's merge logic does.

The pipeline is factored into `run_pipeline`, a pure function with no
Firebase/Flask dependency, so it's unit-testable without the emulator
(see test_main.py). `_handle_request` does the request-shape plumbing;
`assess_symptoms` just wraps it with the `on_call` decorator.

Client-facing response has 4 possible "type" values: the 3 the model can
emit ("question", "assessment", "crisis" — see gemini_client.VALID_TYPES)
plus a 4th, "error", constructed only here for degraded mode when Gemini
itself is unavailable. The model must never emit "error" itself.

History trust (v1 limitation): `history` is client-supplied and not
verified against Firestore. A malicious client could fabricate turns
(including a fake prior "crisis" turn, or a fabricated assistant reply).
Accepted for v1; revisit once conversations are persisted server-side.

No Firestore writes this pass — the client persists messages for now;
server-side persistence lands with the episode model.
"""

from __future__ import annotations

import logging
import os
import re
import time

import firebase_admin
from firebase_functions import https_fn

import gemini_client
import red_flags
import system_prompt

# Required once per process: firebase_functions' App Check/auth token
# verification (used by the enforce_app_check=True below) reads through
# the default firebase_admin app. No Firestore/other admin SDK usage this
# pass — see the module docstring.
firebase_admin.initialize_app()

MAX_MESSAGE_LENGTH = 2000

_URGENCY_TIERS = ("monitor_at_home", "see_doctor_soon", "seek_care_now")

# Owner-approved copy (2026-07-08) for the floor-must-reach-the-user
# fallback (used both by the merge table's question->assessment override
# and by degraded mode). Every fallback below has an EN and TL variant —
# see _message_signals_tagalog for why: Gemini itself, the thing that
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


def _message_signals_tagalog(message: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(message)}
    return not _TAGALOG_MARKER_WORDS.isdisjoint(words)


def _pick_fallback_copy(message: str, *, en: str, tl: str) -> str:
    return tl if _message_signals_tagalog(message) else en

logger = logging.getLogger("pulse.assess_symptoms")


class InvalidRequestError(Exception):
    """Raised for malformed client input (missing/oversized message). The
    handler converts this to an https_fn.HttpsError; it never reaches
    run_pipeline's caller as a bare payload."""


# ---------------------------------------------------------------------------
# Small payload builders
# ---------------------------------------------------------------------------

def _static_fallback_assessment(message: str) -> dict:
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
    }


def _crisis_fallback_payload(message: str) -> dict:
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
    }


def _degraded_error_payload(message: str) -> dict:
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
    }


def _force_crisis(payload: dict) -> dict:
    return {**payload, "type": "crisis", "urgency": None}


def _select_degraded_payload(*, message: str, force_crisis: bool, floor_active: bool) -> dict:
    """Shared by every Gemini-call failure mode — schema-validation failures
    (ModelResponseError) and raw API/network failures alike. gemini_client's
    contract is that callers never see a malformed payload; this is the one
    place that promise is kept regardless of why the call failed."""
    if force_crisis:
        return _crisis_fallback_payload(message)
    if floor_active:
        return _static_fallback_assessment(message)
    return _degraded_error_payload(message)


def _max_urgency(a: str | None, b: str) -> str:
    """Higher-tier-wins, per the ordering monitor_at_home < see_doctor_soon
    < seek_care_now. `b` wins on a tie or if `a` isn't a recognized tier."""
    if a not in _URGENCY_TIERS:
        return b
    return a if _URGENCY_TIERS.index(a) >= _URGENCY_TIERS.index(b) else b


def _history_has_crisis_lock(history: list[dict]) -> bool:
    # ASSUMPTION FLAGGED FOR REVIEW: the spec's history shape is flat
    # {role, content}, but detecting "a prior assistant turn was type
    # crisis" needs a type somewhere. This assumes the client also echoes
    # a "type" key on assistant/model turns (matching the type field of
    # the payload it originally rendered) — please confirm this matches
    # the client's actual history shape.
    #
    # Client contract: assistant turns in the history payload MUST carry
    # their type field (question | assessment | crisis). Crisis-state
    # persistence depends on it until server-side history lands with the
    # episode model.
    return any(
        turn.get("role") in ("assistant", "model") and turn.get("type") == "crisis"
        for turn in history
    )


def _merge_with_red_flags(model_result: dict, message: str) -> dict:
    """Truth table for red_flags.matched (non-self-harm) + model result.
    Self-harm and crisis_lock are handled separately (they force crisis
    outright, upstream of this function) since they outrank this table."""
    model_type = model_result.get("type")
    if model_type == "crisis":
        return model_result  # crisis outranks everything — respected as-is
    if model_type == "assessment":
        return {
            **model_result,
            "urgency": _max_urgency(model_result.get("urgency"), "seek_care_now"),
        }
    # model_type == "question": OVERRIDE to assessment. Whether the
    # model's own question text "already conveys urgency" (the spec's
    # alternate branch) isn't reliably detectable from the 8-field
    # schema without NLP judgment calls, so this always uses the static
    # fallback — flagged rather than guessed at.
    return _static_fallback_assessment(message)


def _log_request(
    *, prompt_version: str, red_flag_rule_ids: list[str], final_urgency: str | None,
    latency_ms: float, retry_used: bool,
) -> None:
    # Structured fields only — never the message text, profile, or key.
    logger.info(
        "assess_symptoms request completed",
        extra={
            "prompt_version": prompt_version,
            "red_flag_rule_ids": red_flag_rule_ids,
            "final_urgency": final_urgency,
            "model_latency_ms": round(latency_ms, 1),
            "retry_used": retry_used,
        },
    )


# ---------------------------------------------------------------------------
# Pipeline (pure function — no Firebase/Flask dependency)
# ---------------------------------------------------------------------------

def run_pipeline(
    *,
    message: str | None,
    profile: dict | None = None,
    worry_level: str | None = None,
    regional_context: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    if not isinstance(message, str) or not message.strip():
        raise InvalidRequestError("Please include a message describing what's going on.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise InvalidRequestError(
            f"That message is a bit long for me to read (max {MAX_MESSAGE_LENGTH} characters)."
        )

    history = history or []
    crisis_lock = _history_has_crisis_lock(history)

    red_flag_result: red_flags.RedFlagResult | None = None
    force_crisis = crisis_lock
    red_flags_crashed = False
    if not crisis_lock:
        try:
            red_flag_result = red_flags.check_red_flags(message, profile)
        except Exception:
            # Belt-and-suspenders for an unknown-unknown: red_flags.py's own
            # helpers already fail closed on every malformed profile value
            # they know how to recognize (see _coerce_age/_coerce_condition_strings
            # there), so reaching this branch means something neither module
            # anticipated. The deterministic floor is the thing nothing else
            # catches — it must never propagate as a raw 500, and it must
            # never silently behave as "no red flag matched" either: if the
            # floor's own evaluation fails, we cannot rule out an emergency
            # pattern, so the cautious default applies at the systems level
            # the same way worst-reasonable-explanation bias applies at the
            # model level. Skip the model entirely for this turn — we have
            # no way to know whether the floor would have forced urgency
            # regardless of what it said — and go straight to the same
            # static seek_care_now fallback used when Gemini itself fails.
            logger.exception("red_flags.check_red_flags raised — treating as an unconfirmed red flag")
            red_flags_crashed = True
        else:
            if red_flag_result.matched and "self_harm_risk" in red_flag_result.rule_ids:
                force_crisis = True

    # Floor is "active" (must reach the user even if Gemini is down) when
    # an ordinary red flag matched, this turn is crisis-forced, or the
    # floor's own check crashed and we can't rule an emergency out —
    # crisis_lock skips the ordinary check above but is itself a stronger
    # floor signal, so it counts too (see the degraded-mode test for why).
    floor_active = force_crisis or bool(red_flag_result and red_flag_result.matched) or red_flags_crashed

    start = time.perf_counter()
    if red_flags_crashed:
        model_result = _select_degraded_payload(
            message=message, force_crisis=force_crisis, floor_active=True
        )
        retry_used = False
        degraded = True
    else:
        prompt = system_prompt.build_system_prompt(profile, worry_level, regional_context)
        try:
            model_result = gemini_client.get_assessment(prompt, history, message)
            retry_used = bool(model_result.pop("_retry_used", False))
            degraded = False
        except gemini_client.ModelResponseError:
            model_result = _select_degraded_payload(
                message=message, force_crisis=force_crisis, floor_active=floor_active
            )
            retry_used = True  # ModelResponseError only raises after the one retry
            degraded = True
        except Exception:
            # Anything else from the Gemini call itself — rate limit, network,
            # auth/quota failure — must degrade the same way a schema-validation
            # failure does, never bubble up as a raw framework 500. No retry was
            # attempted/completed here, unlike the ModelResponseError path.
            logger.exception("Unexpected error calling Gemini")
            model_result = _select_degraded_payload(
                message=message, force_crisis=force_crisis, floor_active=floor_active
            )
            retry_used = False
            degraded = True
    latency_ms = (time.perf_counter() - start) * 1000

    if degraded:
        final_payload = model_result
    elif force_crisis:
        final_payload = _force_crisis(model_result)
    elif red_flag_result and red_flag_result.matched:
        final_payload = _merge_with_red_flags(model_result, message)
    else:
        final_payload = model_result

    rule_ids = red_flag_result.rule_ids if red_flag_result else []
    _log_request(
        prompt_version=system_prompt.PROMPT_VERSION,
        red_flag_rule_ids=rule_ids,
        final_urgency=final_payload.get("urgency"),
        latency_ms=latency_ms,
        retry_used=retry_used,
    )

    return {
        **final_payload,
        "metadata": {
            "prompt_version": system_prompt.PROMPT_VERSION,
            "red_flag_matched": bool(red_flag_result and red_flag_result.matched) or red_flags_crashed,
            "red_flag_rule_ids": rule_ids,
            "model_name": gemini_client.MODEL_NAME,
        },
    }


# ---------------------------------------------------------------------------
# Callable Function
# ---------------------------------------------------------------------------

def _handle_request(request: https_fn.CallableRequest) -> dict:
    data = request.data or {}
    # conversation_id is accepted from the client for forward compatibility
    # but unused this pass — no Firestore writes yet (see module docstring).
    try:
        return run_pipeline(
            message=data.get("message"),
            profile=data.get("profile"),
            worry_level=data.get("worry_level"),
            regional_context=data.get("regional_context"),
            history=data.get("history"),
        )
    except InvalidRequestError as exc:
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.INVALID_ARGUMENT, str(exc)
        ) from exc


def _enforce_app_check_setting() -> bool:
    """App Check enforcement, overridable ONLY for local emulation via
    ENFORCE_APP_CHECK=false in functions/.env.local (emulator-only — the
    plain .env file DOES deploy its values to production, so the override
    must never live there). Fails safe: unset, or any value other than an
    exact case-insensitive "false", keeps enforcement ON."""
    return os.environ.get("ENFORCE_APP_CHECK", "true").strip().lower() != "false"


# region matches the Firestore instance region (asia-southeast1);
# App Check is enforced so only the Pulse app can call this function.
# NOTE: the deployed function id comes from the decorated function's
# __name__, not the variable name — so this must be a def named
# assess_symptoms (a leading-underscore name fails firebase-tools'
# function-id validation at deploy/emulator startup).
@https_fn.on_call(
    region="asia-southeast1",
    enforce_app_check=_enforce_app_check_setting(),
)
def assess_symptoms(request: https_fn.CallableRequest) -> dict:
    return _handle_request(request)
