"""
detect_language coverage tests.

The 2026-07-26 regression (English dog-bite conversation answered in
Tagalog on 3.1-flash-lite) traced to detect_language returning "unknown"
for the entire class of terse, function-word-free symptom statements —
so main._conversation_language yielded None, the CONVERSATION LANGUAGE
directive was omitted, and the model fell back to its Tagalog register
prior. The "live-verified 2026-07-13" claim in the mirroring memory was
invalid: it passed only because those probe strings happened to contain
marker words. These cases pin the terse vocabulary the detector must
classify so that regression class can never silently reappear.
"""

from __future__ import annotations

import pytest

import mirror_probes


@pytest.mark.parametrize(
    "text",
    [
        "i got bit by a dog",
        "im having hydrophobia",
        "im dizzy",
        "my head hurts",
        "No fever",
        "Feeling worse",
    ],
)
def test_terse_english_symptom_statements_classify_english(text):
    assert mirror_probes.detect_language(text) == "english"


@pytest.mark.parametrize(
    "text",
    [
        "nilalagnat ako",
        "inuubo ako",
        "may lagnat",
        "masakit ulo ko",
        "oo",
        "opo",
    ],
)
def test_terse_tagalog_statements_classify_tagalog(text):
    assert mirror_probes.detect_language(text) == "tagalog"
