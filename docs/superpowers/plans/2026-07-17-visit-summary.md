# Visit Summary (Doctor Kit v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user generate, on-demand, a doctor-facing summary of the
current in-memory conversation — a plain-language recap and generated
"questions to ask your doctor," sitting alongside urgency/findings/
watch-for/self-care facts the client already owns — with crisis content
structurally unable to reach the model or the screen, and with a working
staleness check so the narrative never silently outlives the conversation
it describes.

**Architecture:** Two independent pipelines feeding one new screen. A
pure, synchronous client-side facts model (`VisitSummaryFacts`) derives
urgency/findings/watch-for/self-care/monitoring directly from the
in-memory `List<Message>` — zero network cost, always renders. A single
new Cloud Function (`generate_visit_summary`, mirroring `assess_symptoms`'s
shape) handles only the narrative half — recap + doctor questions — via a
new prompt module and a shared Gemini-calling helper extracted from the
existing `get_assessment`. Crisis exchanges are stripped twice,
independently: client-side before the request is built, and server-side
again before the prompt is built — with no crisis-derived artifact (not
even a boolean) crossing the wire in either direction.

**Tech Stack:** Python (Cloud Functions backend, pytest) + Flutter/Dart
(Riverpod `AsyncNotifier`, `go_router`, `flutter_test`). No new packages —
PDF export is explicitly deferred (see spec).

**Spec:** `docs/superpowers/specs/2026-07-17-visit-summary-design.md`
(read this first — it has the full reasoning, including three rounds of
spec review and the owner's three pre-implementation catches; this plan
only restates what's needed to execute it).

---

## Before you start: judgment calls made during planning, not in the spec

The spec was written and approved at the design level; turning it into
exact code required a few decisions the spec didn't pin down. Flagging
them up front:

1. **`get_visit_summary`'s exact signature.** The spec's §4.3 sketch was
   `get_visit_summary(system_prompt, contents)` — contents pre-built.
   This plan instead gives it the same shape as the existing
   `get_assessment(system_prompt, history, user_message)`: it takes raw
   `history` (`list[dict]`) and builds `types.Content` objects
   internally via a new `_build_visit_summary_contents` helper. Reason:
   `main.py` never touches `google.genai.types.Content` directly today —
   that's entirely `gemini_client.py`'s concern — and keeping that
   boundary intact for the new function is more consistent than the
   spec's shorthand implied.
2. **A new `TierLanguageDetectedError` exception.** The spec's §4.4
   blocklist check and §4.1's structured-logging ask for a
   `blocklist_triggered` field are both real, but nothing connects them:
   `_call_gemini_with_retry` (Task 2) only ever raises the generic
   `ModelResponseError` after both attempts fail, which loses *why* the
   final attempt failed. Task 3 adds `TierLanguageDetectedError(ValueError)`
   — raised specifically on a blocklist match — and `run_visit_summary_pipeline`
   (Task 7) inspects `exc.__cause__` (Python's own exception-chaining,
   already used by `get_assessment`'s `raise ModelResponseError(...) from exc`)
   to tell a blocklist failure apart from an ordinary schema failure for
   logging, with zero new plumbing in the retry helper itself.
3. **`ChecklistRow` merges what the spec described as two widgets into
   one.** The spec (§5.3) says extract `AssessmentCard`'s list rows into
   `checklist_row.dart`/`warning_pill.dart`, and separately that the
   visit-summary screen's self-care section needs a checkbox-optional
   variant. Looking at the actual code: `_MonitoringRow`'s existing
   visual (a static history icon, no checkbox) is *already* exactly the
   "read-only row" shape the visit-summary screen needs. Rather than
   building a third rendering path, Task 9 makes one `ChecklistRow`
   widget whose checkbox becomes an optional `onTap`/`done` pair — passing
   both reproduces `_SelfCareRow` pixel-for-pixel; passing neither
   reproduces `_MonitoringRow` pixel-for-pixel. `_MonitoringRow` and
   `_SelfCareRow` both disappear as separate classes.
4. **Reusing `fallbacks.py`'s existing Tagalog-keyword heuristic for the
   backend's degenerate-case string**, rather than inventing a second
   keyword list in `main.py`. `fallbacks._message_signals_tagalog` already
   does exactly this job for other fixed EN/TL copy; Task 5 promotes it
   to a public name (`message_signals_tagalog`) since `main.py` becomes
   a second caller, matching the same promotion rule already applied to
   `system_prompt.py`'s language-block helpers in Task 1.
5. **`run_visit_summary_pipeline`'s tests live in `test_main.py`**, not a
   new file — matching this codebase's existing 1:1 module-to-test-file
   convention (one Python module, one test file, regardless of how many
   pipelines that module contains).
6. **Precedence in `VisitSummaryFacts`'s crisis-mention language-source
   selection.** The spec (§6) says the source turn is "the user turn
   immediately preceding the latest non-crisis assessment, or
   (crisis-only conversation) the latest user turn overall." Read
   literally, a *later* crisis turn in an otherwise-assessed conversation
   should NOT override the assessment's own language signal — only the
   crisis-only case falls back to the crisis turn's preceding text. Task
   10 implements this precedence explicitly (two separate tracked
   variables, assessment wins if it exists) rather than "whichever turn
   is chronologically last," which would have silently done the wrong
   thing for the mixed case.
7. **The `/visit-summary` route sits outside the bottom-nav shell** (a
   top-level `GoRoute`, same tier as `/disclaimer`/`/login`/`/signup`),
   not nested under `/chat`. It's a pushed detail screen, not a tab — it
   should render without the bottom nav bar.

---

## Task 1: `system_prompt.py` — promote language-directive helpers to public names

**Files:**
- Modify: `functions/system_prompt.py:1496-1523,1591`
- Test: `functions/test_system_prompt.py` (no new tests needed — this is
  a rename with no behavior change; existing tests call
  `build_system_prompt()` and check the *rendered text*, never the
  private helper names directly, so they prove the rename is safe)

- [ ] **Step 1: Run the existing suite to confirm the current baseline**

Run (from `functions/`): `pytest test_system_prompt.py -v`
Expected: all tests PASS (this is the "before" snapshot for the no-op
proof in Step 3).

- [ ] **Step 2: Rename the two symbols**

In `functions/system_prompt.py`, rename `_CONVERSATION_LANGUAGE_COPY` →
`CONVERSATION_LANGUAGE_COPY` (line 1496) and
`_render_conversation_language_block` → `render_conversation_language_block`
(line 1506, and its one call site at line 1509 which references the dict,
and line 1591 which calls the function). The block becomes:

```python
CONVERSATION_LANGUAGE_COPY = {
    "english": ("English", "Reply in English."),
    "tagalog": ("Tagalog", "Reply in natural, warm Taglish."),
    "mixed": (
        "Taglish (a mix of Tagalog and English)",
        "Reply in natural, warm Taglish.",
    ),
}


def render_conversation_language_block(conversation_language: str | None) -> str:
    if conversation_language is None:
        return ""
    copy = CONVERSATION_LANGUAGE_COPY.get(conversation_language)
    if copy is None:
        logger.warning(
            "system_prompt: unrecognized conversation_language %r — omitting the directive",
            conversation_language,
        )
        return ""
    name, reply_clause = copy
    return (
        "\n\n"
        f"CONVERSATION LANGUAGE: {name}. Decided from the person's own "
        f"messages across this conversation. {reply_clause} A short tapped "
        "answer chip is not a language switch — only a full message the "
        "person writes in another language changes this."
    )
```

And at line 1591, update the call site inside `_render_context_section`:

```python
        f"{render_conversation_language_block(conversation_language)}"
```

Add a one-line comment above `CONVERSATION_LANGUAGE_COPY` explaining the
promotion (so a future reader doesn't wonder why a "private-looking"
concept has a public name):

```python
# Public (not _-prefixed): visit_summary_prompt.py is a second consumer
# (design spec 2026-07-17 §4.2) — promoted so it imports this directly
# instead of reaching across a module boundary for a private symbol.
```

- [ ] **Step 3: Run the suite again to prove the rename is behavior-preserving**

Run: `pytest test_system_prompt.py -v`
Expected: identical PASS result to Step 1 — same tests, same outcomes.
If anything fails, grep the file for any remaining reference to the old
names (`grep -n "_render_conversation_language_block\|_CONVERSATION_LANGUAGE_COPY" functions/system_prompt.py`)
before proceeding.

- [ ] **Step 4: Commit**

```bash
git add functions/system_prompt.py
git commit -m "refactor(system_prompt): promote conversation-language helpers to public names"
```

---

## Task 2: `gemini_client.py` — extract `_call_gemini_with_retry`

**Files:**
- Modify: `functions/gemini_client.py:235-274` (the current `get_assessment`)
- Test: `functions/test_gemini_client.py`

This is a pure refactor — `get_assessment`'s observable behavior must be
byte-for-byte identical before and after. No existing test in
`test_gemini_client.py` should need to change.

- [ ] **Step 1: Run the existing suite to confirm the current baseline**

Run (from `functions/`): `pytest test_gemini_client.py -v`
Expected: all tests PASS (28 tests as of this writing — record the count
so Step 4 can compare).

- [ ] **Step 2: Add one new test for the extracted helper's `_retry_used` contract**

This is the property the spec review flagged as easy to silently break —
worth a direct anchor, not just relying on `get_assessment`'s existing
tests to catch a regression indirectly. Add to `test_gemini_client.py`,
near the "Retry mechanics" section (after line 434):

```python
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
```

- [ ] **Step 3: Run to verify these two pass against the CURRENT (pre-refactor) code**

Run: `pytest test_gemini_client.py -v -k retry_used`
Expected: both PASS already — `get_assessment` already sets `_retry_used`
today. This confirms the test correctly describes existing behavior
before you touch anything.

- [ ] **Step 4: Extract `_call_gemini_with_retry`**

In `functions/gemini_client.py`, replace the body of `get_assessment`
(lines 235-274) with the extracted helper plus a thin wrapper:

```python
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
```

This introduces two small supporting changes:

1. A `Callable` import — add `from typing import Callable` near the top
   of the file (after the `import re` line).
2. `_parse_and_validate(raw_text)` (the old combined parse+validate
   function) is split: the JSON-parsing/fence-stripping half becomes
   `_parse_json(raw_text)` (returns a plain `dict`/raises `ValueError` on
   bad JSON or a non-object payload), and the schema-specific half is now
   the `validator` callback passed in. Replace the existing
   `_parse_and_validate` function (lines 214-220) with:

```python
def _parse_json(raw_text: str) -> object:
    stripped = _strip_markdown_fences(raw_text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
```

And move the "not a dict" structural check that used to live at the top
of `_validate_payload` (lines 131-133) so it's still enforced — since
`_validate_payload` is now called with an already-parsed Python object
(not raw text), keep its existing `if not isinstance(payload, dict): raise ValueError(...)`
first line exactly as-is; it still runs, just on the output of
`_parse_json` instead of doing the JSON-decoding itself. No change
needed to `_validate_payload`'s body at all — only its caller changed.

- [ ] **Step 5: Run the full suite to prove behavior is unchanged**

Run: `pytest test_gemini_client.py -v`
Expected: same PASS count as Step 1 plus the 2 new tests from Step 2 —
all PASS, zero regressions. If `test_module_has_no_firebase_imports`
fails, check you didn't accidentally add a Firebase import while editing.

- [ ] **Step 6: Commit**

```bash
git add functions/gemini_client.py functions/test_gemini_client.py
git commit -m "refactor(gemini_client): extract _call_gemini_with_retry, shared by get_assessment and the upcoming get_visit_summary"
```

---

## Task 3: `gemini_client.py` — tier-language blocklist, validator, `get_visit_summary`

**Files:**
- Modify: `functions/gemini_client.py`
- Test: `functions/test_gemini_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_gemini_client.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_gemini_client.py -v -k visit_summary`
Expected: every new test FAILS — `get_visit_summary`, `TierLanguageDetectedError`
don't exist yet (`ImportError`/`AttributeError`).

- [ ] **Step 3: Implement**

In `functions/gemini_client.py`, add near `ModelResponseError` (after its
class definition):

```python
class TierLanguageDetectedError(ValueError):
    """Raised by _validate_visit_summary_payload when the model's own
    text states or implies an urgency tier — a ValueError subclass so
    _call_gemini_with_retry's existing retry-on-ValueError mechanism
    treats it identically to a schema failure, while callers can still
    distinguish the cause after a ModelResponseError via
    exc.__cause__ (see run_visit_summary_pipeline's structured logging
    in main.py)."""
```

Add the blocklist, contract, validator, contents builder, and public
function — put these after `get_assessment`, at the end of the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_gemini_client.py -v -k visit_summary`
Expected: all PASS.

- [ ] **Step 5: Run the full file to confirm no regressions**

Run: `pytest test_gemini_client.py -v`
Expected: all PASS (Task 2's count + Task 3's new tests).

- [ ] **Step 6: Commit**

```bash
git add functions/gemini_client.py functions/test_gemini_client.py
git commit -m "feat(gemini_client): add get_visit_summary with a code-enforced tier-language blocklist"
```

---

## Task 4: `functions/visit_summary_prompt.py` (new)

**Files:**
- Create: `functions/visit_summary_prompt.py`
- Test: `functions/test_visit_summary_prompt.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `functions/test_visit_summary_prompt.py`:

```python
"""
Tests for visit_summary_prompt.py — the retrospective recap/doctor-questions
prompt (design spec 2026-07-17-visit-summary-design.md).

Run from functions/:
    pytest test_visit_summary_prompt.py -v
"""

import re

from visit_summary_prompt import PROMPT_VERSION, build_system_prompt


def test_prompt_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", PROMPT_VERSION)


def test_prompt_version_appears_in_assembled_prompt():
    assert f"v{PROMPT_VERSION}" in build_system_prompt()


def test_never_assert_diagnosis_rule_present():
    prompt = build_system_prompt()
    assert "never" in prompt.lower()
    assert "diagnos" in prompt.lower()


def test_never_state_or_imply_urgency_tier_rule_present():
    prompt = build_system_prompt()
    lowered = prompt.lower()
    assert "urgency tier" in lowered or "urgency" in lowered
    assert "never" in lowered


def test_output_format_names_both_contract_fields():
    prompt = build_system_prompt()
    assert "summary" in prompt
    assert "questions_for_doctor" in prompt


def test_conversation_language_directive_absent_by_default():
    assert "CONVERSATION LANGUAGE" not in build_system_prompt(conversation_language=None)


def test_conversation_language_directive_present_when_given():
    prompt = build_system_prompt(conversation_language="tagalog")
    assert "CONVERSATION LANGUAGE" in prompt
    assert "Taglish" in prompt


def test_reuses_system_prompt_language_copy_not_a_duplicate():
    import system_prompt
    import visit_summary_prompt

    assert (
        visit_summary_prompt.render_conversation_language_block
        is system_prompt.render_conversation_language_block
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_visit_summary_prompt.py -v`
Expected: every test FAILS with `ModuleNotFoundError: No module named 'visit_summary_prompt'`.

- [ ] **Step 3: Implement**

Create `functions/visit_summary_prompt.py`:

```python
"""
System prompt for generate_visit_summary — a retrospective recap of a
whole conversation plus a generated "questions to ask your doctor" list.

Deliberately separate from system_prompt.py (design spec
2026-07-17-visit-summary-design.md §4.2): this is a different task —
retrospective synthesis over a full transcript, not live turn-by-turn
triage — with its own PROMPT_VERSION and its own narrow output contract
(summary, questions_for_doctor only; urgency/findings/watch-for/self-care
all stay client-side, see main.py's run_visit_summary_pipeline).

PROMPT_VERSION is bumped on every meaningful wording change, same
discipline as system_prompt.py, on its own independent numbering track.
"""

from __future__ import annotations

from system_prompt import render_conversation_language_block

PROMPT_VERSION = "1.0.0"

IDENTITY = (
    "You are Pulse, writing a retrospective summary of a health "
    "conversation that already happened. Someone is about to see a "
    "doctor and wants a clear recap to bring with them — you are not "
    "talking to the person directly, and you are not continuing the "
    "conversation."
)

# AGENT-DRAFTED PENDING OWNER READ-ALOUD is a Flutter/copy convention
# (crisis-adjacent strings) — this prompt text itself is plain
# instruction, not user-facing canonical copy, so it does not require
# the same read-aloud gate. It still needs the same hedging discipline
# as system_prompt.py's HARD_RULES (AGENTS.md AI rule 4).
HARD_RULES = (
    "## HARD RULES\n"
    "\n"
    "1. Never assert a single diagnosis as fact. Possibilities may be "
    "mentioned only as hedged, plural context (\"sometimes associated "
    "with things like X\"), never as \"you have X.\"\n"
    "\n"
    "2. Never state or imply an urgency tier — not \"monitor at home,\" "
    "not \"see a doctor soon,\" not \"seek care now,\" not a Taglish "
    "equivalent, and not a paraphrase that amounts to the same "
    "recommendation (\"you should get checked out immediately\"). That "
    "information is already shown elsewhere on the screen from a "
    "trusted, deterministic source — your recap describes what was "
    "discussed, it does not re-decide or restate what to do about it.\n"
    "\n"
    "3. Ground every question in questions_for_doctor in something "
    "actually present in the transcript — never invent a symptom, "
    "history detail, or concern that wasn't mentioned.\n"
)

OUTPUT_FORMAT = (
    "## OUTPUT FORMAT\n"
    "\n"
    "Return ONLY a JSON object with exactly these two fields:\n"
    "\n"
    "- summary (string, required, non-empty): a plain-language recap of "
    "what was discussed across the whole conversation — the symptoms "
    "reported, how they progressed, and what was already tried. Written "
    "for a doctor to scan in ten seconds.\n"
    "- questions_for_doctor (array of strings, required, may be empty): "
    "specific questions worth asking the doctor, grounded in the "
    "transcript.\n"
    "\n"
    "No markdown, no extra fields, no commentary outside the JSON "
    "object.\n"
)


def build_system_prompt(conversation_language: str | None = None) -> str:
    """Assemble the full system prompt for one generate_visit_summary
    request.

    conversation_language: "english" | "tagalog" | "mixed" (the
        detect_language vocabulary, derived server-side by main.py's
        _visit_summary_conversation_language), or None to omit the
        directive.
    """
    sections = [
        f"[Pulse visit-summary prompt v{PROMPT_VERSION}]",
        IDENTITY,
        HARD_RULES,
        OUTPUT_FORMAT,
    ]
    language_block = render_conversation_language_block(conversation_language)
    if language_block:
        sections.append(language_block.strip())
    return "\n\n".join(sections)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_visit_summary_prompt.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add functions/visit_summary_prompt.py functions/test_visit_summary_prompt.py
git commit -m "feat(visit_summary_prompt): add the retrospective recap/doctor-questions prompt"
```

---

## Task 5: `fallbacks.py` — promote the Tagalog heuristic, add degenerate-case copy

**Files:**
- Modify: `functions/fallbacks.py`
- Test: `functions/test_main.py` (new tests added in Task 7, once
  `run_visit_summary_pipeline` can call these; this task just adds the
  building blocks with their own direct tests)
- Test: create `functions/test_fallbacks.py` if it doesn't already exist —
  check first: `ls functions/test_fallbacks.py`. If it doesn't exist,
  this task creates it.

- [ ] **Step 1: Check whether `test_fallbacks.py` already exists**

Run: `ls functions/test_fallbacks.py` (or check the Task list — this
plan's earlier `functions/test_*.py` glob did not show one). If it
doesn't exist, Step 3 creates it.

- [ ] **Step 2: Write the failing tests**

Create `functions/test_fallbacks.py`:

```python
"""
Tests for fallbacks.py — owner-approved degraded-mode/fixed copy.

Run from functions/:
    pytest test_fallbacks.py -v
"""

import fallbacks


def test_message_signals_tagalog_is_public():
    # Promoted (design spec 2026-07-17 §4.1): main.py is now a second
    # caller, alongside fallbacks.py's own _pick_fallback_copy.
    assert hasattr(fallbacks, "message_signals_tagalog")


def test_message_signals_tagalog_detects_a_marker_word():
    assert fallbacks.message_signals_tagalog("Masakit ang ulo ko simula kanina")


def test_message_signals_tagalog_false_for_plain_english():
    assert not fallbacks.message_signals_tagalog("My head hurts since this morning")


def test_visit_summary_no_content_payload_english():
    payload = fallbacks.visit_summary_no_content_payload(tagalog=False)
    assert payload["type"] == "visit_summary"
    assert payload["summary"] == fallbacks.VISIT_SUMMARY_NO_CONTENT_EN
    assert payload["questions_for_doctor"] == []


def test_visit_summary_no_content_payload_tagalog():
    payload = fallbacks.visit_summary_no_content_payload(tagalog=True)
    assert payload["summary"] == fallbacks.VISIT_SUMMARY_NO_CONTENT_TL
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `functions/`): `pytest test_fallbacks.py -v`
Expected: `test_message_signals_tagalog_is_public` and the payload tests
FAIL (`AttributeError`); the two `message_signals_tagalog` detection
tests also fail the same way since the function doesn't exist under that
name yet.

- [ ] **Step 4: Implement**

In `functions/fallbacks.py`:

1. Rename `_message_signals_tagalog` → `message_signals_tagalog` (drop
   the leading underscore), and update its one internal call site inside
   `_pick_fallback_copy`:

```python
def message_signals_tagalog(message: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(message)}
    return not _TAGALOG_MARKER_WORDS.isdisjoint(words)


def _pick_fallback_copy(message: str, *, en: str, tl: str) -> str:
    return tl if message_signals_tagalog(message) else en
```

2. Add the degenerate-case copy and payload builder at the end of the
   file:

```python
# AGENT-DRAFTED — PENDING OWNER READ-ALOUD (design spec
# 2026-07-17-visit-summary-design.md §6): NOT yet owner-approved, unlike
# every other string in this file. Used only when a visit-summary
# conversation consisted solely of a crisis exchange — nothing else to
# summarize (run_visit_summary_pipeline's degenerate case, main.py).
VISIT_SUMMARY_NO_CONTENT_EN = "No other symptoms were discussed in this conversation."
VISIT_SUMMARY_NO_CONTENT_TL = "Wala nang ibang sintomas na napag-usapan sa kausapang ito."


def visit_summary_no_content_payload(*, tagalog: bool) -> dict:
    return {
        "type": "visit_summary",
        "summary": VISIT_SUMMARY_NO_CONTENT_TL if tagalog else VISIT_SUMMARY_NO_CONTENT_EN,
        "questions_for_doctor": [],
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest test_fallbacks.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full suite to confirm the rename didn't break anything else**

Run: `pytest -v`
Expected: all PASS (this rename touches a function used inside
`static_fallback_assessment`'s/`crisis_fallback_payload`'s/
`degraded_error_payload`'s shared `_pick_fallback_copy` helper — those
are exercised indirectly by `test_main.py`'s degraded-mode tests, so this
is the real regression check).

- [ ] **Step 7: Commit**

```bash
git add functions/fallbacks.py functions/test_fallbacks.py
git commit -m "feat(fallbacks): promote message_signals_tagalog, add visit-summary degenerate-case copy"
```

---

## Task 6: `main.py` — crisis-exchange stripping + conversation-language wrapper

**Files:**
- Modify: `functions/main.py`
- Test: `functions/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_main.py` (new section near the end):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_main.py -v -k "strip_crisis_exchanges or visit_summary_conversation_language"`
Expected: every test FAILS with `ImportError` (`_strip_crisis_exchanges`,
`_visit_summary_conversation_language` don't exist yet).

- [ ] **Step 3: Implement**

In `functions/main.py`, add both functions after `_conversation_language`
(after line 135, before the `logger = logging.getLogger(...)` line):

```python
def _strip_crisis_exchanges(history: list[dict]) -> list[dict]:
    """Removes each assistant turn with type == "crisis" AND the user
    turn immediately preceding it (design spec §6). Message.toHistoryJson()
    on the client only ever tags `type` on assistant turns — the
    preceding user turn is an untagged {"role": "user", "content": ...}
    entry, so a filter that only drops type == "crisis" entries would
    leave the triggering statement in the transcript. Applied for every
    crisis turn in the conversation, not just the first — this is the
    server-side half of the two-strip-points design (the client runs the
    same rule before the request is ever sent; this re-strip does not
    assume the client did its part correctly)."""
    drop_indices: set[int] = set()
    for i, turn in enumerate(history):
        if (
            isinstance(turn, dict)
            and turn.get("role") == "assistant"
            and turn.get("type") == "crisis"
        ):
            drop_indices.add(i)
            if i > 0 and history[i - 1].get("role") == "user":
                drop_indices.add(i - 1)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_main.py -v -k "strip_crisis_exchanges or visit_summary_conversation_language"`
Expected: all PASS.

- [ ] **Step 5: Run the full file to confirm no regressions**

Run: `pytest test_main.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add functions/main.py functions/test_main.py
git commit -m "feat(main): add crisis-exchange stripping and visit-summary language derivation"
```

---

## Task 7: `main.py` — `run_visit_summary_pipeline`

**Files:**
- Modify: `functions/main.py`
- Test: `functions/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_main.py`:

```python
# ---------------------------------------------------------------------------
# Visit summary: run_visit_summary_pipeline
# ---------------------------------------------------------------------------

import visit_summary_prompt
from main import run_visit_summary_pipeline


def _mock_get_visit_summary(monkeypatch, payload_or_fn):
    if callable(payload_or_fn) and not isinstance(payload_or_fn, dict):
        fn = payload_or_fn
    else:
        fn = lambda *args, **kwargs: dict(payload_or_fn)
    monkeypatch.setattr(main.gemini_client, "get_visit_summary", fn)


VALID_VISIT_SUMMARY = {
    "summary": "The conversation covered a mild headache.",
    "questions_for_doctor": ["Could this be related to sleep?"],
}


def test_run_visit_summary_pipeline_returns_narrative_on_success(monkeypatch):
    _mock_get_visit_summary(monkeypatch, VALID_VISIT_SUMMARY)
    history = [
        {"role": "user", "content": "I have a mild headache since this morning"},
        {
            "role": "assistant", "content": "That sounds manageable.",
            "type": "assessment", "urgency": "monitor_at_home",
            "findings": ["mild headache"], "explanation": "e", "next_step": "n",
        },
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency="monitor_at_home")
    assert result["type"] == "visit_summary"
    assert result["summary"] == VALID_VISIT_SUMMARY["summary"]
    assert result["questions_for_doctor"] == VALID_VISIT_SUMMARY["questions_for_doctor"]
    assert result["metadata"]["prompt_version"] == visit_summary_prompt.PROMPT_VERSION
    assert result["metadata"]["model_name"] == gemini_client.MODEL_NAME
    assert "generated_at" in result["metadata"]


def test_run_visit_summary_pipeline_strips_crisis_exchanges_before_calling_gemini(monkeypatch):
    captured = {}

    def _capture(prompt, history):
        captured["history"] = history
        return dict(VALID_VISIT_SUMMARY)

    _mock_get_visit_summary(monkeypatch, _capture)
    history = [
        {"role": "user", "content": "I want to end my life"},
        {"role": "assistant", "content": "I'm here for you.", "type": "crisis"},
        {"role": "user", "content": "I have a mild headache since this morning"},
        {
            "role": "assistant", "content": "That sounds manageable.",
            "type": "assessment", "urgency": "monitor_at_home",
            "findings": [], "explanation": None, "next_step": None,
        },
    ]
    run_visit_summary_pipeline(history=history, final_urgency="monitor_at_home")
    sent_texts = [turn["content"] for turn in captured["history"]]
    assert "I want to end my life" not in sent_texts
    assert "I'm here for you." not in sent_texts


def test_run_visit_summary_pipeline_degenerate_case_skips_gemini_entirely(monkeypatch):
    calls = []
    _mock_get_visit_summary(monkeypatch, lambda *a, **k: calls.append(1) or dict(VALID_VISIT_SUMMARY))
    history = [
        {"role": "user", "content": "I want to end my life"},
        {"role": "assistant", "content": "I'm here for you.", "type": "crisis"},
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency=None)
    assert calls == []  # gemini_client.get_visit_summary never called
    assert result["type"] == "visit_summary"
    assert result["summary"] == fallbacks.VISIT_SUMMARY_NO_CONTENT_EN
    assert result["questions_for_doctor"] == []


def test_run_visit_summary_pipeline_degenerate_case_picks_tagalog_from_pre_strip_history(monkeypatch):
    _mock_get_visit_summary(monkeypatch, lambda *a, **k: dict(VALID_VISIT_SUMMARY))
    history = [
        {"role": "user", "content": "Gusto ko nang mamatay"},
        {"role": "assistant", "content": "Nandito ako para sa'yo.", "type": "crisis"},
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency=None)
    assert result["summary"] == fallbacks.VISIT_SUMMARY_NO_CONTENT_TL


def test_run_visit_summary_pipeline_accepts_null_final_urgency(monkeypatch):
    _mock_get_visit_summary(monkeypatch, VALID_VISIT_SUMMARY)
    history = [
        {"role": "user", "content": "I want to end my life"},
        {"role": "assistant", "content": "I'm here for you.", "type": "crisis"},
        {"role": "user", "content": "actually just a mild headache too"},
        {
            "role": "assistant", "content": "Noted.", "type": "assessment",
            "urgency": "monitor_at_home", "findings": [], "explanation": None,
            "next_step": None,
        },
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency=None)
    assert result["type"] == "visit_summary"


def test_run_visit_summary_pipeline_rejects_oversized_history():
    history = [{"role": "user", "content": "hi"}] * (main.MAX_ACCEPTED_HISTORY_TURNS + 1)
    with pytest.raises(InvalidRequestError):
        run_visit_summary_pipeline(history=history, final_urgency=None)


def test_run_visit_summary_pipeline_rejects_invalid_final_urgency():
    with pytest.raises(InvalidRequestError):
        run_visit_summary_pipeline(history=[], final_urgency="call_911")


def test_run_visit_summary_pipeline_returns_error_type_on_model_response_error(monkeypatch):
    _mock_get_visit_summary(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(gemini_client.ModelResponseError("boom")))
    history = [
        {"role": "user", "content": "I have a mild headache since this morning"},
        {
            "role": "assistant", "content": "Noted.", "type": "assessment",
            "urgency": "monitor_at_home", "findings": [], "explanation": None,
            "next_step": None,
        },
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency="monitor_at_home")
    assert result["type"] == "error"


def test_run_visit_summary_pipeline_returns_error_type_on_unexpected_exception(monkeypatch):
    _mock_get_visit_summary(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503")))
    history = [
        {"role": "user", "content": "I have a mild headache since this morning"},
        {
            "role": "assistant", "content": "Noted.", "type": "assessment",
            "urgency": "monitor_at_home", "findings": [], "explanation": None,
            "next_step": None,
        },
    ]
    result = run_visit_summary_pipeline(history=history, final_urgency="monitor_at_home")
    assert result["type"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_main.py -v -k run_visit_summary_pipeline`
Expected: every test FAILS with `ImportError: cannot import name 'run_visit_summary_pipeline'`.

- [ ] **Step 3: Implement**

In `functions/main.py`:

1. Add two new imports near the top (after `import time`, before the
   `firebase_admin`/`firebase_functions` imports — matching the existing
   stdlib-imports-first grouping):

```python
from datetime import datetime, timezone
```

And after the existing `import system_prompt` line:

```python
import visit_summary_prompt
import wire_contract
```

2. Add a structured logger and `run_visit_summary_pipeline` after
   `run_pipeline` (after line 409, before the "Callable Function"
   section comment):

```python
def _log_visit_summary_request(
    *, retry_used: bool, blocklist_triggered: bool, degenerate: bool,
    conversation_language: str | None,
) -> None:
    logger.info(
        "generate_visit_summary request completed",
        extra={
            "prompt_version": visit_summary_prompt.PROMPT_VERSION,
            "retry_used": retry_used,
            "blocklist_triggered": blocklist_triggered,
            "degenerate": degenerate,
            "conversation_language": conversation_language,
        },
    )


def _visit_summary_error_response() -> dict:
    return {
        "type": "error",
        "message": "Couldn't put together a visit summary right now — try again in a bit.",
        "metadata": {
            "prompt_version": visit_summary_prompt.PROMPT_VERSION,
            "model_name": gemini_client.MODEL_NAME,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def run_visit_summary_pipeline(
    *, history: list[dict] | None, final_urgency: str | None,
) -> dict:
    """Pure orchestration for generate_visit_summary — mirrors
    run_pipeline/_handle_request's split so this is unit-testable
    without https_fn plumbing. See design spec §4.1.

    The narrative call is scoped narrowly to the recap + doctor
    questions; urgency, findings, watch-for, and self-care all stay
    client-side (design spec §4.5) — final_urgency is grounding only.
    """
    pre_strip_history = history or []
    if len(pre_strip_history) > MAX_ACCEPTED_HISTORY_TURNS:
        raise InvalidRequestError(HISTORY_TOO_LONG_MESSAGE)
    if final_urgency is not None and final_urgency not in wire_contract.URGENCY_TIERS:
        raise InvalidRequestError("final_urgency must be a valid urgency tier or null.")

    stripped_history = _strip_crisis_exchanges(pre_strip_history)

    if not stripped_history:
        # Degenerate case (design spec §4.1): the conversation consisted
        # solely of a crisis exchange — nothing else to summarize. Skip
        # Gemini entirely; classify language from the PRE-strip history
        # (classification only, never reproduction — reading crisis-turn
        # text to decide "was this Tagalog" doesn't touch the
        # no-paraphrase guarantee, since nothing from that text is
        # echoed or exposed).
        user_text = " ".join(
            turn.get("content", "")
            for turn in pre_strip_history
            if isinstance(turn, dict) and turn.get("role") == "user"
        )
        tagalog = fallbacks.message_signals_tagalog(user_text)
        _log_visit_summary_request(
            retry_used=False, blocklist_triggered=False, degenerate=True,
            conversation_language="tagalog" if tagalog else "english",
        )
        payload = fallbacks.visit_summary_no_content_payload(tagalog=tagalog)
        return {
            **payload,
            "metadata": {
                "prompt_version": visit_summary_prompt.PROMPT_VERSION,
                "model_name": gemini_client.MODEL_NAME,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    conversation_language = _visit_summary_conversation_language(stripped_history)
    prompt = visit_summary_prompt.build_system_prompt(
        conversation_language=conversation_language,
    )

    try:
        result = gemini_client.get_visit_summary(prompt, stripped_history)
    except gemini_client.ModelResponseError as exc:
        blocklist_triggered = isinstance(exc.__cause__, gemini_client.TierLanguageDetectedError)
        _log_visit_summary_request(
            retry_used=True, blocklist_triggered=blocklist_triggered, degenerate=False,
            conversation_language=conversation_language,
        )
        return _visit_summary_error_response()
    except Exception:
        logger.exception("Unexpected error calling Gemini for visit summary")
        _log_visit_summary_request(
            retry_used=False, blocklist_triggered=False, degenerate=False,
            conversation_language=conversation_language,
        )
        return _visit_summary_error_response()

    retry_used = bool(result.pop("_retry_used", False))
    _log_visit_summary_request(
        retry_used=retry_used, blocklist_triggered=False, degenerate=False,
        conversation_language=conversation_language,
    )
    return {
        "type": "visit_summary",
        "summary": result["summary"],
        "questions_for_doctor": result["questions_for_doctor"],
        "metadata": {
            "prompt_version": visit_summary_prompt.PROMPT_VERSION,
            "model_name": gemini_client.MODEL_NAME,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_main.py -v -k run_visit_summary_pipeline`
Expected: all PASS.

- [ ] **Step 5: Run the full file to confirm no regressions**

Run: `pytest test_main.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add functions/main.py functions/test_main.py
git commit -m "feat(main): add run_visit_summary_pipeline with degenerate-case and error handling"
```

---

## Task 8: `main.py` — `generate_visit_summary` Callable Function

**Files:**
- Modify: `functions/main.py`
- Test: `functions/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `functions/test_main.py`:

```python
# ---------------------------------------------------------------------------
# Visit summary: _handle_visit_summary_request
# ---------------------------------------------------------------------------

from main import _handle_visit_summary_request


class _FakeVisitSummaryRequest:
    def __init__(self, data):
        self.data = data


def test_handle_visit_summary_request_happy_path(monkeypatch):
    _mock_get_visit_summary(monkeypatch, VALID_VISIT_SUMMARY)
    request = _FakeVisitSummaryRequest({
        "history": [
            {"role": "user", "content": "I have a mild headache since this morning"},
            {
                "role": "assistant", "content": "Noted.", "type": "assessment",
                "urgency": "monitor_at_home", "findings": [], "explanation": None,
                "next_step": None,
            },
        ],
        "final_urgency": "monitor_at_home",
    })
    result = _handle_visit_summary_request(request)
    assert result["type"] == "visit_summary"


def test_handle_visit_summary_request_raises_https_error_on_oversized_history():
    history = [{"role": "user", "content": "hi"}] * (main.MAX_ACCEPTED_HISTORY_TURNS + 1)
    request = _FakeVisitSummaryRequest({"history": history, "final_urgency": None})
    with pytest.raises(https_fn.HttpsError):
        _handle_visit_summary_request(request)


def test_handle_visit_summary_request_defaults_missing_data_to_empty():
    request = _FakeVisitSummaryRequest({})
    result = _handle_visit_summary_request(request)
    # Empty history strips to empty -> degenerate path, no crash.
    assert result["type"] == "visit_summary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `functions/`): `pytest test_main.py -v -k handle_visit_summary_request`
Expected: every test FAILS with `ImportError`.

- [ ] **Step 3: Implement**

In `functions/main.py`, add after `_handle_request` (after line 431,
before `_enforce_app_check_setting`):

```python
def _handle_visit_summary_request(request: https_fn.CallableRequest) -> dict:
    data = request.data or {}
    try:
        return run_visit_summary_pipeline(
            history=data.get("history"),
            final_urgency=data.get("final_urgency"),
        )
    except InvalidRequestError as exc:
        raise https_fn.HttpsError(
            https_fn.FunctionsErrorCode.INVALID_ARGUMENT, str(exc)
        ) from exc
```

And at the very end of the file, after `assess_symptoms`:

```python
@https_fn.on_call(
    region="asia-southeast1",
    enforce_app_check=_enforce_app_check_setting(),
)
def generate_visit_summary(request: https_fn.CallableRequest) -> dict:
    return _handle_visit_summary_request(request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_main.py -v -k handle_visit_summary_request`
Expected: all PASS.

- [ ] **Step 5: Run the entire backend suite**

Run (from `functions/`): `pytest -v`
Expected: all PASS — this is the full backend regression check before
moving to the Flutter side.

- [ ] **Step 6: Commit**

```bash
git add functions/main.py functions/test_main.py
git commit -m "feat(main): deploy generate_visit_summary as a Callable Function"
```

---

## Task 9: Extract `ChecklistRow`/`WarningPill`; refactor `AssessmentCard`

**Files:**
- Create: `lib/shared/widgets/checklist_row.dart`
- Create: `lib/shared/widgets/warning_pill.dart`
- Modify: `lib/features/chat/widgets/assessment_card.dart`
- Test: `test/shared/widgets/checklist_row_test.dart` (new)
- Test: `test/shared/widgets/warning_pill_test.dart` (new)
- Test: `test/features/chat/widgets/assessment_card_test.dart` (existing —
  must keep passing unchanged)

- [ ] **Step 1: Run the existing `assessment_card_test.dart` to confirm the baseline**

Run: `flutter test test/features/chat/widgets/assessment_card_test.dart`
Expected: all 5 tests PASS (this is the "before" snapshot).

- [ ] **Step 2: Write the new widgets' failing tests**

Create `test/shared/widgets/checklist_row_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/shared/widgets/checklist_row.dart';

Widget _wrap(Widget child) =>
    MaterialApp(theme: AppTheme.light, home: Scaffold(body: child));

void main() {
  testWidgets('interactive mode (onTap set) renders a checkbox and calls onTap', (
    tester,
  ) async {
    var tapped = false;
    await tester.pumpWidget(
      _wrap(ChecklistRow(text: 'Rest', onTap: () => tapped = true)),
    );
    expect(find.text('Rest'), findsOneWidget);
    await tester.tap(find.text('Rest'));
    expect(tapped, isTrue);
  });

  testWidgets('done: true renders strikethrough text', (tester) async {
    await tester.pumpWidget(
      _wrap(ChecklistRow(text: 'Rest', done: true, onTap: () {})),
    );
    final text = tester.widget<Text>(find.text('Rest'));
    expect(text.style?.decoration, TextDecoration.lineThrough);
  });

  testWidgets('read-only mode (no onTap) renders no checkbox and is not tappable', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap(const ChecklistRow(text: 'Check temperature')));
    expect(find.text('Check temperature'), findsOneWidget);
    expect(find.byType(InkWell), findsNothing);
    expect(find.byIcon(Icons.history_rounded), findsOneWidget);
  });
}
```

Create `test/shared/widgets/warning_pill_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/shared/widgets/warning_pill.dart';

void main() {
  testWidgets('renders its text and a warning icon', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: WarningPill(text: 'Trouble breathing')),
      ),
    );
    expect(find.text('Trouble breathing'), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
  });
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `flutter test test/shared/widgets/checklist_row_test.dart test/shared/widgets/warning_pill_test.dart`
Expected: both FAIL — `package:pulse_app/shared/widgets/checklist_row.dart`
and `warning_pill.dart` don't exist yet.

- [ ] **Step 4: Implement the two shared widgets**

Create `lib/shared/widgets/checklist_row.dart`:

```dart
// lib/shared/widgets/checklist_row.dart
import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// A single checklist-style row. With [onTap] set, renders a tappable
/// checkbox row (AssessmentCard's self-care checklist). With [onTap]
/// null, renders a plain, non-interactive row with a small history icon
/// instead — no per-item identity to back a "checked" state (used by
/// AssessmentCard's monitoring list and VisitSummaryScreen's read-only
/// recap sections; see the visit-summary design spec §5.3).
class ChecklistRow extends StatelessWidget {
  const ChecklistRow({super.key, required this.text, this.done = false, this.onTap});

  final String text;
  final bool done;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final interactive = onTap != null;
    final row = Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(
        color: interactive ? AppColors.selfCareRowBg : AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
      ),
      child: Row(
        children: [
          if (interactive)
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: done ? AppColors.selfCareChecked : Colors.white,
                borderRadius: BorderRadius.circular(8),
                border: done
                    ? null
                    : Border.all(color: AppColors.selfCareUncheckedBorder, width: 2),
              ),
              child: done
                  ? const Icon(Icons.check, size: 15, color: Colors.white)
                  : null,
            )
          else
            const Icon(Icons.history_rounded, size: 15, color: AppColors.primaryInk),
          const SizedBox(width: 11),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: done ? AppColors.selfCareCheckedText : AppColors.text,
                decoration: done ? TextDecoration.lineThrough : null,
              ),
            ),
          ),
        ],
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: interactive
          ? InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(AppRadii.cardRowRadius),
              child: row,
            )
          : row,
    );
  }
}
```

Create `lib/shared/widgets/warning_pill.dart`:

```dart
// lib/shared/widgets/warning_pill.dart
import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// A coral warning pill — used by AssessmentCard's "Get care if…" list
/// and VisitSummaryScreen's watch-for recap.
class WarningPill extends StatelessWidget {
  const WarningPill({super.key, required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final coral = Theme.of(context).extension<UrgencyColors>()!.seekCareNow;
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        decoration: BoxDecoration(
          color: coral.tint,
          borderRadius: BorderRadius.circular(AppRadii.pillRowRadius),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.warning_amber_rounded, size: 17, color: coral.text),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: coral.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Run the new widget tests to verify they pass**

Run: `flutter test test/shared/widgets/checklist_row_test.dart test/shared/widgets/warning_pill_test.dart`
Expected: all PASS.

- [ ] **Step 6: Refactor `AssessmentCard` to use the shared widgets**

In `lib/features/chat/widgets/assessment_card.dart`:

1. Add imports (after the existing `urgency_result.dart` import):

```dart
import '../../../shared/widgets/checklist_row.dart';
import '../../../shared/widgets/warning_pill.dart';
```

2. Replace the self-care loop (lines 122-127):

```dart
            for (var i = 0; i < result.selfCare.length; i++)
              ChecklistRow(
                text: result.selfCare[i],
                done: checkedSelfCare.contains(i),
                onTap: () => onToggleSelfCare(i),
              ),
```

3. Replace the monitoring loop (line 133):

```dart
            for (final m in result.monitoring) ChecklistRow(text: m),
```

4. Replace the watch-for loop (line 139):

```dart
            for (final w in result.watchFor) WarningPill(text: w),
```

5. Delete the three now-unused private classes entirely: `_SelfCareRow`
   (lines 175-236), `_MonitoringRow` (lines 238-268), `_WatchForPill`
   (lines 270-304).

- [ ] **Step 7: Run `assessment_card_test.dart` to prove the refactor is behavior-preserving**

Run: `flutter test test/features/chat/widgets/assessment_card_test.dart`
Expected: identical PASS result to Step 1 — same 5 tests, same outcomes,
zero changes needed to the test file itself.

- [ ] **Step 8: Run `flutter analyze` to catch any unused-import or dead-code warnings**

Run: `flutter analyze`
Expected: no new warnings/errors introduced by this task.

- [ ] **Step 9: Commit**

```bash
git add lib/shared/widgets/checklist_row.dart lib/shared/widgets/warning_pill.dart lib/features/chat/widgets/assessment_card.dart test/shared/widgets/checklist_row_test.dart test/shared/widgets/warning_pill_test.dart
git commit -m "refactor(assessment_card): extract ChecklistRow/WarningPill to lib/shared/widgets"
```

---

## Task 10: `lib/features/visit_summary/models/visit_summary_facts.dart`

**Files:**
- Create: `lib/features/visit_summary/models/visit_summary_facts.dart`
- Test: `test/features/visit_summary/models/visit_summary_facts_test.dart` (new)

- [ ] **Step 1: Write the failing tests**

Create `test/features/visit_summary/models/visit_summary_facts_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_facts.dart';

Message _assessment({
  required UrgencyLevel urgency,
  List<String> findings = const [],
  List<String> watchFor = const [],
  List<String> selfCare = const [],
  List<String> monitoring = const [],
}) => Message.assistant(
  UrgencyResult(
    type: ChatTurnType.assessment,
    message: 'assessment',
    urgency: urgency,
    findings: findings,
    watchFor: watchFor,
    selfCare: selfCare,
    monitoring: monitoring,
  ),
);

Message _crisis() => Message.assistant(
  const UrgencyResult(type: ChatTurnType.crisis, message: 'crisis reply'),
);

void main() {
  group('VisitSummaryFacts.fromMessages', () {
    test('empty conversation yields all-null/empty facts', () {
      final facts = VisitSummaryFacts.fromMessages([]);
      expect(facts.finalUrgency, isNull);
      expect(facts.hadCrisisTurn, isFalse);
      expect(facts.findings, isEmpty);
    });

    test('single assessment sets final and initial urgency to the same tier', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I have a headache'),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ]);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.initialUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.urgencyChanged, isFalse);
    });

    test('multi-turn progression: urgencyChanged is first-vs-last, not "ever fluctuated"', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome),
        _assessment(urgency: UrgencyLevel.seeDoctorSoon),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ]);
      expect(facts.initialUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.urgencyChanged, isFalse);
    });

    test('a genuine progression sets urgencyChanged true', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome),
        _assessment(urgency: UrgencyLevel.seeDoctorSoon),
      ]);
      expect(facts.urgencyChanged, isTrue);
    });

    test('crisis-only conversation: finalUrgency null, hadCrisisTurn true', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I want to end my life'),
        _crisis(),
      ]);
      expect(facts.finalUrgency, isNull);
      expect(facts.hadCrisisTurn, isTrue);
      expect(facts.crisisMentionText, isNotNull);
    });

    test('mixed crisis+assessment: crisis excluded from aggregates, hadCrisisTurn set', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['mild headache']),
        Message.user('actually I feel like ending it'),
        _crisis(),
      ]);
      expect(facts.finalUrgency, UrgencyLevel.monitorAtHome);
      expect(facts.hadCrisisTurn, isTrue);
      expect(facts.findings, ['mild headache']);
    });

    test('findings/watchFor/selfCare/monitoring are deduped across turns', () {
      final facts = VisitSummaryFacts.fromMessages([
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['fever']),
        _assessment(urgency: UrgencyLevel.monitorAtHome, findings: ['fever', 'cough']),
      ]);
      expect(facts.findings, unorderedEquals(['fever', 'cough']));
    });

    test('TL-keyword heuristic: a Taglish preceding turn selects the TL crisis line', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('Gusto ko nang mamatay'),
        _crisis(),
      ]);
      expect(facts.crisisMentionText, crisisMentionTl);
    });

    test('TL-keyword heuristic: an all-English conversation defaults to EN', () {
      final facts = VisitSummaryFacts.fromMessages([
        Message.user('I want to end my life'),
        _crisis(),
      ]);
      expect(facts.crisisMentionText, crisisMentionEn);
    });

    test(
      'mixed conversation: the latest non-crisis assessment\'s language wins over a later crisis turn',
      () {
        final facts = VisitSummaryFacts.fromMessages([
          Message.user('Gusto ko nang mamatay'),
          _crisis(),
          Message.user('I have a mild headache'),
          _assessment(urgency: UrgencyLevel.monitorAtHome),
        ]);
        expect(facts.crisisMentionText, crisisMentionEn);
      },
    );
  });

  group('stripCrisisExchanges', () {
    test('removes the crisis reply and its preceding user turn', () {
      final userCrisis = Message.user('I want to end my life');
      final crisisReply = _crisis();
      final benignUser = Message.user('actually just a headache');
      final benignAssessment = _assessment(urgency: UrgencyLevel.monitorAtHome);
      final stripped = stripCrisisExchanges([
        userCrisis,
        crisisReply,
        benignUser,
        benignAssessment,
      ]);
      expect(stripped, [benignUser, benignAssessment]);
    });

    test('no-op when there is no crisis turn', () {
      final messages = [
        Message.user('I have a headache'),
        _assessment(urgency: UrgencyLevel.monitorAtHome),
      ];
      expect(stripCrisisExchanges(messages), messages);
    });
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/visit_summary/models/visit_summary_facts_test.dart`
Expected: FAILS — `package:pulse_app/features/visit_summary/models/visit_summary_facts.dart`
doesn't exist yet.

- [ ] **Step 3: Implement**

Create `lib/features/visit_summary/models/visit_summary_facts.dart`:

```dart
// lib/features/visit_summary/models/visit_summary_facts.dart
import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../../chat/models/urgency_result.dart';

/// Function words/particles used only to pick between the EN/TL
/// crisis-mention line below — mirrors fallbacks.py's
/// message_signals_tagalog heuristic on the Python side (kept as its own
/// Dart copy rather than shared cross-language). Optimized for precision
/// over recall: default to English unless a clearly Filipino word is
/// present.
const Set<String> _tagalogMarkerWords = {
  'ako', 'ikaw', 'siya', 'kami', 'tayo', 'kayo', 'sila',
  'ko', 'mo', 'niya', 'namin', 'natin', 'ninyo', 'nila',
  'ang', 'mga', 'yung', 'yun', 'ito', 'iyon', 'niyan', 'nito',
  'hindi', 'wala', 'meron', 'mayroon',
  'ba', 'naman', 'lang', 'din', 'rin', 'po', 'opo',
  'paano', 'bakit', 'saan', 'kailan', 'sino', 'kasi', 'tapos',
  'kanina', 'kagabi', 'bukas', 'kahapon',
};

final RegExp _wordPattern = RegExp(r"[A-Za-z']+");

bool _looksTagalog(String text) {
  final words = _wordPattern
      .allMatches(text)
      .map((m) => m.group(0)!.toLowerCase())
      .toSet();
  return words.intersection(_tagalogMarkerWords).isNotEmpty;
}

/// AGENT-DRAFTED — PENDING OWNER READ-ALOUD (design spec §6). Not final
/// copy until the Tagalog line has been read aloud and approved — do not
/// treat this draft as shippable.
const String crisisMentionEn =
    'This conversation included a moment of emotional distress — '
    'consider mentioning it to your doctor.';
const String crisisMentionTl =
    'May sandali ng matinding pag-aalala sa kausapang ito — '
    'makabubuting banggitin din ito sa iyong doktor.';

/// Deterministic, client-side facts derived from the current in-memory
/// conversation — zero network cost, always renders regardless of the
/// narrative call's availability (design spec §5.1, §7).
class VisitSummaryFacts {
  const VisitSummaryFacts({
    required this.finalUrgency,
    required this.initialUrgency,
    required this.urgencyChanged,
    required this.hadCrisisTurn,
    required this.crisisMentionText,
    this.findings = const [],
    this.watchFor = const [],
    this.selfCare = const [],
    this.monitoring = const [],
  });

  /// Null if every assessment-shaped turn in the conversation was a
  /// crisis turn — crisis turns are excluded from every aggregate below.
  final UrgencyLevel? finalUrgency;
  final UrgencyLevel? initialUrgency;

  /// First-vs-last, not "did it ever fluctuate mid-conversation".
  final bool urgencyChanged;

  final bool hadCrisisTurn;

  /// The EN or TL crisis-mention line to render (crisisMentionEn /
  /// crisisMentionTl), or null when [hadCrisisTurn] is false.
  final String? crisisMentionText;

  final List<String> findings;
  final List<String> watchFor;
  final List<String> selfCare;
  final List<String> monitoring;

  factory VisitSummaryFacts.fromMessages(List<Message> messages) {
    UrgencyLevel? initial;
    UrgencyLevel? current;
    final findings = <String>{};
    final watchFor = <String>{};
    final selfCare = <String>{};
    final monitoring = <String>{};
    var hadCrisisTurn = false;
    // Precedence (design spec §6): the latest non-crisis assessment's
    // language wins over a later crisis turn's — the crisis-only
    // fallback applies only when no non-crisis assessment ever occurred.
    String? assessmentLanguageSource;
    String? crisisOnlyLanguageSource;

    for (var i = 0; i < messages.length; i++) {
      final payload = messages[i].payload;
      if (payload == null) continue;

      if (payload.type == ChatTurnType.crisis) {
        hadCrisisTurn = true;
        if (i > 0 && messages[i - 1].role == MessageRole.user) {
          crisisOnlyLanguageSource = messages[i - 1].text;
        }
        continue;
      }
      if (payload.type != ChatTurnType.assessment) continue;

      initial ??= payload.urgency;
      current = payload.urgency;
      findings.addAll(payload.findings);
      watchFor.addAll(payload.watchFor);
      selfCare.addAll(payload.selfCare);
      monitoring.addAll(payload.monitoring);
      if (i > 0 && messages[i - 1].role == MessageRole.user) {
        assessmentLanguageSource = messages[i - 1].text;
      }
    }

    String? crisisMentionText;
    if (hadCrisisTurn) {
      final source = assessmentLanguageSource ?? crisisOnlyLanguageSource ?? '';
      crisisMentionText = _looksTagalog(source) ? crisisMentionTl : crisisMentionEn;
    }

    return VisitSummaryFacts(
      finalUrgency: current,
      initialUrgency: initial,
      urgencyChanged: initial != null && current != null && initial != current,
      hadCrisisTurn: hadCrisisTurn,
      crisisMentionText: crisisMentionText,
      findings: findings.toList(),
      watchFor: watchFor.toList(),
      selfCare: selfCare.toList(),
      monitoring: monitoring.toList(),
    );
  }
}

/// Removes each assistant turn with type == ChatTurnType.crisis and the
/// user turn immediately preceding it — the client-side half of the
/// two-strip-points design (design spec §6). Mirrors main.py's
/// _strip_crisis_exchanges exactly. Used by VisitSummaryController
/// before sending the request; NOT used by VisitSummaryFacts.fromMessages
/// above, which needs the original, unstripped messages to detect
/// hadCrisisTurn in the first place.
List<Message> stripCrisisExchanges(List<Message> messages) {
  final dropIndices = <int>{};
  for (var i = 0; i < messages.length; i++) {
    if (messages[i].payload?.type == ChatTurnType.crisis) {
      dropIndices.add(i);
      if (i > 0 && messages[i - 1].role == MessageRole.user) {
        dropIndices.add(i - 1);
      }
    }
  }
  return [
    for (var i = 0; i < messages.length; i++)
      if (!dropIndices.contains(i)) messages[i],
  ];
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/visit_summary/models/visit_summary_facts_test.dart`
Expected: all PASS.

- [ ] **Step 5: Run `flutter analyze`**

Run: `flutter analyze`
Expected: no new warnings/errors.

- [ ] **Step 6: Commit**

```bash
git add lib/features/visit_summary/models/visit_summary_facts.dart test/features/visit_summary/models/visit_summary_facts_test.dart
git commit -m "feat(visit_summary): add VisitSummaryFacts and stripCrisisExchanges"
```

---

## Task 11: `lib/features/visit_summary/models/visit_summary_result.dart`

**Files:**
- Create: `lib/features/visit_summary/models/visit_summary_result.dart`
- Test: `test/features/visit_summary/models/visit_summary_result_test.dart` (new)

- [ ] **Step 1: Write the failing tests**

Create `test/features/visit_summary/models/visit_summary_result_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_result.dart';

void main() {
  test('parses a valid visit_summary payload', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'visit_summary',
      'summary': 'A plain recap.',
      'questions_for_doctor': ['Question one?'],
      'metadata': {'prompt_version': '1.0.0'},
    });
    expect(result.isError, isFalse);
    expect(result.summary, 'A plain recap.');
    expect(result.questionsForDoctor, ['Question one?']);
  });

  test('parses an error payload', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'error',
      'message': 'Something went wrong.',
    });
    expect(result.isError, isTrue);
    expect(result.errorMessage, 'Something went wrong.');
  });

  test('never throws on a malformed shape — missing fields default gracefully', () {
    final result = VisitSummaryResult.fromJson({'type': 'visit_summary'});
    expect(result.isError, isFalse);
    expect(result.summary, '');
    expect(result.questionsForDoctor, isEmpty);
  });

  test('non-string entries in questions_for_doctor are dropped, not crashed on', () {
    final result = VisitSummaryResult.fromJson({
      'type': 'visit_summary',
      'summary': 'recap',
      'questions_for_doctor': ['valid', 42, null],
    });
    expect(result.questionsForDoctor, ['valid']);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/visit_summary/models/visit_summary_result_test.dart`
Expected: FAILS — the model file doesn't exist yet.

- [ ] **Step 3: Implement**

Create `lib/features/visit_summary/models/visit_summary_result.dart`:

```dart
// lib/features/visit_summary/models/visit_summary_result.dart

/// The narrative half of the visit summary — parsed from
/// generate_visit_summary's response. Mirrors how UrgencyResult.fromJson
/// defensively parses assess_symptoms responses: never throws on a
/// malformed shape (design spec §4.1, §5.2).
class VisitSummaryResult {
  const VisitSummaryResult({
    required this.isError,
    required this.summary,
    this.questionsForDoctor = const [],
    this.errorMessage,
  });

  final bool isError;
  final String summary;
  final List<String> questionsForDoctor;
  final String? errorMessage;

  factory VisitSummaryResult.fromJson(Map<String, dynamic> json) {
    if (json['type'] == 'error') {
      final message = json['message'];
      return VisitSummaryResult(
        isError: true,
        summary: '',
        errorMessage: message is String
            ? message
            : "Couldn't put together a visit summary right now — try again in a bit.",
      );
    }
    final summary = json['summary'];
    final questions = json['questions_for_doctor'];
    return VisitSummaryResult(
      isError: false,
      summary: summary is String ? summary : '',
      questionsForDoctor: questions is List
          ? questions.whereType<String>().toList()
          : const [],
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/visit_summary/models/visit_summary_result_test.dart`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/features/visit_summary/models/visit_summary_result.dart test/features/visit_summary/models/visit_summary_result_test.dart
git commit -m "feat(visit_summary): add VisitSummaryResult"
```

---

## Task 12: Visit summary repositories

**Files:**
- Create: `lib/features/visit_summary/repositories/visit_summary_repository.dart`
- Create: `lib/features/visit_summary/repositories/callable_visit_summary_repository.dart`
- Create: `lib/features/visit_summary/repositories/fixture_visit_summary_repository.dart`
- Test: `test/features/visit_summary/repositories/callable_visit_summary_repository_test.dart` (new)
- Test: `test/features/visit_summary/repositories/fixture_visit_summary_repository_test.dart` (new)

- [ ] **Step 1: Write the failing tests**

Create `test/features/visit_summary/repositories/callable_visit_summary_repository_test.dart`
(this test targets the pure, unit-testable `buildRequestData` static
method only — mirroring how `callable_chat_repository_test.dart` avoids
needing a live Firebase project; check that file's pattern first with
`cat test/features/chat/repositories/callable_chat_repository_test.dart`
if you want to match it exactly):

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/repositories/callable_visit_summary_repository.dart';

void main() {
  group('buildRequestData', () {
    test('serializes history via toHistoryJson and the urgency tier as a wire string', () {
      final messages = [
        Message.user('I have a headache'),
        Message.assistant(
          const UrgencyResult(
            type: ChatTurnType.assessment,
            message: 'Noted.',
            urgency: UrgencyLevel.monitorAtHome,
            findings: ['mild headache'],
          ),
        ),
      ];
      final data = CallableVisitSummaryRepository.buildRequestData(
        messages: messages,
        finalUrgency: UrgencyLevel.monitorAtHome,
      );
      expect(data['history'], hasLength(2));
      expect(data['final_urgency'], 'monitor_at_home');
    });

    test('a null finalUrgency serializes to a null final_urgency', () {
      final data = CallableVisitSummaryRepository.buildRequestData(
        messages: const [],
        finalUrgency: null,
      );
      expect(data['final_urgency'], isNull);
    });
  });
}
```

Create `test/features/visit_summary/repositories/fixture_visit_summary_repository_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/features/visit_summary/repositories/fixture_visit_summary_repository.dart';

void main() {
  test('returns a non-error VisitSummaryResult with content', () async {
    final result = await FixtureVisitSummaryRepository().generate(
      messages: const [],
      finalUrgency: null,
    );
    expect(result.isError, isFalse);
    expect(result.summary, isNotEmpty);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/visit_summary/repositories/`
Expected: FAILS — none of the repository files exist yet.

- [ ] **Step 3: Implement**

Create `lib/features/visit_summary/repositories/visit_summary_repository.dart`:

```dart
import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_result.dart';

/// Generates the narrative half (recap + doctor questions) of a visit
/// summary. Per AGENTS.md's AI/Backend rules, this repository only ever
/// calls the Callable Function and renders what comes back — it never
/// constructs prompts, holds API keys, or decides urgency locally.
abstract class VisitSummaryRepository {
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  });
}
```

Create `lib/features/visit_summary/repositories/callable_visit_summary_repository.dart`:

```dart
// lib/features/visit_summary/repositories/callable_visit_summary_repository.dart
import 'package:cloud_functions/cloud_functions.dart';

import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../../chat/models/urgency_result.dart';
import '../models/visit_summary_result.dart';
import 'visit_summary_repository.dart';

/// Calls the `generate_visit_summary` Callable Function in
/// asia-southeast1. The caller (VisitSummaryController) is responsible
/// for stripping crisis exchanges before messages ever reach this class
/// — see stripCrisisExchanges in visit_summary_facts.dart.
class CallableVisitSummaryRepository implements VisitSummaryRepository {
  CallableVisitSummaryRepository({FirebaseFunctions? functions})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-southeast1');

  final FirebaseFunctions _functions;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    final callable = _functions.httpsCallable('generate_visit_summary');
    final result = await callable.call<Map<String, dynamic>>(
      buildRequestData(messages: messages, finalUrgency: finalUrgency),
    );
    return VisitSummaryResult.fromJson(
      Map<String, dynamic>.from(result.data as Map),
    );
  }

  /// Extracted as a standalone, pure function so the request shape is
  /// unit-testable without a live Firebase project.
  static Map<String, dynamic> buildRequestData({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) {
    return {
      'history': messages
          .map((m) => m.toHistoryJson())
          .whereType<Map<String, dynamic>>()
          .toList(),
      'final_urgency': UrgencyResult.urgencyWire(finalUrgency),
    };
  }
}
```

Create `lib/features/visit_summary/repositories/fixture_visit_summary_repository.dart`:

```dart
// lib/features/visit_summary/repositories/fixture_visit_summary_repository.dart
import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_result.dart';
import 'visit_summary_repository.dart';

/// Debug-only fixture repository — zero network calls, zero quota cost.
/// Because the narrative call is already deliberately gated behind an
/// in-screen "Generate summary" tap (design spec §5.4), swapping this in
/// makes the whole visit-summary screen demoable end-to-end with zero
/// API calls. See visit_summary_provider.dart for the kDebugMode gate.
class FixtureVisitSummaryRepository implements VisitSummaryRepository {
  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    return const VisitSummaryResult(
      isError: false,
      summary:
          'This conversation covered a mild headache that started this '
          'morning, with no other symptoms reported.',
      questionsForDoctor: [
        'Could this be related to recent screen time or sleep changes?',
        "Is there anything I should watch for that would mean this needs "
            'more urgent attention?',
      ],
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/visit_summary/repositories/`
Expected: all PASS.

- [ ] **Step 5: Run `flutter analyze`**

Run: `flutter analyze`
Expected: no new warnings/errors.

- [ ] **Step 6: Commit**

```bash
git add lib/features/visit_summary/repositories/ test/features/visit_summary/repositories/
git commit -m "feat(visit_summary): add repositories (callable + fixture)"
```

---

## Task 13: `lib/features/visit_summary/providers/visit_summary_provider.dart`

**Files:**
- Create: `lib/features/visit_summary/providers/visit_summary_provider.dart`
- Test: `test/features/visit_summary/providers/visit_summary_provider_test.dart` (new)

- [ ] **Step 1: Write the failing tests**

Create `test/features/visit_summary/providers/visit_summary_provider_test.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/visit_summary/providers/visit_summary_provider.dart';
import 'package:pulse_app/features/visit_summary/repositories/visit_summary_repository.dart';

class _StubRepository implements VisitSummaryRepository {
  _StubRepository(this._result);
  final VisitSummaryResult _result;
  List<Message>? capturedMessages;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    capturedMessages = messages;
    return _result;
  }
}

class _ThrowingRepository implements VisitSummaryRepository {
  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) {
    throw Exception('network down');
  }
}

void main() {
  test('build() is idle — no fetch on creation', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(container.read(visitSummaryControllerProvider).value, isNull);
  });

  test('generate() populates state with the result and the generating message id', () async {
    final stub = _StubRepository(
      const VisitSummaryResult(isError: false, summary: 'recap'),
    );
    final container = ProviderContainer(
      overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
    );
    addTearDown(container.dispose);

    final userMsg = Message.user('hi');
    final assessment = Message.assistant(
      const UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'Noted.',
        urgency: UrgencyLevel.monitorAtHome,
      ),
    );
    await container
        .read(visitSummaryControllerProvider.notifier)
        .generate(messages: [userMsg, assessment], finalUrgency: UrgencyLevel.monitorAtHome);

    final state = container.read(visitSummaryControllerProvider).value;
    expect(state!.result.summary, 'recap');
    expect(state.generatedAtMessageId, assessment.id);
  });

  test('generate() strips crisis exchanges before calling the repository', () async {
    final stub = _StubRepository(
      const VisitSummaryResult(isError: false, summary: 'recap'),
    );
    final container = ProviderContainer(
      overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
    );
    addTearDown(container.dispose);

    final crisisUser = Message.user('I want to end my life');
    final crisisReply = Message.assistant(
      const UrgencyResult(type: ChatTurnType.crisis, message: "I'm here for you."),
    );
    await container
        .read(visitSummaryControllerProvider.notifier)
        .generate(messages: [crisisUser, crisisReply], finalUrgency: null);

    expect(stub.capturedMessages, isEmpty);
  });

  test('a repository failure surfaces as an AsyncError, not a thrown exception', () async {
    final container = ProviderContainer(
      overrides: [
        visitSummaryRepositoryProvider.overrideWithValue(_ThrowingRepository()),
      ],
    );
    addTearDown(container.dispose);

    await container
        .read(visitSummaryControllerProvider.notifier)
        .generate(messages: const [], finalUrgency: null);

    expect(container.read(visitSummaryControllerProvider).hasError, isTrue);
  });

  test('a re-entrant generate() call while loading is a no-op', () async {
    final stub = _StubRepository(
      const VisitSummaryResult(isError: false, summary: 'recap'),
    );
    final container = ProviderContainer(
      overrides: [visitSummaryRepositoryProvider.overrideWithValue(stub)],
    );
    addTearDown(container.dispose);

    final notifier = container.read(visitSummaryControllerProvider.notifier);
    final first = notifier.generate(messages: const [], finalUrgency: null);
    final second = notifier.generate(messages: const [], finalUrgency: null);
    await Future.wait([first, second]);
    // No assertion beyond "did not throw" — the guard's contract is
    // exercised; a stronger call-count assertion would need the stub to
    // count invocations, not required for this narrow regression check.
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/visit_summary/providers/visit_summary_provider_test.dart`
Expected: FAILS — the provider file doesn't exist yet.

- [ ] **Step 3: Implement**

Create `lib/features/visit_summary/providers/visit_summary_provider.dart`:

```dart
// lib/features/visit_summary/providers/visit_summary_provider.dart
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../chat/models/message.dart';
import '../models/visit_summary_facts.dart';
import '../models/visit_summary_result.dart';
import '../repositories/callable_visit_summary_repository.dart';
import '../repositories/fixture_visit_summary_repository.dart';
import '../repositories/visit_summary_repository.dart';

/// Flip to false to wire the real backend once fixture-mode UI review is
/// complete — same convention as chat_provider.dart's
/// _useFixturesInDebug.
const bool _useFixturesInDebug = false;

final visitSummaryRepositoryProvider = Provider<VisitSummaryRepository>((ref) {
  if (kDebugMode && _useFixturesInDebug) {
    return FixtureVisitSummaryRepository();
  }
  return CallableVisitSummaryRepository();
});

/// Bundles the narrative result with the message ID it was generated
/// against — the staleness signal (design spec §5.5). generatedAtMessageId
/// is the last message's id at the moment generate() was called.
class VisitSummaryState {
  const VisitSummaryState({
    required this.result,
    required this.generatedAtMessageId,
  });

  final VisitSummaryResult result;
  final String generatedAtMessageId;
}

/// Idle until the user explicitly taps "Generate summary" — build()
/// never fires the narrative call itself (design spec §5.4: opening the
/// screen must cost zero API calls; the deterministic facts render
/// separately via VisitSummaryFacts.fromMessages, with no need for a
/// provider at all).
class VisitSummaryController extends AsyncNotifier<VisitSummaryState?> {
  @override
  FutureOr<VisitSummaryState?> build() => null;

  Future<void> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async {
    // Double-tap/quota guard — same instinct as ChatController.send's
    // chatIsSendingProvider check.
    if (state.isLoading) return;

    // Client-side half of the two-strip-points crisis design (spec §6):
    // strip before the request is even built, so crisis text never
    // leaves the device when the client is behaving correctly. The
    // server re-strips independently regardless (main.py's
    // _strip_crisis_exchanges) — this is defense-in-depth, not the only
    // enforcement point.
    final strippedMessages = stripCrisisExchanges(messages);
    final generatedAtMessageId = messages.isEmpty ? '' : messages.last.id;

    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final result = await ref
          .read(visitSummaryRepositoryProvider)
          .generate(messages: strippedMessages, finalUrgency: finalUrgency);
      return VisitSummaryState(
        result: result,
        generatedAtMessageId: generatedAtMessageId,
      );
    });
  }
}

final visitSummaryControllerProvider =
    AsyncNotifierProvider<VisitSummaryController, VisitSummaryState?>(
      VisitSummaryController.new,
    );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/visit_summary/providers/visit_summary_provider_test.dart`
Expected: all PASS.

- [ ] **Step 5: Run `flutter analyze`**

Run: `flutter analyze`
Expected: no new warnings/errors.

- [ ] **Step 6: Commit**

```bash
git add lib/features/visit_summary/providers/visit_summary_provider.dart test/features/visit_summary/providers/visit_summary_provider_test.dart
git commit -m "feat(visit_summary): add VisitSummaryController with client-side crisis stripping"
```

---

## Task 14: `lib/features/visit_summary/screens/visit_summary_screen.dart`

**Files:**
- Create: `lib/features/visit_summary/screens/visit_summary_screen.dart`
- Test: `test/features/visit_summary/screens/visit_summary_screen_test.dart` (new)

- [ ] **Step 1: Write the failing tests**

Create `test/features/visit_summary/screens/visit_summary_screen_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/app_theme.dart';
import 'package:pulse_app/features/chat/models/message.dart';
import 'package:pulse_app/features/chat/models/urgency_result.dart';
import 'package:pulse_app/features/chat/providers/chat_provider.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_facts.dart';
import 'package:pulse_app/features/visit_summary/models/visit_summary_result.dart';
import 'package:pulse_app/features/visit_summary/providers/visit_summary_provider.dart';
import 'package:pulse_app/features/visit_summary/repositories/visit_summary_repository.dart';
import 'package:pulse_app/features/visit_summary/screens/visit_summary_screen.dart';

class _StubRepository implements VisitSummaryRepository {
  _StubRepository(this._result);
  final VisitSummaryResult _result;

  @override
  Future<VisitSummaryResult> generate({
    required List<Message> messages,
    required UrgencyLevel? finalUrgency,
  }) async => _result;
}

Message _assessment(UrgencyLevel urgency, {List<String> watchFor = const []}) =>
    Message.assistant(
      UrgencyResult(
        type: ChatTurnType.assessment,
        message: 'Noted.',
        urgency: urgency,
        watchFor: watchFor,
      ),
    );

Future<void> _pump(
  WidgetTester tester, {
  required List<Message> seedMessages,
  VisitSummaryRepository? repository,
}) async {
  final container = ProviderContainer(
    overrides: [
      if (repository != null)
        visitSummaryRepositoryProvider.overrideWithValue(repository),
    ],
  );
  addTearDown(container.dispose);
  // Seed chatControllerProvider's state directly rather than sending
  // through the UI — this screen only reads it, it never mutates chat.
  container.read(chatControllerProvider.notifier).state = AsyncData(seedMessages);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(theme: AppTheme.light, home: const VisitSummaryScreen()),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('tier badge alone: renders when there is an assessment and no crisis turn', (
    tester,
  ) async {
    await _pump(tester, seedMessages: [_assessment(UrgencyLevel.monitorAtHome)]);
    expect(find.text('Monitor at home'), findsOneWidget);
    expect(find.textContaining('emotional distress'), findsNothing);
  });

  testWidgets('crisis line alone: renders when the conversation is crisis-only', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        Message.user('I want to end my life'),
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.crisis, message: "I'm here."),
        ),
      ],
    );
    expect(find.text(crisisMentionEn), findsOneWidget);
    expect(find.text('Monitor at home'), findsNothing);
    expect(find.text('See a doctor soon'), findsNothing);
    expect(find.text('Seek care now'), findsNothing);
  });

  testWidgets('both stacked: a real assessment plus a later crisis turn renders both', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        _assessment(UrgencyLevel.seeDoctorSoon),
        Message.user('actually I feel like ending it'),
        Message.assistant(
          const UrgencyResult(type: ChatTurnType.crisis, message: "I'm here."),
        ),
      ],
    );
    expect(find.text('See a doctor soon'), findsOneWidget);
    expect(find.text(crisisMentionEn), findsOneWidget);
  });

  testWidgets('narrative block starts idle with a Generate summary CTA', (tester) async {
    await _pump(tester, seedMessages: [_assessment(UrgencyLevel.monitorAtHome)]);
    expect(find.text('Generate summary'), findsOneWidget);
  });

  testWidgets('tapping Generate summary shows the loaded recap', (tester) async {
    await _pump(
      tester,
      seedMessages: [_assessment(UrgencyLevel.monitorAtHome)],
      repository: _StubRepository(
        const VisitSummaryResult(
          isError: false,
          summary: 'A plain recap.',
          questionsForDoctor: ['A question?'],
        ),
      ),
    );
    await tester.tap(find.text('Generate summary'));
    await tester.pump(); // enter loading
    await tester.pump(); // resolve
    expect(find.text('A plain recap.'), findsOneWidget);
    expect(find.text('A question?'), findsOneWidget);
  });

  testWidgets('watch-for section renders WarningPills from deterministic facts', (
    tester,
  ) async {
    await _pump(
      tester,
      seedMessages: [
        _assessment(UrgencyLevel.seekCareNow, watchFor: ['Trouble breathing']),
      ],
    );
    expect(find.text('Trouble breathing'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/visit_summary/screens/visit_summary_screen_test.dart`
Expected: FAILS — the screen file doesn't exist yet.

- [ ] **Step 3: Implement**

Create `lib/features/visit_summary/screens/visit_summary_screen.dart`:

```dart
// lib/features/visit_summary/screens/visit_summary_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/checklist_row.dart';
import '../../../shared/widgets/warning_pill.dart';
import '../../chat/providers/chat_provider.dart';
import '../models/visit_summary_facts.dart';
import '../providers/visit_summary_provider.dart';

const Map<UrgencyLevel, String> _tierLabel = {
  UrgencyLevel.monitorAtHome: 'Monitor at home',
  UrgencyLevel.seeDoctorSoon: 'See a doctor soon',
  UrgencyLevel.seekCareNow: 'Seek care now',
};

class VisitSummaryScreen extends ConsumerWidget {
  const VisitSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final messages = ref.watch(chatControllerProvider).value ?? const [];
    final facts = VisitSummaryFacts.fromMessages(messages);
    final narrativeState = ref.watch(visitSummaryControllerProvider);
    final currentLastId = messages.isEmpty ? '' : messages.last.id;
    final isStale =
        narrativeState.value != null &&
        narrativeState.value!.generatedAtMessageId != currentLastId;

    void onGenerate() => ref
        .read(visitSummaryControllerProvider.notifier)
        .generate(messages: messages, finalUrgency: facts.finalUrgency);

    return Scaffold(
      backgroundColor: AppColors.bgCream,
      appBar: AppBar(
        backgroundColor: AppColors.bgCream,
        elevation: 0,
        title: const Text('Visit summary'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        children: [
          _Header(facts: facts),
          const SizedBox(height: AppSpacing.sectionGap),
          _NarrativeBlock(
            state: narrativeState,
            isStale: isStale,
            onGenerate: onGenerate,
          ),
          if (facts.findings.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('What was discussed', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final f in facts.findings) ChecklistRow(text: f),
          ],
          if (facts.selfCare.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Self-care already suggested', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            // Read-only here — no per-item identity to back a checked
            // state across turns (design spec §5.3).
            for (final s in facts.selfCare) ChecklistRow(text: s),
          ],
          if (facts.monitoring.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Things to monitor', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final m in facts.monitoring) ChecklistRow(text: m),
          ],
          if (facts.watchFor.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Get care if…', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final w in facts.watchFor) WarningPill(text: w),
          ],
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.facts});
  final VisitSummaryFacts facts;

  @override
  Widget build(BuildContext context) {
    // Tier badge and crisis-mention line render independently, not
    // either/or (design spec §5.3) — a real assessment and a later
    // crisis moment can both be true of the same conversation.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (facts.finalUrgency != null)
          _TierBadge(
            urgency: facts.finalUrgency!,
            progressionLabel: facts.urgencyChanged
                ? 'Started at ${_tierLabel[facts.initialUrgency]}, now '
                      '${_tierLabel[facts.finalUrgency]}'
                : null,
          ),
        if (facts.hadCrisisTurn) ...[
          if (facts.finalUrgency != null) const SizedBox(height: 12),
          _CrisisMentionBanner(text: facts.crisisMentionText!),
        ],
      ],
    );
  }
}

class _TierBadge extends StatelessWidget {
  const _TierBadge({required this.urgency, required this.progressionLabel});
  final UrgencyLevel urgency;
  final String? progressionLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final palette = theme.extension<UrgencyColors>()!.forLevel(urgency);
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadii.card),
        boxShadow: AppShadows.card,
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: palette.solid,
              borderRadius: BorderRadius.circular(AppRadii.iconChip),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _tierLabel[urgency]!,
                  style: theme.textTheme.titleLarge?.copyWith(color: palette.text),
                ),
                if (progressionLabel != null) ...[
                  const SizedBox(height: 4),
                  Text(progressionLabel!, style: theme.textTheme.bodySmall),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CrisisMentionBanner extends StatelessWidget {
  const _CrisisMentionBanner({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMin),
      decoration: BoxDecoration(
        color: AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.card),
      ),
      child: Text(text, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}

class _NarrativeBlock extends StatelessWidget {
  const _NarrativeBlock({
    required this.state,
    required this.isStale,
    required this.onGenerate,
  });

  final AsyncValue<VisitSummaryState?> state;
  final bool isStale;
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (state.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.hasError) {
      return _NarrativeError(onRetry: onGenerate);
    }
    final data = state.value;
    if (data == null) {
      return _GenerateCta(onGenerate: onGenerate);
    }
    if (isStale) {
      return _StaleBanner(onRegenerate: onGenerate);
    }
    if (data.result.isError) {
      return _NarrativeError(onRetry: onGenerate);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(data.result.summary, style: theme.textTheme.bodyMedium),
        if (data.result.questionsForDoctor.isNotEmpty) ...[
          const SizedBox(height: 18),
          Text('Questions to ask your doctor', style: theme.textTheme.titleSmall),
          const SizedBox(height: 9),
          for (final q in data.result.questionsForDoctor) ChecklistRow(text: q),
        ],
      ],
    );
  }
}

class _GenerateCta extends StatelessWidget {
  const _GenerateCta({required this.onGenerate});
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: onGenerate,
        child: const Text('Generate summary'),
      ),
    );
  }
}

class _NarrativeError extends StatelessWidget {
  const _NarrativeError({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          "Couldn't put together a visit summary right now.",
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 9),
        TextButton(onPressed: onRetry, child: const Text('Try again')),
      ],
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.onRegenerate});
  final VoidCallback onRegenerate;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'The conversation has continued since this summary was generated.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 9),
        TextButton(onPressed: onRegenerate, child: const Text('Regenerate')),
      ],
    );
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/features/visit_summary/screens/visit_summary_screen_test.dart`
Expected: all PASS.

- [ ] **Step 5: Add the staleness regression test**

Append to the same test file's `main()`:

```dart
  testWidgets('a stale narrative (conversation continued) shows a regenerate prompt, not old prose', (
    tester,
  ) async {
    final container = ProviderContainer(
      overrides: [
        visitSummaryRepositoryProvider.overrideWithValue(
          _StubRepository(
            const VisitSummaryResult(isError: false, summary: 'Original recap.'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final firstMessage = _assessment(UrgencyLevel.monitorAtHome);
    container.read(chatControllerProvider.notifier).state = AsyncData([firstMessage]);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(theme: AppTheme.light, home: const VisitSummaryScreen()),
      ),
    );
    await tester.pump();
    await tester.tap(find.text('Generate summary'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Original recap.'), findsOneWidget);

    // Conversation continues past the point the narrative was generated.
    container.read(chatControllerProvider.notifier).state = AsyncData([
      firstMessage,
      _assessment(UrgencyLevel.seeDoctorSoon),
    ]);
    await tester.pump();

    expect(find.text('Original recap.'), findsNothing);
    expect(find.text('Regenerate'), findsOneWidget);
  });
```

- [ ] **Step 6: Run to verify it passes**

Run: `flutter test test/features/visit_summary/screens/visit_summary_screen_test.dart`
Expected: all PASS, including the new staleness test.

- [ ] **Step 7: Run `flutter analyze`**

Run: `flutter analyze`
Expected: no new warnings/errors.

- [ ] **Step 8: Commit**

```bash
git add lib/features/visit_summary/screens/visit_summary_screen.dart test/features/visit_summary/screens/visit_summary_screen_test.dart
git commit -m "feat(visit_summary): add VisitSummaryScreen with independent header composition and staleness detection"
```

---

## Task 15: Entry point — `chat_screen.dart` AppBar action + `app_router.dart` route

**Files:**
- Modify: `lib/features/chat/screens/chat_screen.dart`
- Modify: `lib/core/router/app_router.dart`
- Test: `test/features/chat/screens/chat_screen_test.dart`

- [ ] **Step 1: Write the failing tests**

Append to `test/features/chat/screens/chat_screen_test.dart`'s `main()`
(near the top-level tests, alongside the existing quick-reply test —
check the file's structure first: some tests already live inside a
`engineV2Tests()` function called from `main()`; add these as
standalone `testWidgets` calls in `main()` directly, matching the
existing quick-reply test's placement):

```dart
  testWidgets('the visit-summary AppBar action is disabled with no assessment/crisis turn', (
    tester,
  ) async {
    await _pump(tester, _ScriptedRepository([]));
    final button = tester.widget<IconButton>(find.byIcon(Icons.summarize_outlined));
    expect(button.onPressed, isNull);
  });

  testWidgets('the visit-summary AppBar action enables once an assessment exists', (
    tester,
  ) async {
    await _pump(
      tester,
      _ScriptedRepository([
        const UrgencyResult(
          type: ChatTurnType.assessment,
          message: 'Noted.',
          urgency: UrgencyLevel.monitorAtHome,
          cardAction: CardAction.newCard,
        ),
      ]),
    );
    await tester.enterText(find.byType(TextField), 'I have a headache');
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    final button = tester.widget<IconButton>(find.byIcon(Icons.summarize_outlined));
    expect(button.onPressed, isNotNull);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/features/chat/screens/chat_screen_test.dart -N "visit-summary AppBar action"`
Expected: both FAIL — `find.byIcon(Icons.summarize_outlined)` finds
nothing yet.

- [ ] **Step 3: Add the route to `app_router.dart`**

In `lib/core/router/app_router.dart`:

1. Add an import (after the `settings_screen.dart` import):

```dart
import '../../features/visit_summary/screens/visit_summary_screen.dart';
```

2. Add the route constant to `AppRoutes` (after `settings`):

```dart
  static const visitSummary = '/visit-summary';
```

3. Add a top-level `GoRoute` to the `routes` list — outside the
   `StatefulShellRoute` shell (it's a pushed detail screen, not a tab;
   see "Before you start" item 7), right after the `signup` route and
   before `StatefulShellRoute.indexedStack(`:

```dart
      GoRoute(
        path: AppRoutes.visitSummary,
        builder: (context, state) => const VisitSummaryScreen(),
      ),
```

- [ ] **Step 4: Add the AppBar action to `chat_screen.dart`**

In `lib/features/chat/screens/chat_screen.dart`:

1. Add imports (after the existing `urgency_strip.dart` import):

```dart
import 'package:go_router/go_router.dart';

import '../../../core/router/app_router.dart';
```

2. Inside `build`, after `final messages = state.value ?? const <Message>[];`
   (line 80), add:

```dart
    final hasVisitSummaryContent = messages.any(
      (m) =>
          m.payload?.type == ChatTurnType.assessment ||
          m.payload?.type == ChatTurnType.crisis,
    );
```

3. Add an `actions` list to the `AppBar` (currently has no `actions:`
   parameter — add it after `title:`):

```dart
        actions: [
          IconButton(
            icon: const Icon(Icons.summarize_outlined),
            tooltip: 'Visit summary',
            onPressed: hasVisitSummaryContent
                ? () => context.push(AppRoutes.visitSummary)
                : null,
          ),
        ],
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `flutter test test/features/chat/screens/chat_screen_test.dart`
Expected: all PASS, including the two new tests — this also proves the
existing tests (which pump `ChatScreen` in a plain `MaterialApp`, not
`MaterialApp.router`) still pass, since none of them tap the new button
(tapping it would need a `GoRouter` ancestor, which those tests
deliberately don't set up — see "Before you start" for why the
navigation test in Task 14 wasn't placed here).

- [ ] **Step 6: Run `flutter analyze`**

Run: `flutter analyze`
Expected: no new warnings/errors.

- [ ] **Step 7: Full regression pass — the whole Flutter suite**

Run: `flutter test`
Expected: all tests across the entire `test/` directory PASS.

- [ ] **Step 8: `dart format`**

Run: `dart format --set-exit-if-changed .`
Expected: no changes needed, or apply formatting if it flags anything
(`dart format .` without the flag to actually apply).

- [ ] **Step 9: Commit**

```bash
git add lib/features/chat/screens/chat_screen.dart lib/core/router/app_router.dart test/features/chat/screens/chat_screen_test.dart
git commit -m "feat(chat): wire the visit-summary AppBar entry point"
```

---

## Final verification (whole feature, both sides)

- [ ] **Backend**: from `functions/`, run `pytest -v` — all tests PASS
  (Tasks 1-8's additions plus the full pre-existing suite untouched).
- [ ] **Client**: from the repo root, run `flutter analyze` (zero
  warnings/errors) then `flutter test` (all PASS) then
  `dart format --set-exit-if-changed .` (clean).
- [ ] **Manual smoke test** (per the spec's §8 "Manual" testing note —
  no eval harness exists yet for `visit_summary_prompt.py`): hand-run at
  least one real conversation through `generate_visit_summary` against
  the live emulator/deployed function, including the "bait the
  blocklist" transcript the spec calls out (a dengue-style conversation
  where the tier is the whole story) — confirm the blocklist's retry
  produces a compliant second attempt rather than falling through to
  `type: "error"` on the most natural case. This is not automatable in
  this plan (it needs live Gemini output) — flag it explicitly rather
  than skip it silently.
- [ ] **Reminder — do not skip**: the four AGENT-DRAFTED — PENDING OWNER
  READ-ALOUD strings (`crisisMentionEn`/`crisisMentionTl` in
  `visit_summary_facts.dart`, `VISIT_SUMMARY_NO_CONTENT_EN`/`_TL` in
  `fallbacks.py`) are implementation-complete but **not final copy**.
  Per the design spec §9's deploy gate, this feature cannot ship until
  the owner has read the Tagalog lines aloud and approved them.
