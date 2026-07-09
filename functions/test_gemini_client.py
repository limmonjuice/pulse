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

@pytest.mark.parametrize("payload", [VALID_ASSESSMENT, VALID_QUESTION, VALID_CRISIS])
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


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS])
def test_rejects_non_empty_self_care_outside_assessment(monkeypatch, base):
    bad = {**base, "self_care": ["Rest"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(base)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == base


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS])
def test_rejects_non_empty_monitoring_outside_assessment(monkeypatch, base):
    bad = {**base, "monitoring": ["Check in tomorrow"]}
    _install_fake_genai(monkeypatch, [json.dumps(bad), json.dumps(base)])
    result = get_assessment("system prompt", [], "some message")
    assert _strip_meta(result) == base


@pytest.mark.parametrize("base", [VALID_QUESTION, VALID_CRISIS])
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
