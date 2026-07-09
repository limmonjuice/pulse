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
import system_prompt  # noqa: E402
import checkers  # noqa: E402
from cases import CASES, EvalCase  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _run_checks(case: EvalCase, response: dict) -> list[dict]:
    results = []
    for checker_name, expected in case.checks:
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


def run_case(case: EvalCase) -> dict:
    request = {
        "message": case.message,
        "profile": case.profile,
        "worry_level": case.worry_level,
        "regional_context": case.regional_context,
        "history": case.history,
    }
    print(f"\n{'=' * 70}\n[{case.category}] {case.id}")
    if case.notes:
        print(f"  note: {case.notes}")

    try:
        response = main.run_pipeline(**request)
    except Exception as exc:  # a case crashing must not kill the whole run
        print(f"  CRASHED: {exc!r}")
        return {
            "case_id": case.id,
            "category": case.category,
            "request": request,
            "response": None,
            "crashed": True,
            "error": repr(exc),
            "checks": [
                {"checker": name, "passed": False, "detail": f"pipeline crashed: {exc!r}"}
                for name, _ in case.checks
            ],
            "possibilities_mentioned": None,
        }

    check_results = _run_checks(case, response)
    for cr in check_results:
        verdict = "PASS" if cr["passed"] else "FAIL"
        print(f"  {verdict}  {cr['checker']}: {cr['detail']}")

    print(
        f"  type={response.get('type')!r}  urgency={response.get('urgency')!r}  "
        f"message: {_truncate(response.get('message', ''))}"
    )

    return {
        "case_id": case.id,
        "category": case.category,
        "request": request,
        "response": response,
        "crashed": False,
        "checks": check_results,
        "possibilities_mentioned": checkers.check_possibilities_mentioned(response),
    }


def _print_summary(results: list[dict]) -> None:
    print(f"\n{'=' * 70}\nSUMMARY — PROMPT_VERSION {system_prompt.PROMPT_VERSION}\n{'=' * 70}")

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
    path = RESULTS_DIR / f"{system_prompt.PROMPT_VERSION}_{timestamp}.json"
    payload = {
        "prompt_version": system_prompt.PROMPT_VERSION,
        "model_name": main.gemini_client.MODEL_NAME,
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

    est_seconds = len(cases) * args.delay
    print(f"Pulse eval harness — PROMPT_VERSION {system_prompt.PROMPT_VERSION}")
    scope = f"category {args.category!r}" if args.category else "all categories"
    print(f"Running {len(cases)} case(s) across {scope}")
    print(f"Estimated runtime: ~{est_seconds / 60:.1f} min ({len(cases)} cases x {args.delay}s delay)")

    results = []
    for i, case in enumerate(cases):
        results.append(run_case(case))
        if i < len(cases) - 1:
            time.sleep(args.delay)

    _print_summary(results)
    _write_report(results, args.category)


if __name__ == "__main__":
    main_cli()
