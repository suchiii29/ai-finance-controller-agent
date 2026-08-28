from app.data import read_csv
from app.engine.reconciliation import run_reconciliation


# ============================================================
# AGENT SESSION STATE
# ============================================================

_current_result = None
_current_orders = None
_current_txns = None
_current_settlements = None


def get_reconciliation_result(force_refresh=False):
    """
    Returns one consistent reconciliation result and data snapshot
    for the current agent session.

    force_refresh=True starts a completely new reconciliation run.
    """

    global _current_result
    global _current_orders
    global _current_txns
    global _current_settlements

    if _current_result is None or force_refresh:

        # Load all data ONCE for this investigation session
        _current_orders = read_csv("orders.csv")
        _current_txns = read_csv("gateway_transactions.csv")
        _current_settlements = read_csv("bank_settlements.csv")

        # Run deterministic reconciliation
        _current_result = run_reconciliation(
            _current_orders,
            _current_txns,
            _current_settlements,
        )

    return _current_result


def get_current_data():
    """
    Returns the data snapshot associated with the current
    reconciliation run.

    This ensures all tools investigate the same dataset.
    """

    get_reconciliation_result()

    return (
        _current_orders,
        _current_txns,
        _current_settlements,
    )


# ============================================================
# TOOL 1 — RUN / REFRESH RECONCILIATION
# ============================================================

def run_reconciliation_tool():
    """
    Starts a fresh deterministic reconciliation run
    and returns a concise summary.
    """

    result = get_reconciliation_result(force_refresh=True)
    counts = result.runtime_counts

    return {
        "run_id": result.run_id,
        "records_processed": result.records_processed,
        "orders_reconciled": counts["reconciled_count"],
        "orders_requiring_review": counts["exception_count"],
        "total_incidents": len(result.exceptions),
        "exception_breakdown": counts["exception_count_by_type"],
    }


# ============================================================
# TOOL 2 — GET PRIORITY INCIDENTS
# ============================================================

def get_priority_incidents_tool():
    """
    Returns incidents from the current reconciliation run.

    URGENT incidents appear first.
    """

    result = get_reconciliation_result()

    incidents = sorted(
        result.exceptions,
        key=lambda e: 0 if e.severity == "URGENT" else 1,
    )

    return [
        {
            "exception_id": e.exception_id,
            "type": e.exception_type.value,
            "severity": e.severity,
            "reason": e.reason,
            "references": e.refs,
            "affected_orders": e.affected_order_ids or [],
        }
        for e in incidents
    ]


# ============================================================
# TOOL 3 — INVESTIGATE ONE EXCEPTION
# ============================================================

def get_exception_details_tool(exception_id: str):
    """
    Retrieves detailed deterministic evidence for one exception
    from the SAME reconciliation run.
    """

    result = get_reconciliation_result()

    for e in result.exceptions:
        if e.exception_id == exception_id:
            return {
                "exception_id": e.exception_id,
                "type": e.exception_type.value,
                "severity": e.severity,
                "reason": e.reason,
                "references": e.refs,
                "evidence": e.evidence,
                "affected_orders": e.affected_order_ids or [],
            }

    return {
        "error": (
            f"Exception {exception_id} was not found "
            f"in the current reconciliation run."
        )
    }


# ============================================================
# TOOL 4 — GET ORDER DETAILS
# ============================================================

def get_order_details_tool(order_id: str):
    """
    Retrieves the deterministic reconciliation decision
    and evidence for a specific order.
    """

    result = get_reconciliation_result()

    for decision in result.decisions:
        if decision.order_id == order_id:
            return {
                "order_id": decision.order_id,
                "decision": decision.decision.value,
                "reason": decision.decision_reason,
                "rule_id": decision.rule_id,
                "exception_type": (
                    decision.exception_type.value
                    if decision.exception_type
                    else None
                ),
                "evidence": decision.evidence,
                "batch_blocked": decision.batch_blocked,
                "linked_exception_id": (
                    decision.linked_exception_id
                    if decision.linked_exception_id
                    else None
                ),
            }

    return {
        "error": f"Order {order_id} was not found "
                 f"in the current reconciliation run."
    }


# ============================================================
# TOOL 5 — GET BATCH DETAILS
# ============================================================

def get_batch_details_tool(batch_id: str):
    """
    Retrieves transaction and bank settlement evidence for a batch.

    IMPORTANT:
    Uses the SAME data snapshot as the reconciliation run.
    This tool retrieves evidence only and never changes decisions.
    """

    _, txns, settlements = get_current_data()

    batch_transactions = [
        {
            "txn_id": txn.get("txn_id"),
            "order_ref": txn.get("order_ref"),
            "gross_amount": txn.get("gross_amount"),
            "fee": txn.get("fee"),
            "net_amount": txn.get("net_amount"),
            "currency": txn.get("currency"),
            "settlement_batch_id": txn.get(
                "settlement_batch_id"
            ),
        }
        for txn in txns
        if txn.get("settlement_batch_id") == batch_id
    ]

    settlement = next(
        (
            {
                "settlement_batch_id": s.get(
                    "settlement_batch_id"
                ),
                "credited_amount": s.get("credited_amount"),
                "currency": s.get("currency"),
                "value_date": s.get("value_date"),
            }
            for s in settlements
            if s.get("settlement_batch_id") == batch_id
        ),
        None,
    )

    return {
        "batch_id": batch_id,
        "transactions_found": len(batch_transactions),
        "transactions": batch_transactions,
        "settlement": settlement,
    }


def get_transaction_details_tool(txn_id: str):
    """Returns the source transaction and its deterministic decision evidence."""

    result = get_reconciliation_result()
    _, transactions, _ = get_current_data()
    transaction = next(
        (txn for txn in transactions if txn.get("txn_id") == txn_id),
        None,
    )

    if transaction is None:
        return {"error": f"Transaction {txn_id} was not found."}

    related_decisions = [
        {
            "order_id": decision.order_id,
            "decision": decision.decision.value,
            "reason": decision.decision_reason,
            "evidence": decision.evidence,
            "linked_exception_id": decision.linked_exception_id,
        }
        for decision in result.decisions
        if txn_id in decision.evidence
    ]
    related_exceptions = [
        {
            "exception_id": exception.exception_id,
            "type": exception.exception_type.value,
            "severity": exception.severity,
            "reason": exception.reason,
            "evidence": exception.evidence,
        }
        for exception in result.exceptions
        if txn_id in exception.refs
        or any(txn_id in evidence for evidence in exception.evidence)
    ]

    return {
        "txn_id": txn_id,
        "transaction": transaction,
        "related_decisions": related_decisions,
        "related_exceptions": related_exceptions,
    }


def get_reconciliation_summary_tool():
    """Returns deterministic counts for the current reconciliation snapshot."""

    result = get_reconciliation_result()
    return {
        "run_id": result.run_id,
        "records_processed": result.records_processed,
        "runtime_counts": result.runtime_counts,
        "total_incidents": len(result.exceptions),
    }