"""Tests for wire_contract.py — the shared engine vocabulary."""
import wire_contract as wc


def test_tier_ordering():
    assert wc.max_urgency("monitor_at_home", "seek_care_now") == "seek_care_now"
    assert wc.max_urgency("seek_care_now", "monitor_at_home") == "seek_care_now"
    assert wc.max_urgency("see_doctor_soon", "see_doctor_soon") == "see_doctor_soon"


def test_max_urgency_unrecognized_first_arg_yields_second():
    assert wc.max_urgency(None, "see_doctor_soon") == "see_doctor_soon"
    assert wc.max_urgency("bogus", "monitor_at_home") == "monitor_at_home"


def test_urgency_lt():
    assert wc.urgency_lt("monitor_at_home", "see_doctor_soon")
    assert not wc.urgency_lt("seek_care_now", "see_doctor_soon")
    assert not wc.urgency_lt("see_doctor_soon", "see_doctor_soon")


def test_vocabularies_are_frozen_and_populated():
    assert "reassurance_seeking" in wc.VALID_INTENTS
    assert "start_new_assessment" in wc.VALID_INTENTS
    assert wc.VALID_CHANGE_TYPES == frozenset({
        "new_symptom", "resolved_symptom", "worsening",
        "new_history", "treatment_update", "none",
    })
    assert wc.VALID_CARD_ACTIONS == frozenset({"new", "update", "keep", "clear"})
    assert wc.RESET_INTENTS <= wc.VALID_INTENTS
