# functions/test_episode_state.py
"""Tests for episode_state.py — the State Builder (spec §4).

History shapes mirror Message.toHistoryJson() v2:
user turns {role, content}; assistant turns {role, content, type} plus,
on assessment turns, urgency/findings/explanation/next_step, and on
reset turns assessment_cleared: true.
"""
import episode_state
from episode_state import derive_episode_state

U = lambda text: {"role": "user", "content": text}


def A(type_, content="...", **extra):
    return {"role": "assistant", "content": content, "type": type_, **extra}


ASSESS = A(
    "assessment", urgency="see_doctor_soon",
    findings=["fever", "headache"],
    explanation="Worth a check within 1-2 days.",
    next_step="See a doctor within 1-2 days.",
)

RED_FLAG_TEXT = "I have chest pain and I'm having trouble breathing"


def test_empty_history_is_idle():
    s = derive_episode_state([], None)
    assert s.phase == "idle"
    assert s.current_urgency is None
    assert s.min_safe_urgency is None
    assert s.latched_rule_ids == []
    assert s.questions_used == 0
    assert s.active_findings == []
    assert s.last_assessment is None


def test_latch_from_earlier_user_turn_persists():
    history = [U(RED_FLAG_TEXT), A("assessment", urgency="seek_care_now"),
               U("But I feel okay sometimes.")]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency == "seek_care_now"
    assert s.latched_rule_ids  # the chest-pain rule id(s)


def test_current_urgency_and_scaffolding_from_last_assessment():
    s = derive_episode_state([U("fever po"), ASSESS], None)
    assert s.current_urgency == "see_doctor_soon"
    assert s.active_findings == ["fever", "headache"]
    assert s.last_assessment == {
        "findings": ["fever", "headache"],
        "explanation": "Worth a check within 1-2 days.",
        "next_step": "See a doctor within 1-2 days.",
        "urgency": "see_doctor_soon",
    }
    assert s.phase == "guidance"


def test_reset_marker_clears_everything_before_it():
    history = [U(RED_FLAG_TEXT), A("assessment", urgency="seek_care_now"),
               U("I was just testing"),
               A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency is None
    assert s.current_urgency is None
    assert s.phase == "idle"
    assert s.reset_index == 3


def test_rules_rearm_after_reset():
    history = [U("test lang"), A("conversation", assessment_cleared=True),
               U(RED_FLAG_TEXT)]
    s = derive_episode_state(history, None)
    assert s.min_safe_urgency == "seek_care_now"


def test_questions_used_counts_since_last_card_or_reset():
    history = [U("sore throat"), A("question"), U("no fever"), A("question"),
               U("mild"), ASSESS, U("ok"), A("question")]
    s = derive_episode_state(history, None)
    assert s.questions_used == 1  # only the question AFTER the card counts


def test_phase_assessing_when_last_assistant_turn_is_question():
    s = derive_episode_state([U("sore throat"), A("question")], None)
    assert s.phase == "assessing"


def test_crisis_lock_survives_reset_marker():
    history = [U("crisis text"), A("crisis"),
               U("just testing"), A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.phase == "crisis"


def test_history_scan_crash_fails_closed(monkeypatch):
    def boom(message, profile=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(episode_state.red_flags, "check_red_flags", boom)
    s = derive_episode_state([U("anything"), ASSESS], None)
    assert s.min_safe_urgency == "seek_care_now"
    assert "history_scan_failed" in s.latched_rule_ids


def test_malformed_turns_are_tolerated():
    history = [None, "junk", {"role": "assistant"}, {"role": "user"},
               {"role": "assistant", "type": "assessment", "urgency": 7,
            "content": "x", "findings": "not-a-list"}]
    s = derive_episode_state(history, None)  # must not raise
    assert s.current_urgency is None          # 7 is not a tier
    assert s.active_findings == []            # non-list dropped


def test_self_harm_crisis_survives_reset_marker():
    history = [U("I want to kill myself"),
               A("assessment", urgency="seek_care_now"),  # model failed to tag crisis
               U("just kidding, testing lang"),
               A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.phase == "crisis"
    # but the reset still clears the ordinary floor bookkeeping:
    assert s.min_safe_urgency is None


def test_multiple_reset_markers_uses_last_one():
    history = [U("a"), A("conversation", assessment_cleared=True),
               U("b"), A("conversation", assessment_cleared=True),
               U("c")]
    s = derive_episode_state(history, None)
    assert s.reset_index == 3


def test_reset_marker_as_final_turn_is_idle():
    history = [U(RED_FLAG_TEXT), A("assessment", urgency="seek_care_now"),
               A("conversation", assessment_cleared=True)]
    s = derive_episode_state(history, None)
    assert s.phase == "idle"
    assert s.current_urgency is None
    assert s.min_safe_urgency is None
    assert s.active_findings == []
    assert s.last_assessment is None


def test_assessment_missing_optional_fields_defaults_safely():
    history = [U("fever po"),
               {"role": "assistant", "content": "...", "type": "assessment",
                "urgency": "monitor_at_home"}]
    s = derive_episode_state(history, None)
    assert s.current_urgency == "monitor_at_home"
    assert s.active_findings == []
    assert s.last_assessment == {
        "findings": [],
        "explanation": None,
        "next_step": None,
        "urgency": "monitor_at_home",
    }


def test_history_scan_crash_latches_failure_once_across_multiple_turns(monkeypatch):
    def boom(message, profile=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(episode_state.red_flags, "check_red_flags", boom)
    history = [U("one"), U("two"), U("three")]
    s = derive_episode_state(history, None)
    assert s.latched_rule_ids.count("history_scan_failed") == 1
