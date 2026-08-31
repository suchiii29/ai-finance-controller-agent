"""Evaluator-only metrics for synthetic reconciliation runs.

This module is intentionally separate from the inference and controller paths.
Ground-truth labels are read only by benchmark/evaluation callers.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.data import DATA_DIR
from app.models import BatchResult, EvaluationMetrics


def get_ground_truth_path() -> Path | None:
    """Return the synthetic benchmark ground truth from the canonical demo dataset directory."""
    path = DATA_DIR / "ground_truth.json"
    return path if path.exists() else None


def load_ground_truth(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def evaluate_batch(result: BatchResult, ground_truth: list[dict[str, str]]) -> EvaluationMetrics:
    expected = {item["order_id"]: item["expected_outcome"] for item in ground_truth}
    predictions = {
        decision.order_id: "RECONCILED" if decision.decision.value == "RECONCILED" else "ESCALATE"
        for decision in result.decisions
    }

    cases = len(expected)
    resolved_correct = sum(
        1 for order_id, expected_outcome in expected.items()
        if predictions.get(order_id) == "RECONCILED" and expected_outcome == "RECONCILED"
    )
    escalated_correct = sum(
        1 for order_id, expected_outcome in expected.items()
        if predictions.get(order_id) == "ESCALATE" and expected_outcome == "ESCALATE"
    )
    incorrect_auto_resolutions = sum(
        1 for order_id, expected_outcome in expected.items()
        if predictions.get(order_id) == "RECONCILED" and expected_outcome != "RECONCILED"
    )
    missed_resolvable = sum(
        1 for order_id, expected_outcome in expected.items()
        if predictions.get(order_id) != "RECONCILED" and expected_outcome == "RECONCILED"
    )
    predicted_resolved = sum(value == "RECONCILED" for value in predictions.values())
    actual_resolved = sum(value == "RECONCILED" for value in expected.values())
    actual_exceptions = cases - actual_resolved
    precision = resolved_correct / predicted_resolved if predicted_resolved else 1.0
    recall = resolved_correct / actual_resolved if actual_resolved else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return EvaluationMetrics(
        total_cases_evaluated=cases,
        correctly_reconciled=resolved_correct,
        correctly_escalated=escalated_correct,
        incorrect_auto_resolutions=incorrect_auto_resolutions,
        missed_resolvable_cases=missed_resolvable,
        precision=precision,
        recall=recall,
        f1=f1,
        safe_resolution_rate=resolved_correct / cases if cases else 0.0,
        exception_escalation_accuracy=(
            escalated_correct / actual_exceptions if actual_exceptions else 1.0
        ),
        ground_truth_cases=cases,
    )