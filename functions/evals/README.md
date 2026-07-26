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
python evals/run_evals.py                              # full suite, 28 cases, ~10 min or more
python evals/run_evals.py --category tier_calibration   # one category, fast iteration
python evals/run_evals.py --delay 30                    # slower pacing if you hit rate limits
```

The full suite is 28 cases at the default 20s delay between calls —
about 10 minutes, though cases with `scripted_replies` (see below) make
one extra Gemini call per question turn actually asked, so the real
runtime can run longer than the printed estimate. Each run prints an
estimated runtime before starting, and live output per case (id,
category, PASS/FAIL per check per turn, the actual tier/type/message)
as it runs, not just a table at the end.

Some cases carry `scripted_replies` — chip-style user replies fed back
automatically whenever the pipeline returns type `"question"`, so the
harness can exercise multi-turn conversations (up to
`system_prompt.py`'s 3-question budget) instead of only single-turn
opener/response pairs. `tier_calibration`'s summary line also prints
the average number of question turns before assessment across that
category.

## Per-turn checks and honest failure attribution

Checks carry a scope: `"final"` (default — runs once, on the case's
last response) or `"every_turn"` (runs on every response the case
produced, question turns included). All `language_mirroring` checks
are `every_turn`: a Tagalog question turn to an English user is a
failure AT THAT TURN, even if the case also ends for another reason.
This exists because the 2026-07-13 model swap's mirroring regression
first surfaced as wrong-language question turns that final-only
checking collapsed into "question budget exceeded scripted replies".

Running out of scripted replies while the model keeps asking questions
is reported as its own separate fact (`budget_exceeded`), never as a
blanket failure that masks per-turn findings: the turns that did happen
keep their real per-turn check results, and final-scope checks are
marked "not evaluable" rather than blamed on the budget. Each case's
report entry lists per-turn results (`turns`), not one collapsed
verdict.

## Three outcomes: passed / failed / non-evaluable

Every check result carries `evaluable`. A check that could not
legitimately be scored is **neither a pass nor a fail** — counting it
either way lies about the run:

- **Degraded turns.** If a turn is Pulse-constructed rather than model
  output (`type="error"`, or any hardcoded string from `fallbacks.py`),
  every check on that turn is non-evaluable. Added 2026-07-26 after the
  `language_mirroring` sweep scored `check_language` against
  `FRIENDLY_DEGRADED_ERROR_MESSAGE_EN` — Pulse's own English string —
  and reported it as an English mirroring PASS. The check could not have
  failed, because no model was involved. This is a CLASS defect (every
  checker has the same hole — see the audit in
  `checkers.degraded_turn_reason`), so the gate lives in
  `_run_checks` and applies uniformly rather than inside each checker.
- **Budget-exceeded final checks.** Previously described as "not
  evaluable" but still scored as failures, inflating the failure count
  with turns nobody measured. Now genuinely non-evaluable.
- **Crashes stay failures.** A pipeline crash is a real defect and
  counts against the run.

Pass rates are computed over **evaluable checks only**, and the summary
prints `passed / failed / non-evaluable` separately. Any run with a
non-evaluable check prints a warning and must not be read as a clean
verification — that is the guard against another vacuous 100%.

## Model-swap guard

Every results file is stamped with BOTH the prompt version and the
model, in the filename (`{PROMPT_VERSION}_{MODEL_NAME}_{timestamp}.json`)
and the payload. On startup the runner compares
`gemini_client.MODEL_NAME` against the most recent results file and
prints a loud banner if the model changed — results across models are
not comparable, and a full re-baseline is recommended. Separately, the
regular pytest suite (`test_gemini_client.py`) fails if `MODEL_NAME`
changes without a matching `MODEL_CHANGELOG` entry (date + reason +
whether evals were re-run), so a silent model swap can't survive CI
either.

Categories: `language_mirroring`, `tier_calibration`,
`possibilities_frequency`, `voice_compliance`, `crisis_routing`,
`schema_and_resilience` — see `cases.py` for the full case list and the
reasoning behind each one (including cases flagged in `notes` as
genuine judgment calls, not settled answers).

## Where results land

Every run writes a full JSON report to `evals/results/` —
`{PROMPT_VERSION}_{MODEL_NAME}_{timestamp}.json`, containing every
case's full request, every turn's response and per-turn check results,
and the final checks. That's the artifact for comparing calibration
across prompt versions later: bump `PROMPT_VERSION` in
`system_prompt.py`, rerun, diff the reports — but only within the same
model; a model swap resets every baseline (see the guard above).

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
