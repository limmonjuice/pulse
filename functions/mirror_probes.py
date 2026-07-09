"""
Language-detection heuristic, shared with the eval harness.

RETIRED as a standalone probe script (2026-07-08): this used to be the
first eval-harness case family, hitting the local emulator over raw
HTTP. That job is now subsumed by evals/run_evals.py --category
language_mirroring, which runs the same 4 cases through the real
in-process pipeline (see evals/cases.py) instead of HTTP against a
running emulator. What remains here is just detect_language() and its
marker word sets — evals/checkers.py imports detect_language directly
rather than reimplementing the heuristic.

Detection is heuristic (function-word counting), so treat results as
strong signal, not proof — read the printed replies yourself.
"""

# Common function words — high-frequency, language-distinctive.
TAGALOG_MARKERS = {
    "ang", "ng", "mga", "yung", "mo", "ko", "siya", "niya", "kung",
    "para", "lang", "naman", "kasi", "pero", "tapos", "kaya", "wala",
    "hindi", "may", "sa'yo", "ito", "iyan", "yan", "na",
}
ENGLISH_MARKERS = {
    "the", "and", "you", "your", "that", "this", "with", "for", "have",
    "has", "it's", "are", "was", "been", "should", "would", "can",
    "over", "next", "if", "get", "getting", "doctor", "please", "keep", "watch", "worth",
}


def detect_language(text: str) -> str:
    """Crude classifier: count function-word hits per language."""
    words = [w.strip(".,!?—-()\"'").lower() for w in text.split()]
    tl = sum(1 for w in words if w in TAGALOG_MARKERS)
    en = sum(1 for w in words if w in ENGLISH_MARKERS)
    if tl == 0 and en == 0:
        return "unknown"
    if tl > en * 1.5:
        return "tagalog"
    if en > tl * 1.5:
        return "english"
    return "mixed"  # Taglish territory
