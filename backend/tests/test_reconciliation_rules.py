from __future__ import annotations

from app.engine.reconciliation import run_reconciliation
from app.models import Decision, ExceptionType


def _order(order_id: str, amount: str = "100.00", currency: str = "INR", settlement_by: str = "2026-08-03"):
    return {
        "order_id": order_id,
        "customer_ref": f"CUST-{order_id}",
        "order_amount": amount,
        "currency": currency,
        "order_date": "2026-08-01",
        "expected_settlement_by": settlement_by,
        "status": "paid",
    }


def _txn(txn_id: str, order_ref: str, batch_id: str | None, gross: str, fee: str, net: str, currency: str = "INR"):
    return {
        "txn_id": txn_id,
        "order_ref": order_ref,
        "gross_amount": gross,
        "fee": fee,
        "net_amount": net,
        "currency": currency,
        "txn_date": "2026-08-02",
        "settlement_batch_id": batch_id,
    }


def _settlement(batch_id: str, credited: str, value_date: str = "2026-08-02"):
    return {
        "settlement_batch_id": batch_id,
        "credited_amount": credited,
        "value_date": value_date,
        "utr_reference": f"UTR-{batch_id}",
    }


def test_clean_valid_order_is_reconciled():
    orders = [_order("ORD-100")]
    txns = [_txn("TXN-100", "ORD-100", "SET-100", "100.00", "10.00", "90.00")]
    settlements = [_settlement("SET-100", "90.00")]

    result = run_reconciliation(orders, txns, settlements)
    decisions = {d.order_id: d for d in result.decisions}

    assert decisions["ORD-100"].decision == Decision.RECONCILED
    assert decisions["ORD-100"].exception_type is None


def test_amount_mismatch_is_flagged():
    orders = [_order("ORD-101")]
    txns = [_txn("TXN-101", "ORD-101", "SET-101", "120.00", "10.00", "110.00")]
    settlements = [_settlement("SET-101", "110.00")]

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-101")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.AMOUNT_MISMATCH
    assert decision.rule_id == "R8"


def test_missing_counterpart_is_flagged():
    orders = [_order("ORD-102")]
    txns = []
    settlements = []

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-102")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.MISSING_COUNTERPART
    assert decision.rule_id == "R2"


def test_duplicate_charge_is_flagged():
    orders = [_order("ORD-103")]
    txns = [
        _txn("TXN-103A", "ORD-103", "SET-103", "100.00", "10.00", "90.00"),
        _txn("TXN-103B", "ORD-103", "SET-103", "100.00", "10.00", "90.00"),
    ]
    settlements = [_settlement("SET-103", "180.00")]

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-103")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.DUPLICATE_CHARGE
    assert decision.rule_id == "R3"


def test_currency_mismatch_is_flagged():
    orders = [_order("ORD-104", currency="INR")]
    txns = [_txn("TXN-104", "ORD-104", "SET-104", "100.00", "10.00", "90.00", currency="USD")]
    settlements = [_settlement("SET-104", "90.00")]

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-104")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.CURRENCY_MISMATCH
    assert decision.rule_id == "R7"


def test_date_outside_sla_is_flagged():
    orders = [_order("ORD-105", settlement_by="2026-08-02")]
    txns = [_txn("TXN-105", "ORD-105", "SET-105", "100.00", "10.00", "90.00")]
    settlements = [_settlement("SET-105", "90.00", value_date="2026-08-04")]

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-105")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.DATE_OUTSIDE_SLA
    assert decision.rule_id == "R9"


def test_broken_batch_link_is_flagged():
    orders = [_order("ORD-106")]
    txns = [_txn("TXN-106", "ORD-106", None, "100.00", "10.00", "90.00")]
    settlements = []

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-106")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.BROKEN_BATCH_LINK
    assert decision.rule_id == "R6"


def test_unsafe_batch_mismatch_is_flagged():
    orders = [_order("ORD-107"), _order("ORD-108")]
    txns = [
        _txn("TXN-107", "ORD-107", "SET-107", "100.00", "10.00", "90.00"),
        _txn("TXN-108", "ORD-108", "SET-107", "100.00", "10.00", "90.00"),
    ]
    settlements = [_settlement("SET-107", "150.00")]

    result = run_reconciliation(orders, txns, settlements)
    decision_ids = {d.order_id: d for d in result.decisions}

    assert decision_ids["ORD-107"].decision == Decision.EXCEPTION
    assert decision_ids["ORD-108"].decision == Decision.EXCEPTION
    assert decision_ids["ORD-107"].exception_type == ExceptionType.BATCH_SUM_MISMATCH_UNRESOLVED
    assert decision_ids["ORD-107"].rule_id == "R1"


def test_duplicate_primary_key_still_surfaces_as_malformed_record():
    orders = [_order("ORD-109")]
    txns = [
        _txn("TXN-109", "ORD-109", "SET-109", "100.00", "10.00", "90.00"),
        _txn("TXN-109", "ORD-109", "SET-109", "100.00", "10.00", "90.00"),
    ]
    settlements = [_settlement("SET-109", "90.00")]

    result = run_reconciliation(orders, txns, settlements)
    decision = next(d for d in result.decisions if d.order_id == "ORD-109")

    assert decision.decision == Decision.EXCEPTION
    assert decision.exception_type == ExceptionType.MALFORMED_VALUE
    assert any(exc.exception_type == ExceptionType.DUPLICATE_KEY for exc in result.exceptions)
