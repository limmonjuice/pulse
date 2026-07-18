"""
Tests for main.py — the pipeline that merges the deterministic red-flag
floor (red_flags.py) with the model's own assessment (gemini_client.py).

The pipeline is factored into a pure function, `run_pipeline`, so it can
be exercised here without the functions_framework/Firebase emulator. The
Gemini SDK is always mocked (via monkeypatching `main.gemini_client.get_assessment`)
— no live calls, no network, no API key required.

Run from functions/:
    pytest test_main.py -v

ASSUMPTION FLAGGED FOR REVIEW: crisis_lock detection needs to know
whether a *prior* assistant turn was type "crisis", but the spec's history
shape is the flat {role, content}. These tests assume the client also
echoes a "type" key on assistant turns (i.e. {role, content, type}) and
that `_history_has_crisis_lock` reads it — see the matching note in
main.py.
"""

import logging

import pytest
from firebase_functions import https_fn

import fallbacks
import gemini_client
import main
import wire_contract
from main import InvalidRequestError, run_pipeline

VALID_ASSESSMENT = {
    "type": "assessment",
    "message": "This looks mild — rest and fluids for now.",
    "quick_replies": [],
    "urgency": "monitor_at_home",
    "explanation": "Mild, short-lived symptoms.",
    "watch_for": ["Fever lasting more than 3 days"],
    "next_step": "Rest today and drink plenty of fluids.",
    "possibilities_mentioned": False,
    "self_care": ["Rest", "Drink plenty of fluids"],
    "monitoring": ["Check temperature once or twice a day"],
    "encouragement": "I'm here if anything changes — just let me know.",
    "intents": ["reporting_new_symptom"],
    "requires_clinical_reassessment": True,
    "change_type": "new_symptom",
    "reassessment_reason": None,
    "proposed_card_action": "new",
    "findings": ["mild headache"],
}

VALID_QUESTION = {
    "type": "question",
    "message": "How long have you had this?",
    "quick_replies": ["Just today", "2-3 days", "Longer"],
    "urgency": None,
    "explanation": None,
    "watch_for": [],
    "next_step": None,
    "possibilities_mentioned": False,
    "self_care": [],
    "monitoring": [],
    "encouragement": None,
    "intents": ["reporting_new_symptom"],
    "requires_clinical_reassessment": True,
    "change_type": "new_symptom",
    "reassessment_reason": None,
    "proposed_card_action": "keep",
    "findings": [],
}

VALID_CRISIS = {
    "type": "crisis",
    "message": "Thank you for telling me. I'm here.",
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

VALID_CONVERSATION = {
    "type": "conversation",
    "message": "I hear you — the advice from before still stands.",
    "quick_replies": [],
    "urgency": None,
    "explanation": None,
    "watch_for": [],
    "next_step": None,
    "possibilities_mentioned": False,
    "self_care": [],
    "monitoring": [],
    "encouragement": None,
    "intents": ["reassurance_seeking"],
    "requires_clinical_reassessment": False,
    "change_type": "none",
    "reassessment_reason": None,
    "proposed_card_action": "keep",
    "findings": [],
}

NON_SELF_HARM_RED_FLAG_MESSAGE = "I have chest pain and I'm having trouble breathing"
SELF_HARM_MESSAGE = "I want to kill myself"
BENIGN_MESSAGE = "I have a mild headache since this morning"

# Tagalog equivalents of the three messages above — same red-flag rules,
# different language, for exercising the degraded-mode language heuristic.
NON_SELF_HARM_RED_FLAG_MESSAGE_TL = "Masakit ang dibdib ko at nahihirapan akong huminga"
SELF_HARM_MESSAGE_TL = "Gusto ko nang mamatay"
BENIGN_MESSAGE_TL = "Medyo masakit ang ulo ko simula kaninang umaga"


def _mock_get_assessment(monkeypatch, payload_or_fn):
    if callable(payload_or_fn) and not isinstance(payload_or_fn, dict):
        fn = payload_or_fn
    else:
        fn = lambda *args, **kwargs: dict(payload_or_fn)
    monkeypatch.setattr(main.gemini_client, "get_assessment", fn)


def _raise_model_error(*args, **kwargs):
    raise gemini_client.ModelResponseError("boom")


def _raise_generic_gemini_error(*args, **kwargs):
    # Simulates a raw Gemini API/network failure (rate limit, timeout, auth) —
    # anything that isn't the schema-validation-driven ModelResponseError.
    raise RuntimeError("503 rate limited")


# ---------------------------------------------------------------------------
# Merge truth table — red_flags.matched, non-self-harm
# ---------------------------------------------------------------------------

def test_matched_non_self_harm_assessment_escalates_urgency_to_seek_care_now(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)  # model said monitor_at_home
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == VALID_ASSESSMENT["message"]


def test_matched_non_self_harm_assessment_already_seek_care_now_is_unaffected(monkeypatch):
    payload = {**VALID_ASSESSMENT, "urgency": "seek_care_now"}
    _mock_get_assessment(monkeypatch, payload)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["urgency"] == "seek_care_now"


def test_matched_non_self_harm_question_is_overridden_to_assessment(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_QUESTION)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN
    assert result["quick_replies"] == []


def test_matched_non_self_harm_crisis_is_respected_unchanged(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_CRISIS)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["type"] == "crisis"
    assert result["urgency"] is None
    assert result["message"] == VALID_CRISIS["message"]


@pytest.mark.parametrize("payload", [VALID_ASSESSMENT, VALID_QUESTION, VALID_CRISIS])
def test_no_match_returns_model_result_as_is(monkeypatch, payload):
    _mock_get_assessment(monkeypatch, payload)
    result = run_pipeline(message=BENIGN_MESSAGE)
    for key, value in payload.items():
        assert result[key] == value


# ---------------------------------------------------------------------------
# Self-harm forcing (outranks the ordinary merge table)
# ---------------------------------------------------------------------------

def test_self_harm_match_forces_crisis_even_if_model_returned_assessment(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=SELF_HARM_MESSAGE)
    assert result["type"] == "crisis"
    assert result["urgency"] is None
    # message content is still the model's own words — only type/urgency forced
    assert result["message"] == VALID_ASSESSMENT["message"]


def test_self_harm_match_forces_crisis_even_if_model_returned_question(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_QUESTION)
    result = run_pipeline(message=SELF_HARM_MESSAGE)
    assert result["type"] == "crisis"
    assert result["urgency"] is None


def test_self_harm_match_leaves_already_crisis_type_unaffected(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_CRISIS)
    result = run_pipeline(message=SELF_HARM_MESSAGE)
    assert result["type"] == "crisis"
    assert result["urgency"] is None


def test_self_harm_match_reflected_in_metadata(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=SELF_HARM_MESSAGE)
    assert result["metadata"]["red_flag_matched"] is True
    assert "self_harm_risk" in result["metadata"]["red_flag_rule_ids"]


# ---------------------------------------------------------------------------
# crisis_lock — prior assistant crisis turn forces crisis mode and skips
# red-flag routing this turn
# ---------------------------------------------------------------------------

def _history_with_prior_crisis_turn():
    return [
        {"role": "user", "content": "Sobrang pagod na ako sa lahat."},
        {"role": "assistant", "content": "Salamat sa pagsabi.", "type": "crisis"},
    ]


def test_crisis_lock_forces_crisis_even_with_a_benign_message(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE, history=_history_with_prior_crisis_turn())
    assert result["type"] == "crisis"
    assert result["urgency"] is None


def test_crisis_lock_skips_red_flag_routing_this_turn(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE, history=_history_with_prior_crisis_turn())
    assert result["metadata"]["red_flag_matched"] is False
    assert result["metadata"]["red_flag_rule_ids"] == []


def test_no_crisis_lock_when_history_has_no_crisis_typed_turn(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "type": "question"},
    ]
    result = run_pipeline(message=BENIGN_MESSAGE, history=history)
    assert result["type"] == "assessment"


def test_crisis_lock_ignores_type_field_on_user_turns(monkeypatch):
    # A user can't self-declare crisis_lock by echoing "type": "crisis" on
    # their own turn — only a prior assistant/model turn counts.
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    history = [{"role": "user", "content": "hi", "type": "crisis"}]
    result = run_pipeline(message=BENIGN_MESSAGE, history=history)
    assert result["type"] == "assessment"


# ---------------------------------------------------------------------------
# Degraded mode — Gemini/ModelResponseError failures
# ---------------------------------------------------------------------------

def test_degraded_mode_with_red_flag_match_returns_static_seek_care_fallback(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN


def test_degraded_mode_without_red_flag_match_returns_friendly_error(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=BENIGN_MESSAGE)
    assert result["type"] == "error"
    assert result["urgency"] is None
    assert result["message"] == main.FRIENDLY_DEGRADED_ERROR_MESSAGE_EN


def test_degraded_mode_during_crisis_lock_gives_the_crisis_fallback(monkeypatch):
    # Design choice (flagged): the spec's degraded-mode condition is written
    # as "if red_flags.matched", but during crisis_lock the red-flag check is
    # skipped entirely, so it's never "matched". Falling through to the bare
    # "try again" error message would leave someone mid-crisis with nothing
    # actionable, so crisis_lock is also treated as floor-active here — and
    # gets the crisis-specific fallback, not the generic ER one.
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=BENIGN_MESSAGE, history=_history_with_prior_crisis_turn())
    assert result["type"] == "crisis"
    assert result["urgency"] is None
    assert result["message"] == main.CRISIS_DEGRADED_FALLBACK_EN


def test_degraded_mode_during_self_harm_match_gives_the_crisis_fallback(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=SELF_HARM_MESSAGE)
    assert result["type"] == "crisis"
    assert result["urgency"] is None
    assert result["message"] == main.CRISIS_DEGRADED_FALLBACK_EN


# ---------------------------------------------------------------------------
# Degraded mode — generic Gemini/API failures (not just ModelResponseError).
# gemini_client's contract is "never surface a malformed payload"; that must
# hold for a raw API/network exception too, not only a schema-validation one.
# ---------------------------------------------------------------------------

def test_generic_gemini_failure_with_red_flag_match_returns_static_seek_care_fallback(
    monkeypatch,
):
    _mock_get_assessment(monkeypatch, _raise_generic_gemini_error)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN


def test_generic_gemini_failure_without_red_flag_match_returns_friendly_error(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_generic_gemini_error)
    result = run_pipeline(message=BENIGN_MESSAGE)
    assert result["type"] == "error"
    assert result["urgency"] is None
    assert result["message"] == main.FRIENDLY_DEGRADED_ERROR_MESSAGE_EN


# ---------------------------------------------------------------------------
# Defense in depth — red_flags.check_red_flags itself raising. red_flags.py
# now fails closed on every malformed profile value it knows how to
# recognize (see test_red_flags.py), so this is belt-and-suspenders for an
# unknown-unknown: if the deterministic floor's own evaluation fails, we
# cannot rule out an emergency pattern, so the same cautious static
# seek_care_now fallback used for Gemini failures applies — and the model
# is skipped entirely for that turn, since its text can't be trusted to
# carry the right urgency when the floor couldn't weigh in.
# ---------------------------------------------------------------------------

def _raise_red_flags_error(*args, **kwargs):
    raise TypeError("'<' not supported between instances of 'str' and 'int'")


def test_red_flags_check_raising_returns_static_seek_care_fallback(monkeypatch):
    monkeypatch.setattr(main.red_flags, "check_red_flags", _raise_red_flags_error)
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE)
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN


def test_red_flags_check_raising_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(main.red_flags, "check_red_flags", _raise_red_flags_error)
    call_count = {"n": 0}

    def _tracking_get_assessment(*args, **kwargs):
        call_count["n"] += 1
        return dict(VALID_ASSESSMENT)

    monkeypatch.setattr(main.gemini_client, "get_assessment", _tracking_get_assessment)
    run_pipeline(message=BENIGN_MESSAGE)
    assert call_count["n"] == 0


def test_red_flags_check_raising_reflected_in_metadata(monkeypatch):
    monkeypatch.setattr(main.red_flags, "check_red_flags", _raise_red_flags_error)
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE)
    assert result["metadata"]["red_flag_matched"] is True
    assert result["metadata"]["red_flag_rule_ids"] == []


def test_red_flags_check_raising_mirrors_tagalog_on_the_fallback(monkeypatch):
    monkeypatch.setattr(main.red_flags, "check_red_flags", _raise_red_flags_error)
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE_TL)
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_TL


def test_red_flags_check_not_invoked_during_crisis_lock(monkeypatch):
    # crisis_lock is determined from history before check_red_flags is ever
    # called — confirms that short-circuit still holds after wiring in the
    # try/except above.
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("check_red_flags should not be called during crisis_lock")

    monkeypatch.setattr(main.red_flags, "check_red_flags", _fail_if_called)
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE, history=_history_with_prior_crisis_turn())
    assert result["type"] == "crisis"


# ---------------------------------------------------------------------------
# Degraded mode — language mirroring via the keyword heuristic (Gemini
# itself, the usual mirroring mechanism, is unavailable in this path).
# ---------------------------------------------------------------------------

def test_degraded_mode_with_red_flag_match_mirrors_tagalog(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE_TL)
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_TL


def test_degraded_mode_without_red_flag_match_mirrors_tagalog(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=BENIGN_MESSAGE_TL)
    assert result["type"] == "error"
    assert result["message"] == main.FRIENDLY_DEGRADED_ERROR_MESSAGE_TL


def test_degraded_mode_during_self_harm_match_mirrors_tagalog(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_model_error)
    result = run_pipeline(message=SELF_HARM_MESSAGE_TL)
    assert result["type"] == "crisis"
    assert result["message"] == main.CRISIS_DEGRADED_FALLBACK_TL


def test_matched_non_self_harm_question_is_overridden_to_assessment_mirrors_tagalog(
    monkeypatch,
):
    _mock_get_assessment(monkeypatch, VALID_QUESTION)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE_TL)
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_TL


@pytest.mark.parametrize(
    "message,expected",
    [
        (BENIGN_MESSAGE, False),
        (NON_SELF_HARM_RED_FLAG_MESSAGE, False),
        (SELF_HARM_MESSAGE, False),
        (BENIGN_MESSAGE_TL, True),
        (NON_SELF_HARM_RED_FLAG_MESSAGE_TL, True),
        (SELF_HARM_MESSAGE_TL, True),
        ("check-up ko lang bukas", True),  # Taglish — any Filipino marker counts
    ],
)
def test_language_heuristic(message, expected):
    assert fallbacks.message_signals_tagalog(message) is expected


# ---------------------------------------------------------------------------
# Conversation-language derivation (1.5.5) — the server decides the
# CONVERSATION LANGUAGE directive deterministically; a tapped quick-reply
# chip (below the word threshold) can never flip an established language.
# ---------------------------------------------------------------------------

ENGLISH_OPENER_TURN = {
    "role": "user",
    "content": "Ive been feeling sick lately. whats happening to me?",
}
ASSISTANT_QUESTION_TURN = {
    "role": "assistant",
    "content": "Could you tell me more about your symptoms?",
    "type": "question",
}


def test_conversation_language_full_english_sentence():
    assert (
        main._conversation_language("I have had a sore throat since yesterday", [])
        == "english"
    )


def test_conversation_language_terse_chip_cannot_flip_english_conversation():
    # The exact 2026-07-13 in-app regression shape: English opener, then a
    # tapped chip. Even a chip carrying Tagalog markers ("May pagsusuka at
    # pagtatae") sits below _LANGUAGE_SWITCH_MIN_WORDS, so English holds.
    history = [ENGLISH_OPENER_TURN, ASSISTANT_QUESTION_TURN]
    assert main._conversation_language("Stomach pain or nausea", history) == "english"
    assert main._conversation_language("May pagsusuka at pagtatae", history) == "english"


def test_conversation_language_full_tagalog_sentence_switches():
    history = [ENGLISH_OPENER_TURN, ASSISTANT_QUESTION_TURN]
    msg = "Yung sakit ng ulo ko lumalala na po kanina pa"
    assert main._conversation_language(msg, history) == "tagalog"


def test_conversation_language_terse_only_conversation_uses_newest_confident():
    # No turn reaches the switch threshold, but a terse Tagalog opener
    # still deserves a Tagalog conversation.
    assert main._conversation_language("May lagnat ako", []) == "tagalog"


def test_conversation_language_none_when_nothing_classifies():
    assert main._conversation_language("Stomach pain or nausea", []) is None


def test_conversation_language_skips_malformed_history_turns():
    history = ["garbage", {"role": "user"}, {"role": "user", "content": 42}, None]
    assert (
        main._conversation_language("I have had a fever since yesterday morning", history)
        == "english"
    )


def test_pipeline_passes_conversation_language_directive_to_prompt(monkeypatch):
    seen = {}

    def fake(prompt, history, message):
        seen["prompt"] = prompt
        return dict(VALID_QUESTION)

    _mock_get_assessment(monkeypatch, fake)
    run_pipeline(
        message="Stomach pain or nausea",
        history=[ENGLISH_OPENER_TURN, ASSISTANT_QUESTION_TURN],
    )
    assert "CONVERSATION LANGUAGE: English." in seen["prompt"]


def test_pipeline_omits_conversation_language_directive_when_undetectable(monkeypatch):
    seen = {}

    def fake(prompt, history, message):
        seen["prompt"] = prompt
        return dict(VALID_QUESTION)

    _mock_get_assessment(monkeypatch, fake)
    run_pipeline(message="Stomach pain or nausea")
    assert "CONVERSATION LANGUAGE:" not in seen["prompt"]


# ---------------------------------------------------------------------------
# v1.4.0 fields — self_care/monitoring/encouragement on locally-constructed
# fallback payloads (never from the model, so always the safe empty shape).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "builder",
    [fallbacks.static_fallback_assessment, fallbacks.crisis_fallback_payload, fallbacks.degraded_error_payload],
)
def test_fallback_payloads_carry_new_fields_at_safe_values(builder):
    payload = builder(BENIGN_MESSAGE)
    assert payload["self_care"] == []
    assert payload["monitoring"] == []
    assert payload["encouragement"] is None


# ---------------------------------------------------------------------------
# Input validation — length cap
# ---------------------------------------------------------------------------

def test_missing_message_raises_invalid_request_error():
    with pytest.raises(InvalidRequestError):
        run_pipeline(message=None)


def test_blank_message_raises_invalid_request_error():
    with pytest.raises(InvalidRequestError):
        run_pipeline(message="   ")


def test_message_at_exact_cap_is_allowed(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    message = "a" * main.MAX_MESSAGE_LENGTH
    result = run_pipeline(message=message)
    assert result["type"] == "assessment"


def test_message_over_cap_raises_invalid_request_error(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    message = "a" * (main.MAX_MESSAGE_LENGTH + 1)
    with pytest.raises(InvalidRequestError):
        run_pipeline(message=message)


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

def test_metadata_shape_on_a_matched_request(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    metadata = result["metadata"]
    assert metadata["prompt_version"] == main.system_prompt.PROMPT_VERSION
    assert metadata["model_name"] == gemini_client.MODEL_NAME
    assert metadata["red_flag_matched"] is True
    assert "chest_pain_breathing" in metadata["red_flag_rule_ids"]


def test_metadata_shape_on_an_unmatched_request(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE)
    metadata = result["metadata"]
    assert metadata["red_flag_matched"] is False
    assert metadata["red_flag_rule_ids"] == []


def test_metadata_never_carries_red_flag_rationale_text(monkeypatch):
    # rationale is internal-only (see red_flags.RedFlagResult docstring) —
    # it must never reach the client.
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert "rationale" not in result["metadata"]
    assert "rationale" not in result


# ---------------------------------------------------------------------------
# Logging — structured, and never carries health data or secrets
# ---------------------------------------------------------------------------

def test_logging_never_includes_message_or_profile_content(monkeypatch, caplog):
    unique_message_marker = "UNIQUE_MARKER_MESSAGE_CONTENT_ZZTOP"
    unique_profile_marker = "UNIQUE_MARKER_PROFILE_CONTENT_ZZTOP"
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    with caplog.at_level(logging.INFO, logger=main.logger.name):
        run_pipeline(
            message=f"I have a mild headache, {unique_message_marker}",
            profile={"name": unique_profile_marker, "conditions": [unique_profile_marker]},
        )
    for record in caplog.records:
        haystack = repr(record.getMessage()) + repr(vars(record))
        assert unique_message_marker not in haystack
        assert unique_profile_marker not in haystack


def test_logging_includes_the_required_structured_fields(monkeypatch, caplog):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    with caplog.at_level(logging.INFO, logger=main.logger.name):
        run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.prompt_version == main.system_prompt.PROMPT_VERSION
    assert record.red_flag_rule_ids == ["chest_pain_breathing"]
    assert record.final_urgency == "seek_care_now"
    assert isinstance(record.model_latency_ms, float)
    assert record.retry_used is False


def test_logging_reports_retry_used_true_when_the_client_retried(monkeypatch, caplog):
    payload = {**VALID_ASSESSMENT, "_retry_used": True}
    _mock_get_assessment(monkeypatch, payload)
    with caplog.at_level(logging.INFO, logger=main.logger.name):
        run_pipeline(message=BENIGN_MESSAGE)
    assert caplog.records[0].retry_used is True


# ---------------------------------------------------------------------------
# Tier ordering helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("monitor_at_home", "seek_care_now", "seek_care_now"),
        ("seek_care_now", "monitor_at_home", "seek_care_now"),
        ("see_doctor_soon", "see_doctor_soon", "see_doctor_soon"),
        ("monitor_at_home", "see_doctor_soon", "see_doctor_soon"),
    ],
)
def test_max_urgency_tier_ordering(a, b, expected):
    assert wire_contract.max_urgency(a, b) == expected


# ---------------------------------------------------------------------------
# Thin request handler — input extraction and error conversion only
# (the callable itself needs a real Flask request to invoke through
# `on_call`, so tests target the undecorated `_handle_request` directly,
# per the "factor pipeline out of the handler" instruction)
# ---------------------------------------------------------------------------

def test_handle_request_extracts_fields_and_returns_pipeline_result(monkeypatch):
    captured = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    request = https_fn.CallableRequest(
        data={"message": "hi", "profile": {"age": 5}, "worry_level": "scared"},
        raw_request=None,
    )
    result = main._handle_request(request)
    assert result == {"ok": True}
    assert captured["message"] == "hi"
    assert captured["profile"] == {"age": 5}
    assert captured["worry_level"] == "scared"


def test_handle_request_converts_invalid_request_error_to_https_error(monkeypatch):
    def fake_run_pipeline(**kwargs):
        raise InvalidRequestError("too long")

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)
    request = https_fn.CallableRequest(data={"message": "hi"}, raw_request=None)
    with pytest.raises(https_fn.HttpsError) as exc_info:
        main._handle_request(request)
    assert exc_info.value.code == https_fn.FunctionsErrorCode.INVALID_ARGUMENT


def test_app_check_enforcement_defaults_to_true_when_env_var_is_absent(monkeypatch):
    # Safety pin: production must enforce App Check unless someone
    # EXPLICITLY sets ENFORCE_APP_CHECK=false in that environment. If this
    # test breaks, someone changed the default — that must be a deliberate,
    # reviewed decision, never a silent one.
    monkeypatch.delenv("ENFORCE_APP_CHECK", raising=False)
    assert main._enforce_app_check_setting() is True


def test_app_check_enforcement_can_be_disabled_for_local_emulation(monkeypatch):
    monkeypatch.setenv("ENFORCE_APP_CHECK", "false")
    assert main._enforce_app_check_setting() is False


def test_app_check_enforcement_env_var_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ENFORCE_APP_CHECK", "False")
    assert main._enforce_app_check_setting() is False


def test_app_check_enforcement_stays_on_for_unrecognized_values(monkeypatch):
    # Anything that isn't exactly "false" (case-insensitive) keeps
    # enforcement ON — a typo like "flase" must fail safe, not open.
    monkeypatch.setenv("ENFORCE_APP_CHECK", "flase")
    assert main._enforce_app_check_setting() is True


def test_deployed_function_id_is_assess_symptoms():
    # The deploy/emulator function id comes from the decorated function's
    # __name__ (via the endpoint manifest), NOT the module-level variable it
    # is assigned to. firebase-tools validates it against
    # ^[a-zA-Z][a-zA-Z0-9_-]{0,62}$ — a leading underscore (e.g. a decorated
    # _handle_request) is rejected at emulator startup.
    import re

    endpoint = main.assess_symptoms.__firebase_endpoint__
    assert endpoint.entryPoint == "assess_symptoms"
    assert re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,62}", endpoint.entryPoint)



# ---------------------------------------------------------------------------
# v2 conversation engine (Task 7): envelope, episode gates end-to-end,
# history windows, and the acceptance ceiling
# ---------------------------------------------------------------------------

def _guidance_history(urgency="see_doctor_soon"):
    """A benign two-turn history with an active card, echoed the way
    Message.toHistoryJson() v2 does."""
    return [
        {"role": "user", "content": BENIGN_MESSAGE},
        {
            "role": "assistant",
            "content": "Worth a check within 1-2 days.",
            "type": "assessment",
            "urgency": urgency,
            "findings": ["mild headache"],
            "explanation": "Worth a check within 1-2 days.",
            "next_step": "See a doctor within 1-2 days.",
        },
    ]


def test_first_assessment_gets_new_card_envelope(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    result = run_pipeline(message=BENIGN_MESSAGE)
    assert result["card"] == {"action": "new", "reason": "first_assessment"}
    assert result["conversation_state"] == {
        "urgency": "monitor_at_home",
        "assessment_active": True,
        "phase": "guidance",
    }
    assert result["assessment_cleared"] is False


def test_conversation_turn_keeps_card(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_CONVERSATION)
    result = run_pipeline(message="But I feel okay sometimes.",
                          history=_guidance_history())
    assert result["type"] == "conversation"
    assert result["card"]["action"] == "keep"
    assert result["conversation_state"]["urgency"] == "see_doctor_soon"
    assert result["conversation_state"]["assessment_active"] is True


def test_same_tier_contentless_reassessment_demotes(monkeypatch):
    redundant = {
        **VALID_ASSESSMENT,
        "urgency": "see_doctor_soon",
        "requires_clinical_reassessment": False,
        "change_type": "none",
    }
    _mock_get_assessment(monkeypatch, redundant)
    result = run_pipeline(message="Is it really necessary?",
                          history=_guidance_history())
    assert result["type"] == "conversation"          # demoted
    assert result["card"]["action"] == "keep"
    assert result["urgency"] is None                  # card fields stripped
    assert result["message"] == redundant["message"]  # text survives


def test_red_flag_mid_guidance_forces_card_update(monkeypatch):
    # The model wrongly stays conversational on a new emergency — the
    # floor guard must substitute the static fallback and update the card.
    _mock_get_assessment(monkeypatch, VALID_CONVERSATION)
    result = run_pipeline(message=NON_SELF_HARM_RED_FLAG_MESSAGE,
                          history=_guidance_history("monitor_at_home"))
    assert result["type"] == "assessment"
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN
    assert result["card"] == {"action": "update", "reason": "urgency_raised"}
    assert result["conversation_state"]["urgency"] == "seek_care_now"


def test_reset_clears_assessment(monkeypatch):
    reset_reply = {
        **VALID_CONVERSATION,
        "message": "No worries — thanks for telling me you were testing!",
        "intents": ["testing_system"],
        "proposed_card_action": "clear",
    }
    _mock_get_assessment(monkeypatch, reset_reply)
    result = run_pipeline(message="I was just testing", history=_guidance_history())
    assert result["assessment_cleared"] is True
    assert result["card"]["action"] == "clear"
    assert result["conversation_state"] == {
        "urgency": None, "assessment_active": False, "phase": "idle",
    }


def test_degraded_mid_guidance_keeps_card_and_state(monkeypatch):
    _mock_get_assessment(monkeypatch, _raise_generic_gemini_error)
    result = run_pipeline(message=BENIGN_MESSAGE, history=_guidance_history())
    assert result["type"] == "error"
    assert result["card"]["action"] == "keep"
    assert result["conversation_state"]["urgency"] == "see_doctor_soon"
    assert result["conversation_state"]["assessment_active"] is True


def test_model_history_window_caps_turns_but_latch_sees_everything(monkeypatch):
    captured = {}

    def fake(prompt, history, message):
        captured["history"] = history
        return dict(VALID_CONVERSATION)

    _mock_get_assessment(monkeypatch, fake)
    history = [{"role": "user", "content": NON_SELF_HARM_RED_FLAG_MESSAGE}]
    for i in range(29):
        role = "user" if i % 2 == 0 else "assistant"
        turn = {"role": role, "content": f"benign filler {i}"}
        if role == "assistant":
            turn["type"] = "conversation"
        history.append(turn)
    result = run_pipeline(message="thanks", history=history)
    assert len(captured["history"]) <= main.MODEL_HISTORY_WINDOW
    # The red-flag turn fell outside the model window but the latch —
    # scanned over the FULL history — still forces the floor.
    assert result["urgency"] == "seek_care_now"
    assert result["message"] == main.STATIC_SEEK_CARE_FALLBACK_EN


def test_history_over_acceptance_ceiling_is_rejected(monkeypatch):
    _mock_get_assessment(monkeypatch, VALID_ASSESSMENT)
    too_long = [{"role": "user", "content": "hi"}] * (main.MAX_ACCEPTED_HISTORY_TURNS + 1)
    with pytest.raises(InvalidRequestError):
        run_pipeline(message=BENIGN_MESSAGE, history=too_long)
    at_limit = [{"role": "user", "content": "hi"}] * main.MAX_ACCEPTED_HISTORY_TURNS
    result = run_pipeline(message=BENIGN_MESSAGE, history=at_limit)
    assert result["type"] == "assessment"


def test_logging_includes_v2_structured_fields(monkeypatch, caplog):
    _mock_get_assessment(monkeypatch, VALID_CONVERSATION)
    with caplog.at_level(logging.INFO, logger=main.logger.name):
        run_pipeline(message="thanks!", history=_guidance_history())
    record = caplog.records[0]
    assert record.intents == ["reassurance_seeking"]
    assert record.change_type == "none"
    assert record.requires_clinical_reassessment is False
    assert record.card_action == "keep"
    assert record.demoted is False
    assert record.reset_accepted is False
    assert record.deescalation_accepted is False


# ---------------------------------------------------------------------------
# Visit summary: crisis-exchange stripping (design spec §6)
# ---------------------------------------------------------------------------

from main import _strip_crisis_exchanges, _visit_summary_conversation_language


def test_strip_crisis_exchanges_removes_crisis_reply_and_its_preceding_user_turn():
    history = [
        {"role": "user", "content": "I have a mild headache"},
        {"role": "assistant", "content": "That sounds manageable.", "type": "conversation"},
        {"role": "user", "content": "I want to kill myself"},
        {"role": "assistant", "content": "I'm here for you.", "type": "crisis"},
    ]
    result = _strip_crisis_exchanges(history)
    assert result == history[:2]


def test_strip_crisis_exchanges_handles_multiple_crisis_turns():
    history = [
        {"role": "user", "content": "first crisis statement"},
        {"role": "assistant", "content": "reply 1", "type": "crisis"},
        {"role": "user", "content": "I'm okay now, just a headache"},
        {"role": "assistant", "content": "Glad to hear it.", "type": "conversation"},
        {"role": "user", "content": "second crisis statement"},
        {"role": "assistant", "content": "reply 2", "type": "crisis"},
    ]
    result = _strip_crisis_exchanges(history)
    assert result == history[2:4]


def test_strip_crisis_exchanges_no_op_when_no_crisis_turn():
    history = [
        {"role": "user", "content": "I have a mild headache"},
        {"role": "assistant", "content": "That sounds manageable.", "type": "conversation"},
    ]
    assert _strip_crisis_exchanges(history) == history


def test_strip_crisis_exchanges_crisis_only_conversation_strips_to_empty():
    history = [
        {"role": "user", "content": "crisis statement"},
        {"role": "assistant", "content": "reply", "type": "crisis"},
    ]
    assert _strip_crisis_exchanges(history) == []


def test_strip_crisis_exchanges_handles_leading_crisis_turn_with_no_preceding_user_turn():
    # Defensive: a crisis turn at index 0 has no preceding turn to drop.
    history = [
        {"role": "assistant", "content": "reply", "type": "crisis"},
        {"role": "user", "content": "I'm okay now"},
    ]
    result = _strip_crisis_exchanges(history)
    assert result == history[1:]


def test_strip_crisis_exchanges_never_leaks_crisis_turn_text():
    # The structural property (spec §6/§8), not just "the right length":
    # assert the actual crisis-turn text and its paired user statement's
    # text are both gone, not merely that *a* turn was removed.
    history = [
        {"role": "user", "content": "I want to end my life"},
        {"role": "assistant", "content": "I'm here for you.", "type": "crisis"},
        {"role": "user", "content": "a benign follow-up"},
        {"role": "assistant", "content": "glad to hear it", "type": "conversation"},
    ]
    result = _strip_crisis_exchanges(history)
    texts = [turn["content"] for turn in result]
    assert "I want to end my life" not in texts
    assert "I'm here for you." not in texts


def test_strip_crisis_exchanges_tolerates_malformed_preceding_turn():
    # A malformed (non-dict) entry immediately before a crisis turn must
    # not crash the strip — it's client-supplied JSON, and the whole
    # point of this server-side re-strip is not trusting the client. The
    # crisis turn itself is still dropped; the malformed entry can't be
    # safely identified as "the preceding user turn" so it is left alone.
    history = [
        "not a dict",
        {"role": "assistant", "content": "reply", "type": "crisis"},
        {"role": "user", "content": "a benign follow-up"},
    ]
    result = _strip_crisis_exchanges(history)
    assert result == ["not a dict", {"role": "user", "content": "a benign follow-up"}]


def test_strip_crisis_exchanges_drops_all_contiguous_preceding_user_turns():
    # A malformed/tampered-client history could have more than one
    # consecutive user turn before a crisis reply. Only stripping the
    # nearest one would leak the earlier (possibly crisis-triggering)
    # statement into the transcript. Both must go.
    history = [
        {"role": "user", "content": "I want to kill myself tonight"},
        {"role": "user", "content": "sorry, ignore that, just kidding"},
        {"role": "assistant", "content": "I am here for you.", "type": "crisis"},
    ]
    result = _strip_crisis_exchanges(history)
    assert result == []


# ---------------------------------------------------------------------------
# Visit summary: conversation-language derivation with no distinct "new
# message" (design spec §4.2)
# ---------------------------------------------------------------------------

def test_visit_summary_conversation_language_derives_from_history_alone():
    history = [
        {"role": "user", "content": "Masakit ang ulo ko simula kagabi pa"},
    ]
    assert _visit_summary_conversation_language(history) == "tagalog"


def test_visit_summary_conversation_language_none_on_empty_history():
    assert _visit_summary_conversation_language([]) is None
