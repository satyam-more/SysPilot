"""
The 5 evaluation cases from Step 28.

These run against the synthetic events defined in tests/fixtures/synthetic_events.py.
"""

from tests.evaluation.eval_harness import EvalCase

EVAL_CASES: list[EvalCase] = [
    EvalCase(
        id=1,
        query="Where did I stop learning Rust?",
        expected_sources=["Rust_Notes", "cargo"],
        must_not_claim=["mastered", "completed the book", "finished rust"],
    ),
    EvalCase(
        id=2,
        query="What errors did I encounter while running my code?",
        expected_sources=["cargo"],
        must_not_claim=["no errors", "everything worked", "no issues"],
    ),
    EvalCase(
        id=3,
        query="What was I working on in my Rust project?",
        expected_sources=["Rust_Notes"],
        must_not_claim=["python", "javascript", "web development"],
    ),
    EvalCase(
        id=4,
        query="What did I learn about quantum computing?",
        expected_sources=[],
        must_not_claim=["qubit", "superposition", "entanglement"],
        expect_no_results=True,
    ),
    EvalCase(
        id=5,
        query="Did I fully master the ownership chapter in Rust?",
        expected_sources=["Rust_Notes"],
        must_not_claim=["yes you mastered", "fully mastered", "completely understood"],
        require_uncertainty=True,
    ),
]
