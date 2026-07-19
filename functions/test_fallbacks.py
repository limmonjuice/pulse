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
