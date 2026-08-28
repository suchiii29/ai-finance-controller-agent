from pathlib import Path

from app.evaluation import evaluate_batch, load_ground_truth
from app.engine.reconciliation import run_reconciliation
from app.data import read_csv


def test_complete_generated_batch_has_evaluator_metrics():
    root = Path(__file__).resolve().parents[2]
    result = run_reconciliation(
        read_csv("orders.csv"),
        read_csv("gateway_transactions.csv"),
        read_csv("bank_settlements.csv"),
    )
    metrics = evaluate_batch(
        result,
        load_ground_truth(root / "data" / "generated" / "ground_truth.json"),
    )

    assert metrics.total_cases_evaluated == 60
    assert metrics.ground_truth_cases == 60
    assert metrics.correctly_reconciled == 38
    assert metrics.incorrect_auto_resolutions == 0
    assert metrics.precision == 1.0
    assert metrics.exception_escalation_accuracy == 1.0
    assert 0 < metrics.safe_resolution_rate < 1


def test_evaluator_is_separate_from_controller_inference():
    agent_source = (Path(__file__).parents[1] / "app" / "agent.py").read_text()

    assert "app.evaluation" not in agent_source
    assert "ground_truth" not in agent_source