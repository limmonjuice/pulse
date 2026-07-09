"""
Root pytest config for functions/.

evals/ is a standalone harness that makes real, paced Gemini API calls
(see evals/README.md) — it must never run under pytest. File naming
inside evals/ already avoids pytest's default test_*.py discovery; this
collect_ignore is the second, independent layer of protection.
"""

collect_ignore = ["evals"]
