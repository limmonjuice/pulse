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
    "## 3. TWO KINDS OF TURNS",
    "## 4. THE THREE URGENCY TIERS",
    "## 5. HOW TO RUN THE CONVERSATION",
    "## 6. WORRY CALIBRATION",
    "## 7. OUTPUT FORMAT",
    "## 8. EXAMPLES",
    "## 9. WHAT YOU ARE NOT",
    "## 10. CONTEXT FOR THIS CONVERSATION",
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
    static_end = prompt.index("## 9. WHAT YOU ARE NOT")
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


# ---------------------------------------------------------------------------
# Conversation-language directive (1.5.5) — server-derived (main.py's
# _conversation_language), stated per-request because live probes showed
# no prompt-side rule or example survives a terse chip tap's register.
# ---------------------------------------------------------------------------

def test_conversation_language_directive_absent_by_default():
    assert "CONVERSATION LANGUAGE:" not in build()


def test_conversation_language_directive_english():
    prompt = build_system_prompt(conversation_language="english")
    assert "CONVERSATION LANGUAGE: English." in prompt
    assert "Reply in English." in prompt


@pytest.mark.parametrize("value", ["tagalog", "mixed"])
def test_conversation_language_directive_tagalog_and_mixed_reply_taglish(value):
    prompt = build_system_prompt(conversation_language=value)
    assert "CONVERSATION LANGUAGE:" in prompt
    assert "Reply in natural, warm Taglish." in prompt


def test_conversation_language_directive_unrecognized_value_omitted():
    assert "CONVERSATION LANGUAGE:" not in build_system_prompt(
        conversation_language="klingon"
    )


def test_conversation_language_directive_sits_in_final_dynamic_section():
    # Request-specific content must stay after the static prefix — same
    # cache-hygiene rule the rest of section 9 follows.
    prompt = build_system_prompt(conversation_language="english")
    assert prompt.index("CONVERSATION LANGUAGE: English.") > prompt.index(
        "## 10. CONTEXT FOR THIS CONVERSATION"
    )


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


# ---------------------------------------------------------------------------
# Language recency counterweight (1.5.1, A1) — a forceful restatement of
# the mirroring rule as the LAST static words before the dynamic section,
# after the few-shot deck. Added when gemini-3.1-flash-lite began
# imitating the deck's dominant language instead of mirroring the user.
# ---------------------------------------------------------------------------

RECENCY_MARKER = "Final reminder, because it overrides everything above"


def test_language_recency_reminder_present():
    flattened = re.sub(r"\s+", " ", build())
    assert RECENCY_MARKER in flattened
    assert "English in means English out" in flattened


def test_language_recency_reminder_sits_after_deck_before_dynamic_section():
    prompt = build(SAMPLE_PROFILE, "scared", SAMPLE_REGION)
    reminder_pos = prompt.index(RECENCY_MARKER)
    # After the entire few-shot deck (the last example's final payload)...
    assert reminder_pos > prompt.index("watch list shows up before you're seen")
    # ...and after the remaining static sections...
    assert reminder_pos > prompt.index("## 9. WHAT YOU ARE NOT")
    assert reminder_pos > prompt.index("reply language is decided only by the LANGUAGE")
    # ...but before anything dynamic: the very end of the static prefix.
    assert reminder_pos < prompt.index("## 10. CONTEXT FOR THIS CONVERSATION")
    assert reminder_pos < prompt.index("PERSON CONTEXT (who this conversation is about):")


def test_language_recency_reminder_is_static_across_requests():
    # Cache hygiene: identical position whether or not dynamic context is
    # passed, so the block lives inside the cacheable static prefix.
    flat_empty = re.sub(r"\s+", " ", build())
    flat_full = re.sub(r"\s+", " ", build(SAMPLE_PROFILE, "scared", SAMPLE_REGION))
    assert flat_empty.index(RECENCY_MARKER) == flat_full.index(RECENCY_MARKER)


# ---------------------------------------------------------------------------
# Mirroring root-cause fixes (1.5.2) — probe-confirmed 2026-07-13. Two
# defects made 3.1-flash-lite answer English input in Tagalog: the
# IDENTITY register instruction was an unconditional "write Taglish"
# command (probe P1), and Example 1 answered a mostly-English opener in
# full Tagalog, teaching English-in -> Tagalog-out by template (probe P3).
# ---------------------------------------------------------------------------

def test_register_rule_is_conditional_on_user_language():
    flattened = re.sub(r"\s+", " ", build())
    # The register instruction must open by binding itself to the user's
    # language, and must carry an explicit English branch.
    assert "in whichever language the user wrote their most recent message" in flattened
    assert "When it is English, plain conversational English." in flattened
    # The old unconditional imperative must be gone.
    assert "actually text. Everyday Taglish:" not in flattened


def test_no_example_answers_english_input_in_tagalog():
    # Permanent deck invariant: no example may pair an English-detected
    # user turn with a non-English assistant message. Mixed/Taglish user
    # turns answered in Taglish are fine (that IS mirroring); an
    # English-reading user turn answered in Tagalog teaches the exact
    # regression probe P3 confirmed.
    import mirror_probes

    for i, example in enumerate(FEW_SHOT_EXAMPLES, 1):
        for t, turn in enumerate(example["turns"], 1):
            if mirror_probes.detect_language(turn["user"]) == "english":
                reply_lang = mirror_probes.detect_language(turn["assistant"]["message"])
                assert reply_lang == "english", (
                    f"Example {i} turn {t} answers an English user turn in "
                    f"{reply_lang!r} — this teaches English-in -> Tagalog-out"
                )


def test_progressive_transparency_exemplars_are_bilingual():
    flattened = re.sub(r"\s+", " ", build())
    assert "This doesn't look like an emergency, but I want to be sure" in flattened
    assert "Mukhang hindi ito emergency" in flattened
    assert "always in the user's own language" in flattened


def test_tell_the_staff_script_is_bilingual():
    flattened = re.sub(r"\s+", " ", build())
    assert "When you get there, tell the staff:" in flattened
    assert "Pagdating mo, sabihin mo:" in flattened


def test_english_dengue_example_carries_the_dengue_calibration():
    # 1.5.3/1.5.4: the deck's sole dengue example — English, single-turn
    # (duration already given), same tier, hedged plural possibilities,
    # and the post-fever danger-window teaching carried over from the
    # removed Taglish original.
    import mirror_probes

    twin = FEW_SHOT_EXAMPLES[5]
    assert len(twin["turns"]) == 1
    assert mirror_probes.detect_language(twin["turns"][0]["user"]) == "english"
    final = twin["turns"][0]["assistant"]
    assert final["type"] == "assessment"
    assert final["urgency"] == "see_doctor_soon"
    assert final["possibilities_mentioned"] is True
    assert "dengue" in final["message"].lower()
    assert "after the fever goes down" in final["message"]
    assert mirror_probes.detect_language(final["message"]) == "english"
    assert "AGENT-DRAFTED, PENDING OWNER READ-ALOUD (1.5.3" in (
        (Path(__file__).parent / "system_prompt.py").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Conversation posture (1.5.0) — flipped default, 3-question budget,
# priority order, exposure reasoning, progressive transparency.
# ---------------------------------------------------------------------------

def test_questioning_default_flip_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "would one more concrete answer" in flattened


def test_question_budget_is_three():
    flattened = re.sub(r"\s+", " ", build())
    assert "up to 3 clarifying questions" in flattened


def test_question_priority_order_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "duration, severity, and red-flag-adjacent symptoms outrank" in flattened


def test_exposure_reasoning_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "Exposure reasoning:" in flattened
    assert "floodwater" in flattened
    assert "mosquito bites" in flattened
    assert "animal bite" in flattened


def test_progressive_transparency_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "Progressive transparency:" in flattened
    assert "never answer questions into silence" in flattened


def test_possibilities_do_dont_contrast_present():
    # B3: the hedged-plural ceiling holds even at seek_care_now — a DO/DON'T
    # pair anchored on the spec's own leptospirosis example.
    flattened = re.sub(r"\s+", " ", build())
    assert 'pwedeng seryosong impeksyon, kasama yung tinatawag na leptospirosis' in flattened
    assert 'this is highly concerning for Leptospirosis, your timing fits' in flattened


def test_seek_care_now_enrichments_present():
    flattened = re.sub(r"\s+", " ", build())
    assert "Pagdating mo, sabihin mo:" in flattened
    assert "avoid ibuprofen" in flattened.lower()


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


def test_exactly_nine_examples():
    # 1.5.4: the Taglish dengue example was removed (owner decision — its
    # presence made English dengue-shaped openers mirror Tagalog; see the
    # note atop FEW_SHOT_EXAMPLES). 2.0.0 added three conversation-engine
    # examples: EN reassurance, TL anxious asking-why, testing reset.
    assert len(FEW_SHOT_EXAMPLES) == 9


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
    # v2.0.0 proposal fields (spec §5)
    "intents",
    "requires_clinical_reassessment",
    "change_type",
    "reassessment_reason",
    "proposed_card_action",
    "findings",
}


def test_every_example_payload_follows_the_flat_schema():
    # Flat schema: every field present in every payload, with null/[] when
    # inapplicable — so the Dart-side fromJson can be dumb and total.
    for example in FEW_SHOT_EXAMPLES:
        for turn in example["turns"]:
            payload = turn["assistant"]
            json.dumps(payload)  # must be JSON-serializable
            assert set(payload) == REQUIRED_FIELDS
            assert payload["type"] in {
                "question", "assessment", "crisis", "conversation",
            }
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
        "monitor_at_home",   # mild sore throat — Pulse is not alarmist
        "monitor_at_home",   # Taglish caregiver child-fever case
        "seek_care_now",     # casual tone, red-thread symptoms
        None,                # crisis — no tier, no triage furniture
        "see_doctor_soon",   # English cat-scratch exposure (1.5.1 rebalance)
        "see_doctor_soon",   # English dengue-advisory case (sole dengue example since 1.5.4)
        None,                # EN reassurance — final turn is a conversation turn
        None,                # TL anxious asking-why — final turn is a conversation turn
        None,                # testing reset — final turn is a conversation turn
    ]


def test_escalation_example_demonstrates_validated_escalation():
    # Example 4 is the canonical validated-escalation example: validate the
    # user's benign theory, name the real limitation, then let the tier land
    # as the conclusion. Anchored on stable substrings, not full sentences.
    final = _final_payload(FEW_SHOT_EXAMPLES[2])
    assert final["possibilities_mentioned"] is True
    message = final["message"]
    assert "puyat o migraine" in message                    # (a) validation
    assert "rare pero seryosong problema" in message        # (b) hedged plural
    assert "masisiguro sa chat lang" in message             # (b) named limitation
    assert "hindi ko masasabing puyat lang ito" in message  # kept mirror line
    # 1.3.1: explanation owner-replaced (old text used banned formal terms).
    assert "masisiguro sa chat lang — kaya ngayong araw" in final["explanation"]


def test_caregiver_example_is_taglish_with_chip_question():
    example = FEW_SHOT_EXAMPLES[1]
    assert "anak" in example["turns"][0]["user"]
    first = example["turns"][0]["assistant"]
    assert first["type"] == "question"
    assert 2 <= len(first["quick_replies"]) <= 4
    # 1.3.0: the question addresses the child by profile name, not "si baby".
    assert "si Mika" in first["message"]


def test_caregiver_assessment_uses_everyday_register():
    # 1.4.0: this care-advice line moved from "message" into "self_care"
    # (no-duplication rule) — it should no longer appear in the message.
    final = _final_payload(FEW_SHOT_EXAMPLES[1])
    assert any("naka-recommend sa box" in item for item in final["self_care"])
    assert "naka-recommend sa box" not in final["message"]


def test_caregiver_assessment_hands_off_to_self_care():
    # 1.4.1: restitched handoff line — the message gestures to self_care
    # instead of leaving a dangling reference to nothing.
    final = _final_payload(FEW_SHOT_EXAMPLES[1])
    assert "nilista ko sa baba" in final["message"]


def test_sore_throat_example_hands_off_to_self_care():
    # 1.4.1: restitched handoff line — same pattern as the Mika example,
    # in English.
    final = _final_payload(FEW_SHOT_EXAMPLES[0])
    assert "listed what helps below" in final["message"]


def test_sore_throat_example_now_has_a_question_turn():
    # 1.5.0 (A2): the deck over-taught single-turn assessment, so this
    # example gained a leading question turn (highest-value gap: fever) —
    # the approved assessment payload itself is unchanged (verified below).
    example = FEW_SHOT_EXAMPLES[0]
    assert len(example["turns"]) == 2
    first = example["turns"][0]["assistant"]
    assert first["type"] == "question"
    assert 2 <= len(first["quick_replies"]) <= 4


def test_sore_throat_example_final_assessment_unchanged():
    # The final assessment message is the pre-1.5.0 approved copy,
    # verbatim — only a question turn was prepended.
    final = _final_payload(FEW_SHOT_EXAMPLES[0])
    assert "That sounds like a common sore throat so far" in final["message"]
    assert final["urgency"] == "monitor_at_home"


def test_cat_scratch_example_is_english_exposure_with_question_turn():
    # 1.5.1 (A2): the deck's second "exposure + feeling unwell" template,
    # all-English, so Example 1 (Taglish mosquito/dengue) is no longer the
    # only model for that shape. One chip question, then see_doctor_soon.
    example = FEW_SHOT_EXAMPLES[4]
    assert "cat scratched me" in example["turns"][0]["user"]
    first = example["turns"][0]["assistant"]
    assert first["type"] == "question"
    assert 2 <= len(first["quick_replies"]) <= 4
    final = _final_payload(example)
    assert final["type"] == "assessment"
    assert final["urgency"] == "see_doctor_soon"
    assert final["possibilities_mentioned"] is True


def test_cat_scratch_example_is_english_end_to_end():
    # The whole point of the example: English in, English out — no
    # Tagalog function words anywhere in either assistant turn.
    import mirror_probes

    example = FEW_SHOT_EXAMPLES[4]
    for turn in example["turns"]:
        payload = turn["assistant"]
        texts = [payload["message"]]
        texts += payload["quick_replies"] + payload["watch_for"]
        texts += payload["self_care"] + payload["monitoring"]
        for field in ("explanation", "next_step", "encouragement"):
            if payload[field]:
                texts.append(payload[field])
        for text in texts:
            assert mirror_probes.detect_language(text) in ("english", "unknown"), text


def test_cat_scratch_example_watch_for_covers_spread_and_fever():
    final = _final_payload(FEW_SHOT_EXAMPLES[4])
    joined = " ".join(final["watch_for"]).lower()
    assert "spreading" in joined
    assert "red streaks" in joined
    assert "fever" in joined


def test_cat_scratch_example_next_step_is_tell_the_staff_style():
    final = _final_payload(FEW_SHOT_EXAMPLES[4])
    assert "tell the staff" in final["next_step"]


def test_cat_scratch_example_flagged_for_owner_read_aloud():
    source = (Path(__file__).parent / "system_prompt.py").read_text(encoding="utf-8")
    assert "AGENT-DRAFTED, PENDING OWNER READ-ALOUD (1.5.1)" in source


def test_crisis_example_shape_and_canonical_copy():
    example = FEW_SHOT_EXAMPLES[3]
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


# ---------------------------------------------------------------------------
# v2.0.0 conversation engine (spec §7): two kinds of turns, intent
# vocabulary, and the server-derived CONVERSATION STATE block
# ---------------------------------------------------------------------------

import wire_contract

SAMPLE_STATE = {
    "current_urgency": "seek_care_now",
    "active_findings": ["vomiting blood", "abdominal pain"],
    "last_assessment": {
        "findings": ["vomiting blood", "abdominal pain"],
        "explanation": "Blood in vomit needs same-day evaluation.",
        "next_step": "Go to the ER today.",
        "urgency": "seek_care_now",
    },
    "latch_active": True,
    "questions_used": 1,
}


def test_prompt_version_is_2_0_0():
    assert PROMPT_VERSION == "2.0.0"


def test_two_kinds_of_turns_teaches_golden_rule_and_every_intent():
    prompt = build()
    assert "## 3. TWO KINDS OF TURNS" in prompt
    assert "INTENT first" in prompt
    for intent in wire_contract.VALID_INTENTS:
        assert intent in prompt, f"intent {intent!r} missing from the prompt"
    for change in wire_contract.VALID_CHANGE_TYPES:
        assert change in prompt, f"change_type {change!r} missing from the prompt"


def test_state_block_omitted_when_no_conversation_state():
    assert "CONVERSATION STATE (server-derived" not in build()


def test_state_block_renders_findings_card_latch_and_directive():
    prompt = build_system_prompt(conversation_state=SAMPLE_STATE)
    assert "CONVERSATION STATE (server-derived" in prompt
    assert "CURRENT FINDINGS: vomiting blood; abdominal pain" in prompt
    assert "ACTIVE GUIDANCE CARD: seek_care_now" in prompt
    assert "Blood in vomit needs same-day evaluation." in prompt
    assert "already visible" in prompt
    assert "cannot go below seek_care_now" in prompt
    assert "1 of 3" in prompt


def test_state_block_sits_in_final_dynamic_section():
    prompt = build_system_prompt(conversation_state=SAMPLE_STATE)
    assert (prompt.index("CONVERSATION STATE (server-derived")
            > prompt.index("## 10. CONTEXT FOR THIS CONVERSATION"))


def test_state_block_without_latch_or_card_stays_quiet():
    prompt = build_system_prompt(conversation_state={
        "current_urgency": None, "active_findings": [],
        "last_assessment": None, "latch_active": False, "questions_used": 0,
    })
    assert "ACTIVE GUIDANCE CARD" not in prompt
    assert "CURRENT FINDINGS" not in prompt
    assert "cannot go below" not in prompt
    assert "0 of 3" in prompt


def test_new_v2_examples_present():
    titles = " | ".join(e["title"] for e in FEW_SHOT_EXAMPLES)
    assert "reassurance" in titles.lower()
    assert "asking-why" in titles.lower() or "asking why" in titles.lower()
    assert "testing reset" in titles.lower()


def test_every_example_turn_carries_the_v2_fields():
    for example in FEW_SHOT_EXAMPLES:
        for turn in example["turns"]:
            payload = turn["assistant"]
            for f in ("intents", "requires_clinical_reassessment", "change_type",
                      "reassessment_reason", "proposed_card_action", "findings"):
                assert f in payload, (example["title"], f)
