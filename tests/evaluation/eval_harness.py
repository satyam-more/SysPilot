"""
Evaluation harness data structures.

An EvalCase defines a question and the correctness criteria for the answer.
An EvalResult captures what the agent actually produced and whether it passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: int
    query: str
    # Substrings that must appear somewhere in the cited evidence
    # (titles, content excerpts, or file paths). At least one per entry.
    expected_sources: list[str] = field(default_factory=list)
    # Strings that must NOT appear in the answer text (case-insensitive).
    # These represent hallucinations or overconfident claims.
    must_not_claim: list[str] = field(default_factory=list)
    # The answer must contain at least one of these uncertainty markers
    # when the case requires the model to hedge (e.g. "I think", "seems").
    # Empty list means no hedging requirement.
    require_uncertainty: bool = False
    # If True, the correct behavior is to find NO relevant events and say so.
    expect_no_results: bool = False


@dataclass
class EvalResult:
    case_id: int
    query: str
    model: str
    answer: str
    evidence_count: int
    correct: bool
    evidence_correct: bool
    hallucination_free: bool
    latency_ms: float
    iterations: int
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "case": self.case_id,
            "query": self.query,
            "model": self.model,
            "correct": self.correct,
            "evidence_correct": self.evidence_correct,
            "hallucination_free": self.hallucination_free,
            "latency_ms": round(self.latency_ms, 1),
            "iterations": self.iterations,
            "evidence_count": self.evidence_count,
            "answer": self.answer,
            "notes": self.notes,
        }


# Uncertainty markers that indicate the model is hedging appropriately.
UNCERTAINTY_MARKERS = [
    "i think",
    "it seems",
    "based on the evidence",
    "appears",
    "likely",
    "probably",
    "may have",
    "might have",
    "seems like",
    "not sure",
    "unclear",
    "cannot confirm",
    "no record",
    "nothing recorded",
    "don't have",
    "do not have",
    "no evidence",
]


def score_case(case: EvalCase, answer: str, evidence: list[dict]) -> tuple[bool, bool, bool, str]:
    """
    Score an answer against a case.

    Returns (correct, evidence_correct, hallucination_free, notes).
    """
    answer_lower = answer.lower()
    notes_parts: list[str] = []

    # 1. Hallucination check — must not contain forbidden claims.
    hallucination_free = True
    for forbidden in case.must_not_claim:
        if forbidden.lower() in answer_lower:
            hallucination_free = False
            notes_parts.append(f"contains forbidden claim: {forbidden!r}")

    # 2. Evidence check.
    evidence_blob = " ".join(
        f"{e.get('title', '')} {e.get('content_excerpt', '')} {e.get('file_path', '')}"
        for e in evidence
    ).lower()

    if case.expect_no_results:
        # Correct behavior: no (or irrelevant) evidence AND an uncertainty marker.
        evidence_correct = True  # not applicable; we check the answer instead
        has_uncertainty = any(m in answer_lower for m in UNCERTAINTY_MARKERS)
        if not has_uncertainty:
            notes_parts.append("expected a 'no results' / uncertainty answer")
        correct = hallucination_free and has_uncertainty
    else:
        # At least one expected source string must appear in the evidence.
        found = [s for s in case.expected_sources if s.lower() in evidence_blob]
        evidence_correct = len(found) == len(case.expected_sources)
        if not evidence_correct:
            missing = [s for s in case.expected_sources if s.lower() not in evidence_blob]
            notes_parts.append(f"missing evidence: {missing}")

        correct = hallucination_free and evidence_correct

        # 3. Uncertainty requirement (for cases that must hedge).
        if case.require_uncertainty:
            has_uncertainty = any(m in answer_lower for m in UNCERTAINTY_MARKERS)
            if not has_uncertainty:
                correct = False
                notes_parts.append("missing required uncertainty marker")

    notes = "; ".join(notes_parts) if notes_parts else "ok"
    return correct, evidence_correct, hallucination_free, notes
