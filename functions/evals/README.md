# Pulse eval harness

Turns "is the prompt calibrated well?" from a feeling into a number,
tracked per `PROMPT_VERSION` (see `system_prompt.py`).

This is **not** part of the pytest suite. It makes real, paced calls to
Gemini through the actual pipeline (`main.run_pipeline` — the same pure
function `test_main.py` calls, with the Gemini SDK mocked). No mocking
here: every case is a live request, so results reflect the real model
and the real prompt, not a fixture.

## ⚠️ Never add this to CI or pytest

- It costs real API money on every run.
- It takes real wall-clock time (paced to avoid rate limits).
- Results are non-deterministic — a model call, not a fixture — so it
  can't be a pass/fail gate the way `pytest` is.

Two independent layers keep `pytest` away from this directory: no file
in here is named `test_*.py`, and `functions/conftest.py` has
`collect_ignore = ["evals"]`. Don't undo either.

## Running it

From `functions/`, with `GEMINI_API_KEY` set in `functions/.env` (the
harness loads that file itself — no emulator needed):

```bash
python evals/run_evals.py                              # full suite, ~28 cases, ~10 min
python evals/run_evals.py --category tier_calibration   # one category, fast iteration
python evals/run_evals.py --delay 30                    # slower pacing if you hit rate limits
```

The full suite is ~28 cases at the default 20s delay between calls —
about 10 minutes. Each run prints an estimated runtime before starting,
and live output per case (id, category, PASS/FAIL per check, the
actual tier/type/message) as it runs, not just a table at the end.

Categories: `language_mirroring`, `tier_calibration`,
`possibilities_frequency`, `voice_compliance`, `crisis_routing`,
`schema_and_resilience` — see `cases.py` for the full case list and the
reasoning behind each one (including cases flagged in `notes` as
genuine judgment calls, not settled answers).

## Where results land

Every run writes a full JSON report to `evals/results/` —
`{PROMPT_VERSION}_{timestamp}.json`, containing every case's full
request, full response, and per-check results. That's the artifact for
comparing calibration across prompt versions later: bump
`PROMPT_VERSION` in `system_prompt.py`, rerun, diff the reports.

## Reading the summary

- Most categories print a pass rate (checks passed / total).
- `possibilities_frequency` has no per-case pass/fail — it's tallied
  into a ratio, flagged if it drops under 50%. Silence about
  plausible possibilities isn't safer, it's just less useful.
- `voice_compliance`'s word/regex checks are heuristics, not proof of
  good copy — a clean pass doesn't mean the Taglish actually reads
  well; read the printed replies.
- A case marked `CRASHED` failed inside the pipeline itself (not a
  model-quality issue) — see the printed exception and the case's
  `notes` in `cases.py`.
