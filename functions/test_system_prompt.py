"""
Tests for system_prompt.py — structural invariants only.

These assert the assembled prompt's structure and contract text, and that
the few-shot example payloads obey the JSON schema Pulse's client renders.
They deliberately do NOT test model behavior — that isn't testable here.

Run from functions/:
    pytest test_system_prompt.py -v
"""

import json
import re
from pathlib import Path

import pytest

from system_prompt import FEW_SHOT_EXAMPLES, PROMPT_VERSION, build_system_prompt

VALID_URGENCIES = {"monitor_at_home", "see_doctor_soon", "seek_care_now"}

# Static sections first, all dynamic content last — the static prefix
# (~90% of the prompt) stays byte-identical across requests, which lets
# Gemini's implicit context caching reuse it.
SECTION_HEADERS = [
    "## 1. WHO YOU ARE",
    "## 2. HARD RULES",
    "## 3. THE THREE URGENCY TIERS",
    "## 4. HOW TO RUN THE CONVERSATION",
    "## 5. WORRY CALIBRATION",
    "## 6. OUTPUT FORMAT",
    "## 7. EXAMPLES",
    "## 8. WHAT YOU ARE NOT",
    "## 9. CONTEXT FOR THIS CONVERSATION",
]

SAMPLE_PROFILE = {
    "relationship": "child",
    "age": 4,
    "sex": "female",
    "conditions": ["asthma"],
    "medications": ["salbutamol inhaler"],
    "allergies": ["amoxicillin"],
}

SAMPLE_REGION = "Active dengue advisory for the user's province, issued this month."


def build(profile=None, worry_level=None, regional_context=None):
    return build_system_prompt(profile, worry_level, regional_context)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_prompt_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", PROMPT_VERSION)


def test_prompt_version_appears_in_assembled_prompt():
    assert f"v{PROMPT_VERSION}" in build()


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_all_sections_present_in_order():
    prompt = build()
    positions = [prompt.index(header) for header in SECTION_HEADERS]
    assert positions == sorted(positions)


@pytest.mark.parametrize(
    "field",
    [
        "type",
        "message",
        "quick_replies",
        "urgency",
        "explanation",
        "watch_for",
        "next_step",
        "possibilities_mentioned",
    ],
)
def test_json_contract_field_documented(field):
    assert f'"{field}"' in build()


def test_all_three_urgency_ids_present():
    prompt = build()
    for urgency_id in VALID_URGENCIES:
        assert urgency_id in prompt


def test_json_only_output_instruction_present():
    prompt = build().lower()
    assert "no markdown fences" in prompt
    assert "never add fields" in prompt


def test_crisis_type_documented_in_contract_and_hard_rules():
    prompt = build()
    assert '"crisis"' in prompt
    assert 'type "crisis"' in prompt  # hard rule 7 must route to it


def test_dynamic_blocks_come_after_all_static_sections():
    # Cache hygiene: everything request-specific must sit after the last
    # static section, so the static prefix is byte-identical across
    # requests and implicitly cacheable.
    prompt = build(SAMPLE_PROFILE, "scared", SAMPLE_REGION)
    static_end = prompt.index("## 8. WHAT YOU ARE NOT")
    # Full block labels, not bare "PERSON CONTEXT" — the identity section
    # legitimately forward-references that name in static text.
    assert prompt.index("PERSON CONTEXT (who this conversation is about):") > static_end
    assert prompt.index("REGIONAL HEALTH CONTEXT:") > static_end
    assert prompt.index("CURRENT WORRY LEVEL:") > static_end
    # And the injected values themselves must not leak before the boundary.
    assert prompt.index(SAMPLE_REGION) > static_end
    assert prompt.index("asthma") > static_end


# ---------------------------------------------------------------------------
# Language mirroring (1.3.3) — regional_context/profile must never anchor
# reply language; only the user's own most recent words do.
# ---------------------------------------------------------------------------

def test_language_hard_rule_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "MOST RECENT message" in flattened
    assert "do NOT demonstrate language choice" in flattened


def test_examples_deck_framing_precedes_first_example():
    flattened = re.sub(r"\s+", " ", build())
    framing = (
        "Mirror the USER's language per the language rule — never the "
        "examples' language."
    )
    assert framing in flattened
    assert flattened.index(framing) < flattened.index("Example 1")


def test_context_section_framing_precedes_dynamic_content():
    flattened = re.sub(r"\s+", " ", build(SAMPLE_PROFILE, "scared", SAMPLE_REGION))
    marker = "never a signal for which language to reply in"
    assert marker in flattened
    assert flattened.index(marker) < flattened.index(
        "PERSON CONTEXT (who this conversation is about):"
    )


def test_context_section_framing_is_static_across_requests():
    # The framing line must sit in the cacheable static prefix: identical
    # position regardless of what profile/worry/regional_context are passed.
    marker = "reply language is decided only by the LANGUAGE"
    flat_empty = re.sub(r"\s+", " ", build())
    flat_full = re.sub(r"\s+", " ", build(SAMPLE_PROFILE, "scared", SAMPLE_REGION))
    assert flat_empty.index(marker) == flat_full.index(marker)


def test_example_json_is_rendered_compact():
    # Examples are the bulk of the prompt; they must render without
    # pretty-print indentation.
    assert '{"type": "question", "message":' in build()


def test_validated_escalation_principle_present():
    prompt = build()
    flattened = re.sub(r"\s+", " ", prompt)
    assert "Validated escalation" in prompt
    # The limitation must be named plainly, not hidden behind vague caution.
    assert "conversation alone" in flattened
    # Scope guard: the principle applies to escalations, not every reply.
    assert (
        "monitor_at_home replies where you and the person agree stay short "
        "and confident" in flattened
    )


def test_possibilities_calibration_line_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "not caution; it is incompleteness" in flattened


def test_narrative_flow_handoff_rule_present():
    # 1.4.1: codifies the handoff pattern the two restitched examples below
    # model — a brief gesture to the structured field, never a dangling
    # reference that points at nothing.
    flattened = re.sub(r"\s+", " ", build())
    assert "hand off to it naturally" in flattened
    assert "never a sentence that points at nothing" in flattened


def test_hard_rule_6_states_substance_not_boilerplate():
    # 1.3.1: rule 6 demands honest substance about Pulse's limits, woven in
    # naturally — not a disclaimer formula the examples no longer model.
    flattened = re.sub(r"\s+", " ", build())
    assert "cannot examine" in flattened
    assert "a doctor's check" in flattened
    assert "boilerplate disclaimer" in flattened


def test_no_stray_owner_review_comments_remain():
    # The three agent-drafted messages from 1.3.0 were owner-approved in
    # 1.3.1; only the standing mental-health/clinical review flags remain.
    source = (Path(__file__).parent / "system_prompt.py").read_text(encoding="utf-8")
    assert "flagged for owner review" not in source
    assert "FLAGGED FOR MENTAL-HEALTH REVIEW" in source  # standing flag stays
    assert "FLAGGED FOR CLINICIAN REVIEW" in source      # standing flag stays


def test_voice_rule_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "text message to a friend" in flattened
    assert "No idioms, metaphors, or figurative phrases" in flattened


def test_crisis_mode_persistence_instructed():
    flattened = re.sub(r"\s+", " ", build())
    assert "enters crisis mode" in flattened
    assert 'every subsequent reply is type "crisis"' in flattened


def test_crisis_banned_minimizing_phrases_listed():
    flattened = re.sub(r"\s+", " ", build())
    assert '"at least"' in flattened
    assert '"kaya mo yan"' in flattened


# ---------------------------------------------------------------------------
# Dynamic injection: profile
# ---------------------------------------------------------------------------

def test_profile_fields_injected():
    prompt = build(profile=SAMPLE_PROFILE)
    assert "the user's child" in prompt
    assert "4 years old" in prompt
    assert "asthma" in prompt
    assert "salbutamol inhaler" in prompt
    assert "amoxicillin" in prompt


def test_no_profile_yields_explicit_placeholder():
    assert "No profile details were provided" in build()


def test_age_months_preferred_over_years_for_infants():
    prompt = build(profile={"age_months": 2, "age": 0})
    assert "2 months old" in prompt


# ---------------------------------------------------------------------------
# Malformed profile values — must fail closed, never crash. Regression
# coverage for a TypeError the eval harness's schema_and_resilience
# category found (evals/cases.py's schema_garbage_profile_does_not_crash):
# once red_flags.py's identical bug class was fixed, the exact same
# garbage profile still crashed here, in _render_profile_block's
# ', '.join(values) on a non-list "medications" value.
# ---------------------------------------------------------------------------

GARBAGE_PROFILE = {
    "relationship": "self",
    "age": "unknown",
    "conditions": "asthma",
    "medications": 123,
    "allergies": {"nuts": True},
}


def test_malformed_profile_matches_the_exact_eval_harness_garbage_case():
    prompt = build(profile=GARBAGE_PROFILE)
    assert "The user is describing their own symptoms." in prompt
    assert "Age: unknown years old" in prompt


def test_non_list_medications_is_omitted_not_crashed():
    prompt = build(profile={"medications": 123})
    assert "Medications:" not in prompt


def test_conditions_as_plain_string_is_omitted_not_crashed():
    # A bare string is technically iterable (chars), so silently joining
    # it would produce garbled output ("a, s, t, h, m, a") — must be
    # rejected as the wrong shape instead, same as a non-iterable value.
    prompt = build(profile={"conditions": "asthma"})
    assert "Ongoing conditions:" not in prompt


def test_allergies_list_with_non_string_items_is_omitted_not_crashed():
    prompt = build(profile={"allergies": [1, 2, 3]})
    assert "Allergies:" not in prompt


def test_relationship_wrong_type_falls_back_to_unspecified():
    prompt = build(profile={"relationship": 12345})
    assert "Relationship not specified" in prompt


def test_profile_argument_itself_not_a_dict_falls_back_to_no_profile():
    prompt = build(profile=["not", "a", "dict"])
    assert "No profile details were provided" in prompt


def test_well_formed_conditions_still_render_normally():
    # Confirms the fix didn't break the legitimate, well-typed path.
    prompt = build(profile={"conditions": ["asthma", "eczema"]})
    assert "Ongoing conditions: asthma, eczema" in prompt


# ---------------------------------------------------------------------------
# Dynamic injection: worry level
# ---------------------------------------------------------------------------

def test_worry_scared_injected():
    assert "CURRENT WORRY LEVEL: scared" in build(worry_level="scared")


def test_worry_just_checking_injected():
    assert "CURRENT WORRY LEVEL: just_checking" in build(worry_level="just_checking")


def test_worry_none_normalizes_to_unknown():
    assert "CURRENT WORRY LEVEL: unknown" in build()


def test_worry_unrecognized_value_normalizes_to_unknown():
    assert "CURRENT WORRY LEVEL: unknown" in build(worry_level="panicking!!")


def test_worry_must_not_change_tier_stated_explicitly():
    # Whitespace-normalized: the phrase may wrap across lines in the copy.
    flattened = re.sub(r"\s+", " ", build())
    assert "never change the urgency tier" in flattened


# ---------------------------------------------------------------------------
# Dynamic injection: regional context
# ---------------------------------------------------------------------------

def test_regional_context_injected():
    assert SAMPLE_REGION in build(regional_context=SAMPLE_REGION)


def test_no_regional_context_yields_explicit_placeholder():
    assert "No active regional advisories" in build()


# ---------------------------------------------------------------------------
# Forbidden content
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase",
    ["i diagnose", "i can diagnose", "as an ai", "just an ai", "language model"],
)
def test_forbidden_phrases_absent(phrase):
    prompt = build(SAMPLE_PROFILE, "scared", SAMPLE_REGION)
    assert phrase not in prompt.lower()


EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def test_no_emoji_anywhere():
    assert not EMOJI_RE.search(build(SAMPLE_PROFILE, "scared", SAMPLE_REGION))


def test_no_hotline_like_numbers_in_static_prompt():
    # The model must never carry hotline numbers (they go stale; the app
    # injects current ones). No 4+ digit run should exist in the static
    # prompt — regional_context is caller-supplied and exempt.
    assert not re.search(r"\d{4,}", build())


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

def _final_payload(example):
    return example["turns"][-1]["assistant"]


def test_exactly_five_examples():
    assert len(FEW_SHOT_EXAMPLES) == 5


REQUIRED_FIELDS = {
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


def test_every_example_payload_follows_the_flat_schema():
    # Flat schema: every field present in every payload, with null/[] when
    # inapplicable — so the Dart-side fromJson can be dumb and total.
    for example in FEW_SHOT_EXAMPLES:
        for turn in example["turns"]:
            payload = turn["assistant"]
            json.dumps(payload)  # must be JSON-serializable
            assert set(payload) == REQUIRED_FIELDS
            assert payload["type"] in {"question", "assessment", "crisis"}
            assert isinstance(payload["message"], str) and payload["message"]
            assert isinstance(payload["quick_replies"], list)
            assert isinstance(payload["watch_for"], list)
            assert isinstance(payload["possibilities_mentioned"], bool)
            assert isinstance(payload["self_care"], list)
            assert isinstance(payload["monitoring"], list)
            if payload["type"] == "question":
                assert 2 <= len(payload["quick_replies"]) <= 4
                assert all(isinstance(qr, str) and qr for qr in payload["quick_replies"])
                assert payload["watch_for"] == []
                assert payload["urgency"] is None
                assert payload["explanation"] is None
                assert payload["next_step"] is None
                assert payload["self_care"] == []
                assert payload["monitoring"] == []
                assert payload["encouragement"] is None
            elif payload["type"] == "assessment":
                assert payload["quick_replies"] == []
                assert payload["urgency"] in VALID_URGENCIES
                assert isinstance(payload["explanation"], str) and payload["explanation"]
                assert payload["watch_for"], "assessments must include watch_for signs"
                assert all(isinstance(w, str) and w for w in payload["watch_for"])
                assert isinstance(payload["next_step"], str) and payload["next_step"]
                assert all(isinstance(s, str) and s for s in payload["self_care"])
                assert all(isinstance(m, str) and m for m in payload["monitoring"])
                assert (
                    isinstance(payload["encouragement"], str) and payload["encouragement"]
                ), "assessments must include a non-empty encouragement"
            else:  # crisis — message only; no triage furniture
                assert payload["quick_replies"] == []
                assert payload["watch_for"] == []
                assert payload["urgency"] is None
                assert payload["explanation"] is None
                assert payload["next_step"] is None
                assert payload["self_care"] == []
                assert payload["monitoring"] == []
                assert payload["encouragement"] is None


def test_example_tier_outcomes():
    finals = [_final_payload(example) for example in FEW_SHOT_EXAMPLES]
    assert [payload["urgency"] for payload in finals] == [
        "see_doctor_soon",   # dengue-advisory case
        "monitor_at_home",   # mild sore throat — Pulse is not alarmist
        "monitor_at_home",   # Taglish caregiver child-fever case
        "seek_care_now",     # casual tone, red-thread symptoms
        None,                # crisis — no tier, no triage furniture
    ]


def test_dengue_example_mentions_possibilities_plurally():
    final = _final_payload(FEW_SHOT_EXAMPLES[0])
    assert final["possibilities_mentioned"] is True
    assert "dengue" in final["message"].lower()


def test_dengue_example_teaches_post_fever_window():
    # The counterintuitive dengue danger window is AFTER the fever breaks —
    # the canonical example must teach this. As of 1.3.0 the teaching lives
    # in the message body (approved Taglish copy), not the watch_for items.
    final = _final_payload(FEW_SHOT_EXAMPLES[0])
    assert "bumaba na yung lagnat" in final["message"]


def test_dengue_example_fields_use_approved_taglish_copy():
    # 1.3.1: explanation and next_step were owner-replaced to match the
    # conversation's register (they were English inside a Taglish exchange).
    final = _final_payload(FEW_SHOT_EXAMPLES[0])
    assert "kaya mas mabuting magpa-check" in final["explanation"]
    assert "blood test para malaman kung dengue" in final["next_step"]


def test_escalation_example_demonstrates_validated_escalation():
    # Example 4 is the canonical validated-escalation example: validate the
    # user's benign theory, name the real limitation, then let the tier land
    # as the conclusion. Anchored on stable substrings, not full sentences.
    final = _final_payload(FEW_SHOT_EXAMPLES[3])
    assert final["possibilities_mentioned"] is True
    message = final["message"]
    assert "puyat o migraine" in message                    # (a) validation
    assert "rare pero seryosong problema" in message        # (b) hedged plural
    assert "masisiguro sa chat lang" in message             # (b) named limitation
    assert "hindi ko masasabing puyat lang ito" in message  # kept mirror line
    # 1.3.1: explanation owner-replaced (old text used banned formal terms).
    assert "masisiguro sa chat lang — kaya ngayong araw" in final["explanation"]


def test_caregiver_example_is_taglish_with_chip_question():
    example = FEW_SHOT_EXAMPLES[2]
    assert "anak" in example["turns"][0]["user"]
    first = example["turns"][0]["assistant"]
    assert first["type"] == "question"
    assert 2 <= len(first["quick_replies"]) <= 4
    # 1.3.0: the question addresses the child by profile name, not "si baby".
    assert "si Mika" in first["message"]


def test_caregiver_assessment_uses_everyday_register():
    # 1.4.0: this care-advice line moved from "message" into "self_care"
    # (no-duplication rule) — it should no longer appear in the message.
    final = _final_payload(FEW_SHOT_EXAMPLES[2])
    assert any("naka-recommend sa box" in item for item in final["self_care"])
    assert "naka-recommend sa box" not in final["message"]


def test_caregiver_assessment_hands_off_to_self_care():
    # 1.4.1: restitched handoff line — the message gestures to self_care
    # instead of leaving a dangling reference to nothing.
    final = _final_payload(FEW_SHOT_EXAMPLES[2])
    assert "nilista ko sa baba" in final["message"]


def test_sore_throat_example_hands_off_to_self_care():
    # 1.4.1: restitched handoff line — same pattern as the Mika example,
    # in English.
    final = _final_payload(FEW_SHOT_EXAMPLES[1])
    assert "listed what helps below" in final["message"]


def test_crisis_example_shape_and_canonical_copy():
    example = FEW_SHOT_EXAMPLES[4]
    assert len(example["turns"]) == 1
    payload = example["turns"][0]["assistant"]
    assert set(payload) == REQUIRED_FIELDS
    assert payload["type"] == "crisis"
    assert payload["urgency"] is None
    assert payload["explanation"] is None
    assert payload["next_step"] is None
    assert payload["quick_replies"] == []
    assert payload["watch_for"] == []
    assert payload["possibilities_mentioned"] is False
    assert "Salamat at sinabi mo" in payload["message"]
    assert "hindi sila mawawala" in payload["message"]
    # The model must never carry numbers — the app injects them.
    assert not re.search(r"\d", payload["message"])


def test_profile_name_injected():
    assert "Name: Mika" in build(profile={"name": "Mika", "age": 4})


def test_examples_are_rendered_into_the_prompt():
    prompt = build()
    for example in FEW_SHOT_EXAMPLES:
        assert example["turns"][0]["user"][:40] in prompt
    assert '"type": "question"' in prompt
    assert '"type": "assessment"' in prompt
