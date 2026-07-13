"""
CLI runner for Pulse's Gemini calibration eval harness. See README.md in
this directory for what this is, cost/runtime expectations, and the
CI/pytest isolation warning.

Run from functions/:
    python evals/run_evals.py                                  # full suite
    python evals/run_evals.py --category tier_calibration       # one category
    python evals/run_evals.py --delay 30                        # slower pacing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_FUNCTIONS_DIR = Path(__file__).resolve().parent.parent
if str(_FUNCTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_FUNCTIONS_DIR))

_ENV_PATH = _FUNCTIONS_DIR / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE loader for functions/.env — the same file and
    GEMINI_API_KEY gemini_client.py reads via genai.Client(). Needed here
    because this harness runs as a plain `python` process, outside the
    firebase-tools emulator that normally injects .env into the deployed
    or emulated function's environment. Does not override a key already
    set in the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(_ENV_PATH)

import main  # noqa: E402  (import order matters: sys.path/env must be set first)
import gemini_client  # noqa: E402
import system_prompt  # noqa: E402
import checkers  # noqa: E402
from cases import CASES, EvalCase  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _split_checks(case: EvalCase) -> tuple[list[tuple], list[tuple]]:
    """Partition a case's checks by scope. Each check is either
    (checker_name, expected) — scope "final", the historical default —
    or (checker_name, expected, scope) with scope "final" or
    "every_turn". every_turn checks run against EVERY response the case
    produced, question turns included: a Tagalog question turn to an
    English user is a failure at that turn, no matter how the case ends."""
    final_checks: list[tuple] = []
    every_turn_checks: list[tuple] = []
    for check in case.checks:
        if len(check) == 3:
            name, expected, scope = check
        else:
            (name, expected), scope = check, "final"
        if scope == "every_turn":
            every_turn_checks.append((name, expected))
        elif scope == "final":
            final_checks.append((name, expected))
        else:
            raise ValueError(f"case {case.id}: unknown check scope {scope!r}")
    return final_checks, every_turn_checks


def _run_checks(checks: list[tuple], response: dict) -> list[dict]:
    results = []
    for checker_name, expected in checks:
        checker_fn = checkers.CHECKERS[checker_name]
        outcome = checker_fn(response, expected)
        if isinstance(outcome, tuple):
            passed, detail = outcome
        else:
            # check_possibilities_mentioned returns a bare bool when used
            # as an assertion (see its docstring) — compare against expected.
            passed, detail = (outcome == expected), f"value={outcome!r} (expected {expected!r})"
        results.append({"checker": checker_name, "passed": passed, "detail": detail})
    return results


def _truncate(text: str, n: int = 200) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 3] + "..."


def run_case(case: EvalCase, delay: float) -> dict:
    print(f"\n{'=' * 70}\n[{case.category}] {case.id}")
    if case.notes:
        print(f"  note: {case.notes}")

    final_checks, every_turn_checks = _split_checks(case)

    # Multi-turn loop: as long as the pipeline keeps returning type
    # "question" (up to system_prompt.py's 3-question budget), feed back
    # the next scripted reply and call again. `history` accumulates the
    # real turns exchanged so far; `message` is always the next thing the
    # simulated user says. EVERY response — question turns included — is
    # recorded in `turns` and run through the case's every_turn checks;
    # final-scope checks additionally run on the last response. The two
    # red-flag-floor sanity cases never loop for real — the deterministic
    # floor converts their question (if any) to an assessment inside
    # run_pipeline itself, before this function ever sees it.
    history = list(case.history)
    message = case.message
    remaining_replies = list(case.scripted_replies)
    question_turns = 0
    turns: list[dict] = []
    budget_exceeded = False

    while True:
        request = {
            "message": message,
            "profile": case.profile,
            "worry_level": case.worry_level,
            "regional_context": case.regional_context,
            "history": history,
        }
        try:
            response = main.run_pipeline(**request)
        except Exception as exc:  # a case crashing must not kill the whole run
            print(f"  CRASHED: {exc!r}")
            crash_checks = [
                {"checker": name, "passed": False, "detail": f"pipeline crashed: {exc!r}", "scope": "final"}
                for name, _ in final_checks + every_turn_checks
            ]
            return {
                "case_id": case.id,
                "category": case.category,
                "request": request,
                "response": None,
                "turns": turns,
                "crashed": True,
                "budget_exceeded": False,
                "error": repr(exc),
                # Turns that DID happen keep their real per-turn results.
                "checks": [c for t in turns for c in t["checks"]] + crash_checks,
                "possibilities_mentioned": None,
                "question_turns": question_turns,
            }

        turn_no = len(turns) + 1
        turn_check_results = [
            {**cr, "scope": "every_turn", "turn": turn_no}
            for cr in _run_checks(every_turn_checks, response)
        ]
        turns.append(
            {
                "turn": turn_no,
                "user_message": message,
                "response": response,
                "checks": turn_check_results,
            }
        )
        is_question = response.get("type") == "question"
        if is_question:
            question_turns += 1
            print(f"  question turn {question_turns}: {_truncate(response.get('message', ''))}")
        for cr in turn_check_results:
            verdict = "PASS" if cr["passed"] else "FAIL"
            print(f"    turn {turn_no} {verdict}  {cr['checker']}: {cr['detail']}")

        if not is_question:
            break

        if not remaining_replies:
            # Honest attribution (B2): running out of scripted replies is
            # ITS OWN fact, reported alongside — never instead of — the
            # per-turn results above. Final-scope checks could not be
            # evaluated (there is no final non-question response); they are
            # recorded as such rather than silently absorbing the blame.
            budget_exceeded = True
            print("  BUDGET EXCEEDED: model asked another question after scripted replies ran out")
            break

        # Client contract (see main.py's _history_has_crisis_lock): assistant
        # turns in history must carry their "type" field.
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response.get("message", ""), "type": response.get("type")},
        ]
        message = remaining_replies.pop(0)
        time.sleep(delay)

    if budget_exceeded:
        final_check_results = [
            {
                "checker": name,
                "passed": False,
                "detail": "not evaluable: question budget exceeded scripted replies before a final response",
                "scope": "final",
            }
            for name, _ in final_checks
        ]
    else:
        # check_min_question_turns reads a synthetic field that never
        # touches the stored/report response.
        check_response = {**response, "_eval_question_turns": question_turns}
        final_check_results = [
            {**cr, "scope": "final"} for cr in _run_checks(final_checks, check_response)
        ]
    for cr in final_check_results:
        verdict = "PASS" if cr["passed"] else "FAIL"
        print(f"  {verdict}  {cr['checker']}: {cr['detail']}")

    print(
        f"  type={response.get('type')!r}  urgency={response.get('urgency')!r}  "
        f"message: {_truncate(response.get('message', ''))}"
    )

    all_checks = [c for t in turns for c in t["checks"]] + final_check_results
    return {
        "case_id": case.id,
        "category": case.category,
        "request": request,
        "response": response,
        "turns": turns,
        "crashed": False,
        "budget_exceeded": budget_exceeded,
        "checks": all_checks,
        "possibilities_mentioned": (
            None if budget_exceeded else checkers.check_possibilities_mentioned(response)
        ),
        "question_turns": question_turns,
    }


def _check_model_continuity() -> None:
    """Make a silent model swap impossible to miss: compare the current
    MODEL_NAME against the most recent results file and print a loud
    banner if it changed. Results across different models are NOT
    comparable — calibration and language behavior are per-model."""
    latest = max(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, default=None)
    if latest is None:
        return
    try:
        previous_model = json.loads(latest.read_text(encoding="utf-8")).get("model_name")
    except (OSError, json.JSONDecodeError):
        previous_model = None
    if previous_model and previous_model != gemini_client.MODEL_NAME:
        bar = "!" * 70
        print(
            f"\n{bar}\n"
            f"!!  MODEL CHANGED since last eval run:\n"
            f"!!      {previous_model}  ->  {gemini_client.MODEL_NAME}\n"
            f"!!  Results are NOT comparable across models — a full\n"
            f"!!  re-baseline of every category is recommended, and\n"
            f"!!  gemini_client.MODEL_CHANGELOG must carry the new entry.\n"
            f"!!  (last results file: {latest.name})\n"
            f"{bar}\n"
        )


def _print_summary(results: list[dict]) -> None:
    print(
        f"\n{'=' * 70}\nSUMMARY — PROMPT_VERSION {system_prompt.PROMPT_VERSION} "
        f"on {gemini_client.MODEL_NAME}\n{'=' * 70}"
    )

    by_category: dict[str, list[dict]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    overall_total = 0
    overall_passed = 0
    possibilities_ratio = None

    for category in sorted(by_category):
        entries = by_category[category]
        if category == "possibilities_frequency":
            tallied = [e["possibilities_mentioned"] for e in entries if e["possibilities_mentioned"] is not None]
            ratio = (sum(1 for v in tallied if v) / len(tallied)) if tallied else 0.0
            possibilities_ratio = ratio
            flag = "  <-- below 50%!" if ratio < 0.5 else ""
            print(f"  {category}: {sum(1 for v in tallied if v)}/{len(tallied)} mentioned possibilities ({ratio:.0%}){flag}")
            continue
        checks_flat = [c for e in entries for c in e["checks"]]
        passed = sum(1 for c in checks_flat if c["passed"])
        total = len(checks_flat)
        overall_total += total
        overall_passed += passed
        rate = (passed / total * 100) if total else 0.0
        print(f"  {category}: {passed}/{total} checks passed ({rate:.0f}%)")
        budget_exceeded = [e["case_id"] for e in entries if e.get("budget_exceeded")]
        if budget_exceeded:
            print(
                f"    {len(budget_exceeded)} case(s) ended on question-budget "
                f"exhaustion (reported separately from check results): {budget_exceeded}"
            )
        if category == "tier_calibration":
            question_turns = [e.get("question_turns", 0) or 0 for e in entries]
            avg_question_turns = sum(question_turns) / len(question_turns) if question_turns else 0.0
            print(f"    avg question-turns-before-assessment: {avg_question_turns:.2f}")

    if overall_total:
        print(f"\n  OVERALL: {overall_passed}/{overall_total} checks passed ({overall_passed / overall_total:.0%})")
    if possibilities_ratio is not None:
        print(f"  possibilities_frequency ratio: {possibilities_ratio:.0%}")

    crashed = [r for r in results if r["crashed"]]
    if crashed:
        print(f"\n  {len(crashed)} case(s) CRASHED: {[r['case_id'] for r in crashed]}")

    print(f"\n  PROMPT_VERSION: {system_prompt.PROMPT_VERSION}")


def _write_report(results: list[dict], category_filter: str | None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Both PROMPT_VERSION and MODEL_NAME in the filename (B3): a results
    # file must be attributable to its exact prompt AND model at a glance —
    # the same prompt on a different model is a different baseline.
    path = RESULTS_DIR / f"{system_prompt.PROMPT_VERSION}_{gemini_client.MODEL_NAME}_{timestamp}.json"
    payload = {
        "prompt_version": system_prompt.PROMPT_VERSION,
        "model_name": gemini_client.MODEL_NAME,
        "category_filter": category_filter,
        "timestamp": timestamp,
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Full report written to: {path}")
    return path


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Pulse prompt-calibration eval harness")
    parser.add_argument("--category", default=None, help="Run only this category")
    parser.add_argument(
        "--delay", type=float, default=20.0,
        help="Seconds between real API calls (default 20 — faster spacing hits rate limits)",
    )
    args = parser.parse_args()

    cases = [c for c in CASES if args.category is None or c.category == args.category]
    if not cases:
        available = sorted({c.category for c in CASES})
        print(f"No cases match category {args.category!r}. Available categories: {available}")
        sys.exit(1)

    _check_model_continuity()

    # Lower bound: cases with scripted_replies make one extra Gemini call
    # per question turn actually asked, which this can't know in advance.
    est_seconds = len(cases) * args.delay
    print(
        f"Pulse eval harness — PROMPT_VERSION {system_prompt.PROMPT_VERSION} "
        f"on {gemini_client.MODEL_NAME}"
    )
    scope = f"category {args.category!r}" if args.category else "all categories"
    print(f"Running {len(cases)} case(s) across {scope}")
    print(f"Estimated runtime: >= ~{est_seconds / 60:.1f} min ({len(cases)} cases x {args.delay}s delay; more for multi-turn cases)")

    results = []
    for i, case in enumerate(cases):
        results.append(run_case(case, args.delay))
        if i < len(cases) - 1:
            time.sleep(args.delay)

    _print_summary(results)
    _write_report(results, args.category)


if __name__ == "__main__":
    main_cli()
