"""
Tests for gemini_client.py — the Gemini SDK wrapper.

The Gemini SDK itself is always mocked here (via genai.Client, the
google.genai entry point); no live calls, no network, no API key
required. Run from functions/:
    pytest test_gemini_client.py -v
"""

import json

import pytest

import gemini_client
from gemini_client import ModelResponseError, get_assessment

VALID_ASSESSMENT = {
    "type": "assessment",
    "message": "This looks mild — rest and fluids for now.",
    "quick_replies": [],
    "urgency": "monitor_at_home",
    "explanation": "Mild, short-lived symptoms in an otherwise healthy adult.",
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
    "findings": ["mild fever"],
}

VALID_QUESTION = {
    "type": "question",
    "message": "How long have you had this fever?",
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

# v2 (conversation engine): a plain reply turn — answers the person's
# message without re-triaging. No card fields, no urgency.
VALID_CONVERSATION = {
    "type": "conversation",
    "message": "I'm glad you're feeling okay at times — the advice still stands.",
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

REQUIRED_FIELDS = list(VALID_ASSESSMENT.keys())


def _strip_meta(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeModelsApi:
    """Stands in for genai.Client().models. Feed it a queue of response
    texts (one per call) so tests can script first-attempt vs retry
    behavior. Records every call's `contents`/`model`/`config` for
    assertions."""

    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = []  # list of `contents` passed to each call
        self.model_name = None
        self.config = None

    def generate_content(self, *, model, contents, config):
        self.calls.append(contents)
        self.model_name = model
        self.config = config
        if not self._texts:
            raise AssertionError("generate_content called more times than scripted")
        return _FakeResponse(self._texts.pop(0))


class _FakeClient:
    def __init__(self, texts):
        self.models = _FakeModelsApi(texts)


def _install_fake_genai(monkeypatch, texts):
    fake_client = _FakeClient(texts)
    monkeypatch.setattr(gemini_client.genai, "Client", lambda *args, **kwargs: fake_client)
    return fake_client.models


# ---------------------------------------------------------------------------
# Fence-stripping
# ---------------------------------------------------------------------------

def test_strips_json_language_tagged_fence(monkeypatch):
    text = "```json\n" + json.dumps(VALID_ASSESSMENT) + "\n```"
    _install_fake_genai(monkeypatch, [text])
    result = get_assessment("system prompt", [], "I have a mild fever")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_strips_bare_fence_with_no_language_tag(monkeypatch):
    text = "```\n" + json.dumps(VALID_ASSESSMENT) + "\n```"
    _install_fake_genai(monkeypatch, [text])
    result = get_assessment("system prompt", [], "I have a mild fever")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_accepts_plain_json_with_no_fence(monkeypatch):
    text = json.dumps(VALID_ASSESSMENT)
    _install_fake_genai(monkeypatch, [text])
    result = get_assessment("system prompt", [], "I have a mild fever")
    assert _strip_meta(result) == VALID_ASSESSMENT


# ---------------------------------------------------------------------------
# Accepting each valid type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload", [VALID_ASSESSMENT, VALID_QUESTION, VALID_CRISIS, VALID_CONVERSATION]
)
def test_accepts_each_valid_type(monkeypatch, payload):
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


# ---------------------------------------------------------------------------
# Schema validation — field-by-field rejection (each retries once, then
# succeeds on a valid retry response)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_rejects_response_missing_a_required_field_then_retries(monkeypatch, field):
    bad = {k: v for k, v in VALID_ASSESSMENT.items() if k != field}
    fake_models = _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)]
    )
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT
    assert len(fake_models.calls) == 2


def test_rejects_invalid_type_value(monkeypatch):
    bad = {**VALID_ASSESSMENT, "type": "diagnosis"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_rejects_invalid_urgency_value(monkeypatch):
    bad = {**VALID_ASSESSMENT, "urgency": "call_911"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_rejects_assessment_with_null_urgency(monkeypatch):
    bad = {**VALID_ASSESSMENT, "urgency": None}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_rejects_crisis_with_non_null_urgency(monkeypatch):
    bad = {**VALID_CRISIS, "urgency": "seek_care_now"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CRISIS)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CRISIS


def test_rejects_question_with_one_quick_reply(monkeypatch):
    bad = {**VALID_QUESTION, "quick_replies": ["only one"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_QUESTION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_QUESTION


def test_rejects_question_with_five_quick_replies(monkeypatch):
    bad = {**VALID_QUESTION, "quick_replies": ["a", "b", "c", "d", "e"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_QUESTION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_QUESTION


@pytest.mark.parametrize("count", [2, 3, 4])
def test_accepts_question_with_boundary_quick_reply_counts(monkeypatch, count):
    payload = {**VALID_QUESTION, "quick_replies": [f"reply {i}" for i in range(count)]}
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS, VALID_CONVERSATION])
def test_rejects_non_empty_self_care_outside_assessment(monkeypatch, base):
    bad = {**base, "self_care": ["Rest"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(base)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == base


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS, VALID_CONVERSATION])
def test_rejects_non_empty_monitoring_outside_assessment(monkeypatch, base):
    bad = {**base, "monitoring": ["Check in tomorrow"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(base)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == base


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS, VALID_CONVERSATION])
def test_rejects_non_null_encouragement_outside_assessment(monkeypatch, base):
    bad = {**base, "encouragement": "I'm here for you."}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(base)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == base


def test_rejects_assessment_with_null_encouragement(monkeypatch):
    bad = {**VALID_ASSESSMENT, "encouragement": None}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_accepts_assessment_with_empty_self_care_and_monitoring(monkeypatch):
    # A seek_care_now assessment can validly have no home-care/monitoring
    # plan — "go now" is the plan.
    payload = {**VALID_ASSESSMENT, "self_care": [], "monitoring": []}
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


def test_rejects_non_json_object_payload(monkeypatch):
    _install_fake_genai(
        monkeypatch, [json.dumps(["not", "an", "object"]), json.dumps(VALID_ASSESSMENT)]
    )
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


def test_rejects_malformed_json_then_retries(monkeypatch):
    fake_models = _install_fake_genai(
        monkeypatch, ["not json at all {{{", json.dumps(VALID_ASSESSMENT)]
    )
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT
    assert len(fake_models.calls) == 2


# ---------------------------------------------------------------------------
# v2 proposal fields (conversation engine)
# ---------------------------------------------------------------------------

def test_conversation_accepts_up_to_four_quick_replies(monkeypatch):
    payload = {**VALID_CONVERSATION, "quick_replies": ["a", "b", "c", "d"]}
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


def test_conversation_rejects_five_quick_replies(monkeypatch):
    bad = {**VALID_CONVERSATION, "quick_replies": ["a", "b", "c", "d", "e"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


@pytest.mark.parametrize("field,value", [
    ("urgency", "monitor_at_home"),
    ("explanation", "an explanation"),
    ("next_step", "a next step"),
])
def test_conversation_rejects_card_fields(monkeypatch, field, value):
    bad = {**VALID_CONVERSATION, field: value}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


@pytest.mark.parametrize("intents", [
    [],                                          # empty
    ["bogus_intent"],                            # unknown value
    ["asking_why", "thanking", "joke", "greeting"],  # more than 3
    "asking_why",                                # not a list
])
def test_rejects_invalid_intents(monkeypatch, intents):
    bad = {**VALID_CONVERSATION, "intents": intents}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


def test_accepts_three_valid_intents(monkeypatch):
    payload = {
        **VALID_CONVERSATION,
        "intents": ["emotional_support", "asking_about_recommendation", "asking_why"],
    }
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


def test_rejects_unknown_change_type(monkeypatch):
    bad = {**VALID_CONVERSATION, "change_type": "bogus"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


@pytest.mark.parametrize("change", [
    "new_symptom", "resolved_symptom", "worsening",
    "new_history", "treatment_update", "none",
])
def test_accepts_each_valid_change_type(monkeypatch, change):
    payload = {**VALID_CONVERSATION, "change_type": change}
    _install_fake_genai(monkeypatch, [json.dumps(payload)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == payload


def test_rejects_non_bool_requires_clinical_reassessment(monkeypatch):
    bad = {**VALID_CONVERSATION, "requires_clinical_reassessment": "yes"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


def test_rejects_unknown_proposed_card_action(monkeypatch):
    bad = {**VALID_CONVERSATION, "proposed_card_action": "replace"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


def test_rejects_non_string_reassessment_reason(monkeypatch):
    bad = {**VALID_CONVERSATION, "reassessment_reason": 42}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_CONVERSATION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_CONVERSATION


def test_rejects_findings_outside_assessment(monkeypatch):
    bad = {**VALID_QUESTION, "findings": ["fever"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_QUESTION)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_QUESTION


def test_rejects_non_list_findings(monkeypatch):
    bad = {**VALID_ASSESSMENT, "findings": "fever"}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == VALID_ASSESSMENT


# ---------------------------------------------------------------------------
# Retry mechanics
# ---------------------------------------------------------------------------

def test_retries_exactly_once_then_raises_on_second_failure(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, ["garbage one", "garbage two"])
    with pytest.raises(ModelResponseError):
        get_assessment("system prompt", [], "some message")
    assert len(fake_models.calls) == 2


def test_retry_request_includes_corrective_suffix(monkeypatch):
    fake_models = _install_fake_genai(
        monkeypatch, ["garbage", json.dumps(VALID_ASSESSMENT)]
    )
    get_assessment("system prompt", [], "some message")
    retry_contents = fake_models.calls[1]
    retry_text = str(retry_contents)
    assert "not valid JSON" in retry_text or "valid JSON" in retry_text


def test_does_not_retry_when_first_response_is_valid(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    get_assessment("system prompt", [], "some message")
    assert len(fake_models.calls) == 1


def test_retry_used_is_false_on_first_attempt_success(monkeypatch):
    _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    result = get_assessment("system prompt", [], "some message")
    assert result["_retry_used"] is False


def test_retry_used_is_true_when_the_retry_succeeded(monkeypatch):
    _install_fake_genai(
        monkeypatch, ["garbage", json.dumps(VALID_ASSESSMENT)]
    )
    result = get_assessment("system prompt", [], "some message")
    assert result["_retry_used"] is True


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------

def test_uses_configured_model_name_constant(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    get_assessment("system prompt", [], "some message")
    assert fake_models.model_name == gemini_client.MODEL_NAME


def test_uses_low_temperature_for_calibration(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    get_assessment("system prompt", [], "some message")
    assert 0.2 <= fake_models.config.temperature <= 0.4


def test_requests_json_response_mime_type(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    get_assessment("system prompt", [], "some message")
    assert fake_models.config.response_mime_type == "application/json"


def test_passes_system_prompt_through(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    get_assessment("a very specific system prompt", [], "some message")
    assert fake_models.config.system_instruction == "a very specific system prompt"


def test_includes_prior_history_turns_in_the_request(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_ASSESSMENT)])
    history = [
        {"role": "user", "content": "earlier message"},
        {"role": "assistant", "content": "earlier reply"},
    ]
    get_assessment("system prompt", history, "latest message")
    sent = str(fake_models.calls[0])
    assert "earlier message" in sent
    assert "earlier reply" in sent
    assert "latest message" in sent


# ---------------------------------------------------------------------------
# No Firebase imports (gemini_client.py must be unit-testable standalone)
# ---------------------------------------------------------------------------

def test_module_has_no_firebase_imports():
    import pathlib

    source = pathlib.Path(gemini_client.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "firebase" not in stripped.lower(), f"unexpected Firebase import: {line!r}"


# ---------------------------------------------------------------------------
# Model-swap guard (B3, 2026-07-13): changing MODEL_NAME without a
# MODEL_CHANGELOG entry must fail the suite. The 3.1-flash-lite swap
# shipped with evals un-rerun and hid a language-mirroring regression —
# this makes that class of silent swap impossible.
# ---------------------------------------------------------------------------

def test_current_model_has_a_changelog_entry():
    logged_models = [entry["model"] for entry in gemini_client.MODEL_CHANGELOG]
    assert gemini_client.MODEL_NAME in logged_models, (
        f"MODEL_NAME {gemini_client.MODEL_NAME!r} has no MODEL_CHANGELOG entry — "
        "add one (date + reason + evals_rerun) before changing the model string. "
        "A model swap invalidates every eval baseline in evals/results/."
    )


def test_changelog_entries_carry_date_reason_and_evals_rerun():
    import re

    assert gemini_client.MODEL_CHANGELOG, "MODEL_CHANGELOG must never be empty"
    for entry in gemini_client.MODEL_CHANGELOG:
        assert {"model", "date", "reason", "evals_rerun"} <= set(entry), entry
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["date"]), entry["date"]
        assert entry["reason"].strip(), "reason must not be empty"
        # Honest tri-state: yes, no, or partial — with room for detail after.
        assert entry["evals_rerun"].strip().lower().startswith(("yes", "no", "partial")), (
            entry["evals_rerun"]
        )


def test_changelog_is_ordered_and_ends_with_current_model():
    # The last entry is the active model — keeps the file readable as a
    # chronological history and makes "what changed last" unambiguous.
    assert gemini_client.MODEL_CHANGELOG[-1]["model"] == gemini_client.MODEL_NAME
    dates = [entry["date"] for entry in gemini_client.MODEL_CHANGELOG]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# get_visit_summary + tier-language blocklist (design spec 2026-07-17 §4.4)
# ---------------------------------------------------------------------------

from gemini_client import TierLanguageDetectedError, get_visit_summary

VALID_VISIT_SUMMARY = {
    "summary": "The conversation covered a mild headache that started this morning.",
    "questions_for_doctor": [
        "Could this be related to recent sleep changes?",
    ],
}


def test_get_visit_summary_accepts_a_valid_payload(monkeypatch):
    _install_fake_genai(monkeypatch, [json.dumps(VALID_VISIT_SUMMARY)])
    result = get_visit_summary("system prompt", [])
    assert result["summary"] == VALID_VISIT_SUMMARY["summary"]
    assert result["questions_for_doctor"] == VALID_VISIT_SUMMARY["questions_for_doctor"]
    assert result["_retry_used"] is False


def test_get_visit_summary_rejects_missing_summary_then_retries(monkeypatch):
    bad = {"questions_for_doctor": []}
    fake_models = _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_VISIT_SUMMARY)]
    )
    result = get_visit_summary("system prompt", [])
    assert result["summary"] == VALID_VISIT_SUMMARY["summary"]
    assert len(fake_models.calls) == 2


def test_get_visit_summary_rejects_empty_summary(monkeypatch):
    bad = {**VALID_VISIT_SUMMARY, "summary": "   "}
    _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_VISIT_SUMMARY)]
    )
    result = get_visit_summary("system prompt", [])
    assert result["summary"] == VALID_VISIT_SUMMARY["summary"]


def test_get_visit_summary_rejects_non_string_question(monkeypatch):
    bad = {**VALID_VISIT_SUMMARY, "questions_for_doctor": [42]}
    _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_VISIT_SUMMARY)]
    )
    result = get_visit_summary("system prompt", [])
    assert result["questions_for_doctor"] == VALID_VISIT_SUMMARY["questions_for_doctor"]


@pytest.mark.parametrize("phrase", [
    "you should see a doctor soon",
    "SEEK CARE NOW",
    "Monitor at Home for now",
    "kailangan mo nang pumunta sa doktor",
    "magpatingin ka na agad",
])
def test_get_visit_summary_rejects_tier_language_in_summary(monkeypatch, phrase):
    bad = {**VALID_VISIT_SUMMARY, "summary": f"The conversation suggested {phrase}."}
    _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_VISIT_SUMMARY)]
    )
    result = get_visit_summary("system prompt", [])
    assert result["summary"] == VALID_VISIT_SUMMARY["summary"]


def test_get_visit_summary_rejects_tier_language_in_a_question(monkeypatch):
    bad = {
        **VALID_VISIT_SUMMARY,
        "questions_for_doctor": ["Should I seek care now given the fever?"],
    }
    _install_fake_genai(
        monkeypatch, [json.dumps(bad), json.dumps(VALID_VISIT_SUMMARY)]
    )
    result = get_visit_summary("system prompt", [])
    assert result["questions_for_doctor"] == VALID_VISIT_SUMMARY["questions_for_doctor"]


def test_get_visit_summary_blocklist_failure_is_a_tier_language_detected_error(monkeypatch):
    bad = {**VALID_VISIT_SUMMARY, "summary": "You should seek care now."}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(bad)])
    with pytest.raises(ModelResponseError) as exc_info:
        get_visit_summary("system prompt", [])
    assert isinstance(exc_info.value.__cause__, TierLanguageDetectedError)


def test_get_visit_summary_schema_failure_is_not_a_tier_language_detected_error(monkeypatch):
    _install_fake_genai(monkeypatch, ["garbage one", "garbage two"])
    with pytest.raises(ModelResponseError) as exc_info:
        get_visit_summary("system prompt", [])
    assert not isinstance(exc_info.value.__cause__, TierLanguageDetectedError)


def test_get_visit_summary_sends_history_as_contents_with_no_trailing_message(monkeypatch):
    fake_models = _install_fake_genai(monkeypatch, [json.dumps(VALID_VISIT_SUMMARY)])
    history = [
        {"role": "user", "content": "I have a headache"},
        {"role": "assistant", "content": "How long?", "type": "question"},
        {"role": "user", "content": "Since this morning"},
    ]
    get_visit_summary("system prompt", history)
    sent = fake_models.calls[0]
    assert len(sent) == 3  # exactly the 3 history turns — no extra trailing content
