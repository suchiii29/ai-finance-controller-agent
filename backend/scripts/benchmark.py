"""Run the complete synthetic batch and evaluator benchmark."""

import json
from pathlib import Path
from time import perf_counter

from app.agent import run_batch_controller
from app.evaluation import evaluate_batch, load_ground_truth
from app.tools import get_reconciliation_result


ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "data" / "generated" / "ground_truth.json"


def main():
    started = perf_counter()
    report = run_batch_controller()
    result = get_reconciliation_result()
    evaluation = evaluate_batch(result, load_ground_truth(GROUND_TRUTH))
    output = report.model_dump(mode="json")
    output["evaluation"] = evaluation.model_dump(mode="json")
    output["benchmark_total_seconds"] = perf_counter() - started
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()