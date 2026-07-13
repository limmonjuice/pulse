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
import time

import firebase_admin
from firebase_functions import https_fn

import fallbacks
import gemini_client
import mirror_probes
import red_flags
import system_prompt
import wire_contract

# Required once per process: firebase_functions' App Check/auth token
# verification (used by the enforce_app_check=True below) reads through
# the default firebase_admin app. No Firestore/other admin SDK usage this
# pass — see the module docstring.
firebase_admin.initialize_app()

MAX_MESSAGE_LENGTH = 2000

# Re-exported for test compatibility — the copy itself lives in
# fallbacks.py now (see that module's docstring for why).
STATIC_SEEK_CARE_FALLBACK_EN = fallbacks.STATIC_SEEK_CARE_FALLBACK_EN
STATIC_SEEK_CARE_FALLBACK_TL = fallbacks.STATIC_SEEK_CARE_FALLBACK_TL
FRIENDLY_DEGRADED_ERROR_MESSAGE_EN = fallbacks.FRIENDLY_DEGRADED_ERROR_MESSAGE_EN
FRIENDLY_DEGRADED_ERROR_MESSAGE_TL = fallbacks.FRIENDLY_DEGRADED_ERROR_MESSAGE_TL
CRISIS_DEGRADED_FALLBACK_EN = fallbacks.CRISIS_DEGRADED_FALLBACK_EN
CRISIS_DEGRADED_FALLBACK_TL = fallbacks.CRISIS_DEGRADED_FALLBACK_TL


# A user turn must be at least this many words before it can CHANGE the
# conversation's language. Tapped quick-reply chips are the model's own
# words echoed back (3-4 words), so they can never flip it; a person
# genuinely switching writes a full sentence.
_LANGUAGE_SWITCH_MIN_WORDS = 5


def _conversation_language(message: str, history: list[dict]) -> str | None:
    """Derive the conversation's language from the person's own turns,
    for system_prompt's CONVERSATION LANGUAGE directive (1.5.5).

    The model can't be trusted with this on low-signal turns: live probes
    (2026-07-13) showed a tapped chip like "Stomach pain or nausea" reads
    as code-switched Taglish register to 3.1-flash-lite and flips an
    all-English conversation to Tagalog, and no prompt-side counterweight
    (rule or few-shot example) beat that prior — only a server-stated
    directive did. So the server decides, deterministically: newest user
    turn first, the first turn that is both confidently classified by
    mirror_probes.detect_language AND long enough to be a real switch
    (>= _LANGUAGE_SWITCH_MIN_WORDS words) wins. If no turn passes that
    bar, the newest confidently classified turn of any length wins (a
    terse first message still deserves its own language). None when
    nothing classifies — the prompt's own rules then stand alone.
    """
    texts = [
        turn.get("content")
        for turn in history
        if isinstance(turn, dict) and turn.get("role") == "user"
    ]
    texts.append(message)
    newest_confident: str | None = None
    for text in reversed(texts):
        if not isinstance(text, str):
            continue
        detected = mirror_probes.detect_language(text)
        if detected == "unknown":
            continue
        if newest_confident is None:
            newest_confident = detected
        if len(text.split()) >= _LANGUAGE_SWITCH_MIN_WORDS:
            return detected
    return newest_confident

logger = logging.getLogger("pulse.assess_symptoms")


class InvalidRequestError(Exception):
    """Raised for malformed client input (missing/oversized message). The
    handler converts this to an https_fn.HttpsError; it never reaches
    run_pipeline's caller as a bare payload."""


# ---------------------------------------------------------------------------
# Small payload builders
# ---------------------------------------------------------------------------

def _force_crisis(payload: dict) -> dict:
    return {**payload, "type": "crisis", "urgency": None}


def _select_degraded_payload(*, message: str, force_crisis: bool, floor_active: bool) -> dict:
    """Shared by every Gemini-call failure mode — schema-validation failures
    (ModelResponseError) and raw API/network failures alike. gemini_client's
    contract is that callers never see a malformed payload; this is the one
    place that promise is kept regardless of why the call failed."""
    if force_crisis:
        return fallbacks.crisis_fallback_payload(message)
    if floor_active:
        return fallbacks.static_fallback_assessment(message)
    return fallbacks.degraded_error_payload(message)


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
            "urgency": wire_contract.max_urgency(model_result.get("urgency"), "seek_care_now"),
        }
    # model_type == "question": OVERRIDE to assessment. Whether the
    # model's own question text "already conveys urgency" (the spec's
    # alternate branch) isn't reliably detectable from the 8-field
    # schema without NLP judgment calls, so this always uses the static
    # fallback — flagged rather than guessed at.
    return fallbacks.static_fallback_assessment(message)


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
        prompt = system_prompt.build_system_prompt(
            profile,
            worry_level,
            regional_context,
            conversation_language=_conversation_language(message, history),
        )
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
