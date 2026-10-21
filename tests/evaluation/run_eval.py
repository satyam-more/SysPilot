"""
Evaluation runner.

Seeds a fresh database with synthetic events, runs each eval case through
the agent loop against the currently active provider, scores the result,
and writes a results JSON file.

Usage:
    .venv/bin/python -m tests.evaluation.run_eval            # offline (default)
    .venv/bin/python -m tests.evaluation.run_eval --out tests/evaluation/results_offline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path

from tests.evaluation.eval_cases import EVAL_CASES
from tests.evaluation.eval_harness import EvalResult, score_case


def _seed_database(db_dir: Path) -> None:
    """Point the DB at a temp dir, init schema, seed synthetic events."""
    import backend.database.db as db_mod

    db_path = db_dir / "eval.db"
    db_mod._DB_DIR = db_dir
    db_mod._DB_PATH = db_path
    db_mod._conn = None
    db_mod.init_db()

    from backend.memory.events import ingest_event
    from tests.fixtures.synthetic_events import SYNTHETIC_EVENTS

    # Make sure privacy is active-allowed before seeding.
    from backend.privacy.controller import PrivacyController
    PrivacyController._reset()
    PrivacyController().deactivate_privacy()

    for ev in SYNTHETIC_EVENTS:
        ingest_event(ev)


async def _run_one(case, model_name: str) -> EvalResult:
    from backend.harness.loop import run_agent_loop

    start = time.perf_counter()
    try:
        result = await run_agent_loop(user_question=case.query)
        answer = result["answer"]
        evidence = result.get("evidence", [])
        iterations = result["iterations"]
        error = None
    except Exception as exc:  # noqa: BLE001 — eval must capture any failure
        answer = ""
        evidence = []
        iterations = 0
        error = f"{type(exc).__name__}: {exc}"

    latency_ms = (time.perf_counter() - start) * 1000.0

    if error:
        return EvalResult(
            case_id=case.id,
            query=case.query,
            model=model_name,
            answer="",
            evidence_count=0,
            correct=False,
            evidence_correct=False,
            hallucination_free=False,
            latency_ms=latency_ms,
            iterations=iterations,
            notes=f"ERROR: {error}",
        )

    correct, evidence_correct, hallucination_free, notes = score_case(
        case, answer, evidence
    )

    return EvalResult(
        case_id=case.id,
        query=case.query,
        model=model_name,
        answer=answer,
        evidence_count=len(evidence),
        correct=correct,
        evidence_correct=evidence_correct,
        hallucination_free=hallucination_free,
        latency_ms=latency_ms,
        iterations=iterations,
        notes=notes,
    )


async def run_all(out_path: Path, provider_label: str) -> dict:
    from backend.harness.providers import provider_registry

    provider = provider_registry.get_active_provider()
    model_name = provider.get_active_model()

    results: list[EvalResult] = []
    for i, case in enumerate(EVAL_CASES):
        if i > 0:
            # Space out requests to stay under free-tier rate limits.
            await asyncio.sleep(15)
        print(f"\n=== Case {case.id}: {case.query}")
        res = await _run_one(case, model_name)
        status = "PASS" if res.correct else "FAIL"
        print(f"    [{status}] {res.notes} ({res.latency_ms:.0f}ms, {res.iterations} iters)")
        print(f"    answer: {res.answer[:160]}")
        results.append(res)

    passed = sum(1 for r in results if r.correct)
    summary = {
        "model": model_name,
        "provider": provider_label,
        "passed": passed,
        "total": len(results),
        "cases": [r.to_dict() for r in results],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n==== {passed}/{len(results)} cases passed. Results written to {out_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="tests/evaluation/results_api.json",
        help="Path to write the results JSON.",
    )
    parser.add_argument(
        "--provider",
        choices=["api", "offline"],
        default="api",
        help="Which provider to evaluate. Default: api (OpenAI).",
    )
    args = parser.parse_args()

    # 1. Read the REAL saved provider config (which provider/model/key_ref)
    #    from the user's actual DB before we switch to a temp DB for events.
    import backend.database.db as db_mod
    from backend.harness.providers import provider_registry

    db_mod._conn = None
    db_mod.init_db()  # opens the real ~/.config/syspilot DB
    provider_registry._load_config()
    saved_provider = provider_registry._api_config.get("provider", "openai")
    saved_model = provider_registry._api_config.get("model", "")
    saved_key_ref = provider_registry._api_config.get("key_ref", "")

    # 2. Seed a fresh temp DB with synthetic events (isolates the eval data).
    with tempfile.TemporaryDirectory() as tmp:
        _seed_database(Path(tmp))

        if args.provider == "api":
            from backend.security.keystore import key_is_configured

            if not (saved_key_ref and key_is_configured(saved_provider)):
                print(
                    "ERROR: API mode requested but no API key is configured.\n"
                    "Add your key first via the Settings UI, then re-run."
                )
                return
            # Restore the real provider config (temp-DB seeding reset it).
            provider_registry._api_config = {
                "provider": saved_provider,
                "model": saved_model or "llama-3.3-70b-versatile",
                "key_ref": saved_key_ref,
            }
            provider_registry._current_mode = "api"
            print(f"Evaluating provider={saved_provider} model={provider_registry._api_config['model']}")
        else:
            provider_registry._current_mode = "offline"

        asyncio.run(run_all(Path(args.out), args.provider))


if __name__ == "__main__":
    main()
