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


def test_final_urgency_block_absent_by_default():
    assert "INTERNAL CONTEXT" not in build_system_prompt(final_urgency=None)


def test_final_urgency_block_present_when_given_and_says_do_not_restate():
    prompt = build_system_prompt(final_urgency="see_doctor_soon")
    assert "see_doctor_soon" in prompt
    assert "do not restate" in prompt.lower()
