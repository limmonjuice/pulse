"""
Cloud Functions entry point for Pulse.

Defines the one Callable Function the Flutter client invokes via the
`cloud_functions` package (never raw HTTP): `assess_symptoms`. This is
the only layer allowed to orchestrate a Gemini call, composing the five
components of the conversation engine (spec §3):

    State Builder    episode_state.derive_episode_state — episode state
                     from client-echoed history (red-flag latch, resets)
    Prompt Builder   system_prompt.build_system_prompt (+ the
                     CONVERSATION STATE block built here)
    LLM              gemini_client.get_assessment — ONE call per message;
                     its structured outputs are proposals, never decisions
    Safety Engine    safety_engine.apply_gates — crisis force, urgency
                     clamp, floor guard, reset gate, card directive matrix
    Response Builder this module — the client envelope (turn payload +
                     card directive + conversation_state snapshot)

The AI never gets the final say on emergencies; the deterministic layers
(red_flags.py via the State Builder and Safety Engine) do.

Client-facing response has 5 possible "type" values: the 4 the model can
emit ("question", "assessment", "crisis", "conversation" — see
gemini_client.VALID_TYPES) plus a 5th, "error", constructed only here
for degraded mode when Gemini itself is unavailable. The model must
never emit "error" itself.

History trust (v1 limitation): `history` is client-supplied and not
verified against Firestore. A malicious client could fabricate turns
(including a fake prior "crisis" turn, a fabricated assistant reply, or
a forged reset marker). Accepted for v1; revisit once conversations are
persisted server-side. The client contract for assistant-turn echoes
(type, urgency, findings, explanation, next_step, assessment_cleared)
is documented in episode_state.py and Message.toHistoryJson().

No Firestore writes this pass — the client persists messages for now;
server-side persistence lands with the episode model.
"""

from __future__ import annotations

import logging
import os
import time

import firebase_admin
from firebase_functions import https_fn

import episode_state
import fallbacks
import gemini_client
import mirror_probes
import red_flags
import safety_engine
import system_prompt

# Required once per process: firebase_functions' App Check/auth token
# verification (used by the enforce_app_check=True below) reads through
# the default firebase_admin app. No Firestore/other admin SDK usage this
# pass — see the module docstring.
firebase_admin.initialize_app()

MAX_MESSAGE_LENGTH = 2000

# The model sees at most this many history turns (token cost); episode
# derivation and the language directive always scan the FULL accepted
# history — truncation is safe for the model because the CONVERSATION
# STATE block carries the active card's context forward regardless of
# which turns fell out of the window (spec §10).
MODEL_HISTORY_WINDOW = 20

# Hard acceptance ceiling on client-supplied history (episode_state
# quality review, 2026-07-14): the latch scan and _conversation_language
# are O(history) per request and nothing else bounds the input. Reject
# rather than silently truncate — truncation could drop an old red-flag
# turn and weaken the latch.
MAX_ACCEPTED_HISTORY_TURNS = 200
HISTORY_TOO_LONG_MESSAGE = (
    "This conversation has gotten quite long — please start a new chat "
    "so I can help properly."
)

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


def _strip_crisis_exchanges(history: list[dict]) -> list[dict]:
    """Removes each assistant turn with type == "crisis" AND every
    contiguous user turn immediately preceding it (design spec §6).
    Message.toHistoryJson() on the client only ever tags `type` on
    assistant turns — the preceding user turn(s) are untagged
    {"role": "user", "content": ...} entries, so a filter that only
    drops type == "crisis" entries would leave the triggering
    statement(s) in the transcript. A well-formed history has exactly
    one user turn before a crisis reply, but this is the server-side
    half of the two-strip-points design (the client runs the same rule
    before the request is ever sent; this re-strip does not assume the
    client did its part correctly, or that its history is well-formed)
    — so the walk continues backward through however many consecutive
    user turns it finds, stopping at the first non-user or non-dict
    entry, to guarantee no crisis-adjacent user statement survives.
    Applied for every crisis turn in the conversation, not just the
    first."""
    drop_indices: set[int] = set()
    for i, turn in enumerate(history):
        if (
            isinstance(turn, dict)
            and turn.get("role") == "assistant"
            and turn.get("type") == "crisis"
        ):
            drop_indices.add(i)
            j = i - 1
            while j >= 0 and isinstance(history[j], dict) and history[j].get("role") == "user":
                drop_indices.add(j)
                j -= 1
    return [turn for i, turn in enumerate(history) if i not in drop_indices]


def _visit_summary_conversation_language(history: list[dict]) -> str | None:
    """Reuses _conversation_language's deterministic derivation for a
    transcript with no distinct "new message" — generate_visit_summary is
    retrospective, not a live turn. Passing message="" is safe:
    mirror_probes.detect_language("") always returns "unknown" (an empty
    string never confidently classifies), so the newest-turn-first walk
    falls straight through to history's own user turns, exactly as
    intended."""
    return _conversation_language(message="", history=history)


logger = logging.getLogger("pulse.assess_symptoms")


class InvalidRequestError(Exception):
    """Raised for malformed client input (missing/oversized message,
    over-ceiling history). The handler converts this to an
    https_fn.HttpsError; it never reaches run_pipeline's caller as a
    bare payload."""


# ---------------------------------------------------------------------------
# Small builders (degraded mode + envelope)
# ---------------------------------------------------------------------------

def _select_degraded_payload(*, message: str, force_crisis: bool, floor_active: bool) -> dict:
    """Shared by every Gemini-call failure mode — schema-validation failures
    (ModelResponseError) and raw API/network failures alike. gemini_client's
    contract is that callers never see a malformed payload; this is the one
    place that promise is kept regardless of why the call failed.

    floor_active is deliberately scoped to THIS turn's signals (current
    red-flag match, crisis force, or a crashed check) — an episode latch
    from earlier turns alone does not re-emit the static fallback, because
    the guidance it forced is already on the person's screen (spec §9)."""
    if force_crisis:
        return fallbacks.crisis_fallback_payload(message)
    if floor_active:
        return fallbacks.static_fallback_assessment(message)
    return fallbacks.degraded_error_payload(message)


def _degraded_card(state: episode_state.EpisodeState, payload: dict) -> tuple[str, str]:
    """Card directive for degraded turns — the Safety Engine never saw a
    model proposal, so the only card-worthy event is the static fallback
    newly raising (or setting) the visible urgency."""
    if payload.get("type") == "assessment":
        if state.current_urgency is None:
            return "new", "first_assessment"
        if payload.get("urgency") != state.current_urgency:
            return "update", "urgency_raised"
    return "keep", "none"


def _conversation_state_summary(state: episode_state.EpisodeState,
                                history: list[dict]) -> dict | None:
    """The Prompt Builder's episode snapshot (spec §7). None on a fresh
    conversation — the block is omitted entirely."""
    if not history:
        return None
    return {
        "current_urgency": state.current_urgency,
        "active_findings": state.active_findings,
        "last_assessment": state.last_assessment,
        "latch_active": state.min_safe_urgency is not None,
        "questions_used": state.questions_used,
    }


def _post_turn_state(state: episode_state.EpisodeState, payload: dict,
                     card_action: str) -> dict:
    """The envelope's conversation_state snapshot — what is true AFTER
    this turn. Drives the client's pinned UrgencyStrip; the client applies
    no urgency logic of its own (AGENTS.md AI/Backend rule 7)."""
    if payload.get("type") == "crisis":
        return {"urgency": None, "assessment_active": False, "phase": "crisis"}
    if card_action == "clear":
        return {"urgency": None, "assessment_active": False, "phase": "idle"}
    if payload.get("type") == "assessment" and card_action in ("new", "update"):
        return {
            "urgency": payload.get("urgency"),
            "assessment_active": True,
            "phase": "guidance",
        }
    urgency = state.current_urgency
    if urgency is not None:
        phase = "guidance"
    elif payload.get("type") == "question":
        phase = "assessing"
    else:
        phase = "idle"
    return {
        "urgency": urgency,
        "assessment_active": urgency is not None,
        "phase": phase,
    }


def _log_request(
    *, prompt_version: str, red_flag_rule_ids: list[str], final_urgency: str | None,
    latency_ms: float, retry_used: bool, intents: list, change_type: str | None,
    requires_clinical_reassessment: bool | None, card_action: str, demoted: bool,
    reset_accepted: bool, deescalation_accepted: bool,
    proposed_vs_final_urgency: str,
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
            "intents": intents,
            "change_type": change_type,
            "requires_clinical_reassessment": requires_clinical_reassessment,
            "card_action": card_action,
            "demoted": demoted,
            "reset_accepted": reset_accepted,
            "deescalation_accepted": deescalation_accepted,
            "proposed_vs_final_urgency": proposed_vs_final_urgency,
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
    if len(history) > MAX_ACCEPTED_HISTORY_TURNS:
        raise InvalidRequestError(HISTORY_TOO_LONG_MESSAGE)

    # State Builder: crisis lock (assistant crisis turns OR a self-harm
    # match anywhere in the full history) plus latch/urgency/scaffolding.
    state = episode_state.derive_episode_state(history, profile)
    crisis_lock = state.phase == "crisis"

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
    # an ordinary red flag matched THIS turn, this turn is crisis-forced,
    # or the floor's own check crashed and we can't rule an emergency out —
    # crisis_lock skips the ordinary check above but is itself a stronger
    # floor signal, so it counts too (see the degraded-mode test for why).
    floor_active = force_crisis or bool(red_flag_result and red_flag_result.matched) or red_flags_crashed
    rule_ids_now = list(red_flag_result.rule_ids) if red_flag_result else []

    start = time.perf_counter()
    if red_flags_crashed:
        model_result = _select_degraded_payload(
            message=message, force_crisis=force_crisis, floor_active=True
        )
        retry_used = False
        degraded = True
    else:
        # Prompt Builder: static persona/rules + the dynamic tail
        # (language directive + episode snapshot).
        prompt = system_prompt.build_system_prompt(
            profile,
            worry_level,
            regional_context,
            conversation_language=_conversation_language(message, history),
            conversation_state=_conversation_state_summary(state, history),
        )
        # LLM: the model sees only the post-reset tail of history, capped
        # at MODEL_HISTORY_WINDOW turns; derivation above saw all of it.
        model_history = history[state.reset_index + 1:][-MODEL_HISTORY_WINDOW:]
        try:
            model_result = gemini_client.get_assessment(prompt, model_history, message)
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

    proposed_urgency = model_result.get("urgency")

    # Safety Engine: the model proposed; deterministic gates dispose.
    if degraded:
        final_payload = model_result
        card_action, card_reason = _degraded_card(state, final_payload)
        assessment_cleared = False
        demoted = reset_accepted = deescalation_accepted = False
    else:
        gate = safety_engine.apply_gates(
            state=state,
            message=message,
            current_match_rule_ids=rule_ids_now,
            force_crisis=force_crisis,
            model_result=model_result,
        )
        final_payload = gate.payload
        card_action, card_reason = gate.card_action, gate.card_reason
        assessment_cleared = gate.assessment_cleared
        demoted = gate.demoted
        reset_accepted = gate.reset_accepted
        deescalation_accepted = gate.deescalation_accepted

    _log_request(
        prompt_version=system_prompt.PROMPT_VERSION,
        red_flag_rule_ids=rule_ids_now,
        final_urgency=final_payload.get("urgency"),
        latency_ms=latency_ms,
        retry_used=retry_used,
        intents=final_payload.get("intents", []),
        change_type=final_payload.get("change_type"),
        requires_clinical_reassessment=final_payload.get("requires_clinical_reassessment"),
        card_action=card_action,
        demoted=demoted,
        reset_accepted=reset_accepted,
        deescalation_accepted=deescalation_accepted,
        proposed_vs_final_urgency=f"{proposed_urgency}->{final_payload.get('urgency')}",
    )

    # Response Builder: turn payload + card directive + state snapshot.
    return {
        **final_payload,
        "assessment_cleared": assessment_cleared,
        "card": {"action": card_action, "reason": card_reason},
        "conversation_state": _post_turn_state(state, final_payload, card_action),
        "metadata": {
            "prompt_version": system_prompt.PROMPT_VERSION,
            "red_flag_matched": bool(red_flag_result and red_flag_result.matched) or red_flags_crashed,
            "red_flag_rule_ids": rule_ids_now,
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
