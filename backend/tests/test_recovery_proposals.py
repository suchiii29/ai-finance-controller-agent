from app.investigation import build_recovery_proposal_for_exception


def test_fee_delta_recovery_is_generated_when_verifiable_evidence_exists():
    incident = {
        "exception_id": "EXC-REC-001",
        "type": "AMOUNT_MISMATCH",
        "references": ["TXN-1001"],
        "reason": "Amount or fee arithmetic does not reconcile.",
        "verified_fields": {
            "Order ID": "ORD-1001",
            "Order Amount": "₹500.00",
            "Net Amount": "₹480.00",
            "Settlement Amount": "₹480.00",
            "Currency": "INR",
        },
    }

    proposal = build_recovery_proposal_for_exception(incident)

    assert proposal["proposal_type"] == "POSSIBLE_GATEWAY_FEE_ADJUSTMENT"
    assert proposal["status"] == "PROPOSED"
    assert proposal["requires_human_approval"] is True
    assert proposal["proposed_amount"] == "₹20.00"
    assert "verified difference" in proposal["explanation"].lower()


def test_unsupported_discrepancy_returns_insufficient_evidence():
    incident = {
        "exception_id": "EXC-REC-002",
        "type": "MISSING_COUNTERPART",
        "references": ["ORD-2002"],
        "reason": "No gateway transaction exists for the order.",
        "verified_fields": {
            "Order ID": "ORD-2002",
            "Order Amount": "₹150.00",
        },
    }

    proposal = build_recovery_proposal_for_exception(incident)

    assert proposal["proposal_type"] == "INSUFFICIENT_EVIDENCE_FOR_SAFE_RECOVERY"
    assert proposal["status"] == "INSUFFICIENT_EVIDENCE"
    assert proposal["requires_human_approval"] is True
    assert "insufficient evidence" in proposal["limitations"][0].lower()


def test_proposal_generation_does_not_change_decision_status():
    incident = {
        "exception_id": "EXC-REC-003",
        "type": "BATCH_SUM_MISMATCH_UNRESOLVED",
        "references": ["SET-3001"],
        "reason": "Batch total mismatch; cause cannot be safely isolated.",
        "verified_fields": {
            "Settlement Batch": "SET-3001",
            "Settlement Amount": "₹180.00",
            "Transaction Count": "3",
        },
    }

    proposal = build_recovery_proposal_for_exception(incident)

    assert proposal["requires_human_approval"] is True
    assert proposal["status"] in {"PROPOSED", "INSUFFICIENT_EVIDENCE"}
    assert proposal["proposal_type"] != "RECONCILED"


def test_precision_recall_and_false_positive_count_are_calculated_consistently():
    from app.evaluation import evaluate_batch
    from app.models import BatchResult, Decision, ExceptionType
    from datetime import datetime

    result = BatchResult(
        run_id="RUN-1",
        generated_at=datetime.utcnow(),
        records_processed=4,
        decisions=[
            {"order_id": "ORD-1", "decision": Decision.RECONCILED, "decision_reason": "ok", "rule_id": "R1", "evidence": ["e1"]},
            {"order_id": "ORD-2", "decision": Decision.RECONCILED, "decision_reason": "bad", "rule_id": "R2", "exception_type": ExceptionType.MISSING_COUNTERPART, "evidence": ["e2"]},
            {"order_id": "ORD-3", "decision": Decision.EXCEPTION, "decision_reason": "ok", "rule_id": "R1", "evidence": ["e3"]},
            {"order_id": "ORD-4", "decision": Decision.EXCEPTION, "decision_reason": "bad", "rule_id": "R2", "exception_type": ExceptionType.MISSING_COUNTERPART, "evidence": ["e4"]},
        ],
        exceptions=[],
        runtime_counts={},
        throughput={"records_per_second": 1.0},
    )

    ground_truth = [
        {"order_id": "ORD-1", "expected_outcome": "RECONCILED"},
        {"order_id": "ORD-2", "expected_outcome": "ESCALATE"},
        {"order_id": "ORD-3", "expected_outcome": "RECONCILED"},
        {"order_id": "ORD-4", "expected_outcome": "ESCALATE"},
    ]

    metrics = evaluate_batch(result, ground_truth)

    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.incorrect_auto_resolutions == 1
    assert metrics.safe_resolution_rate == 0.25


def test_processing_time_per_record_is_calculated_safely():
    from app.evaluation import evaluate_batch
    from app.models import BatchResult, Decision
    from datetime import datetime

    result = BatchResult(
        run_id="RUN-2",
        generated_at=datetime.utcnow(),
        records_processed=100,
        decisions=[
            {"order_id": f"ORD-{i}", "decision": Decision.RECONCILED, "decision_reason": "ok", "rule_id": "R1", "evidence": ["e"]}
            for i in range(1, 11)
        ],
        exceptions=[],
        runtime_counts={},
        throughput={"records_per_second": 25.0},
    )

    metrics = evaluate_batch(result, [{"order_id": f"ORD-{i}", "expected_outcome": "RECONCILED"} for i in range(1, 11)])

    assert metrics.total_cases_evaluated == 10
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0

