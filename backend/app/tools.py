from app.data import read_csv
from app.engine.reconciliation import run_reconciliation
from app.ingestion import IngestionSummary


# ============================================================
# AGENT SESSION STATE
# ============================================================

_current_result = None
_current_orders = None
_current_txns = None
_current_settlements = None
_current_ingestion_summary = None
_is_custom_upload = False


def set_custom_batch(orders: list[dict], txns: list[dict], settlements: list[dict], summary: IngestionSummary):
    """
    Sets session state to a custom uploaded financial batch.
    Executes the deterministic reconciliation engine.
    """
    global _current_result, _current_orders, _current_txns, _current_settlements, _current_ingestion_summary, _is_custom_upload, _current_report

    _current_orders = orders
    _current_txns = txns
    _current_settlements = settlements
    _current_ingestion_summary = summary
    _is_custom_upload = True
    _current_report = None

    _current_result = run_reconciliation(orders, txns, settlements)
    return _current_result


def set_demo_batch():
    """
    Sets session state to the synthetic demo batch.
    Executes the deterministic reconciliation engine.
    """
    global _current_result, _current_orders, _current_txns, _current_settlements, _current_ingestion_summary, _is_custom_upload, _current_report

    _current_orders = read_csv("orders.csv")
    _current_txns = read_csv("gateway_transactions.csv")
    _current_settlements = read_csv("bank_settlements.csv")

    total_rows = len(_current_orders) + len(_current_txns) + len(_current_settlements)
    _current_ingestion_summary = IngestionSummary(
        success=True,
        total_rows_received=total_rows,
        usable_orders_count=len(_current_orders),
        usable_transactions_count=len(_current_txns),
        usable_settlements_count=len(_current_settlements),
        ignored_columns=[],
        ignored_rows_count=0,
        detected_record_types=["order", "gateway_transaction", "bank_settlement"],
        validation_warnings=[],
        unprocessable_records=[],
    )
    _is_custom_upload = False
    _current_report = None

    _current_result = run_reconciliation(
        _current_orders,
        _current_txns,
        _current_settlements,
    )
    return _current_result


def get_current_ingestion_summary() -> IngestionSummary | None:
    return _current_ingestion_summary


def is_custom_upload() -> bool:
    return _is_custom_upload


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
    global _is_custom_upload

    if _current_result is None or force_refresh:
        if _is_custom_upload and _current_orders is not None:
            _current_result = run_reconciliation(_current_orders, _current_txns, _current_settlements)
        else:
            set_demo_batch()

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
def build_verified_evidence_fields(exception) -> dict[str, str]:
    """
    Extracts ONLY verified fields that actually exist in the current run snapshot.
    Handles ExceptionRecord objects or dictionaries.
    """
    orders, txns, settlements = get_current_data()
    orders = orders or []
    txns = txns or []
    settlements = settlements or []

    if isinstance(exception, dict):
        scope = exception.get("scope", "ORDER")
        refs = exception.get("references") or exception.get("refs") or []
        affected_orders = exception.get("affected_orders") or exception.get("affected_order_ids") or []
    else:
        scope = getattr(exception, "scope", "ORDER")
        refs = getattr(exception, "refs", []) or []
        affected_orders = getattr(exception, "affected_order_ids", []) or []

    verified: dict[str, str] = {}

    matched_txns = [t for t in txns if t.get("txn_id") in refs]
    matched_orders = [o for o in orders if o.get("order_id") in refs or o.get("order_id") in affected_orders]
    matched_settlements = [s for s in settlements if s.get("settlement_batch_id") in refs]

    if not matched_txns and (refs or affected_orders):
        matched_txns = [t for t in txns if t.get("order_ref") in refs or t.get("order_ref") in affected_orders]

    if scope == "SOURCE_RECORD" or any(r.startswith("TXN-") for r in refs):
        txn = matched_txns[0] if matched_txns else None
        if txn:
            verified["Transaction ID"] = str(txn.get("txn_id") or "Not available in uploaded data")
            verified["Order ID"] = str(txn.get("order_ref") or "Not available in uploaded data")
            verified["Settlement Batch"] = str(txn.get("settlement_batch_id") or "Not available in uploaded data")
            verified["Gross Amount"] = f"{txn.get('currency', 'INR')} {txn.get('gross_amount')}" if txn.get("gross_amount") is not None else "Not available in uploaded data"
            verified["Fee"] = f"{txn.get('currency', 'INR')} {txn.get('fee')}" if txn.get("fee") is not None else "Not available in uploaded data"
            verified["Net Amount"] = f"{txn.get('currency', 'INR')} {txn.get('net_amount')}" if txn.get("net_amount") is not None else "Not available in uploaded data"
            verified["Currency"] = str(txn.get("currency") or "INR")
            verified["Relevant Date"] = str(txn.get("txn_date") or txn.get("timestamp") or "Not available in uploaded data")
        else:
            verified["Transaction ID"] = refs[0] if refs else "Not available in uploaded data"
            verified["Order ID"] = affected_orders[0] if affected_orders else "Not available in uploaded data"
            verified["Settlement Batch"] = "Not available in uploaded data"
            verified["Gross Amount"] = "Not available in uploaded data"
            verified["Fee"] = "Not available in uploaded data"
            verified["Net Amount"] = "Not available in uploaded data"
            verified["Currency"] = "Not available in uploaded data"
            verified["Relevant Date"] = "Not available in uploaded data"

    elif scope == "BATCH" or any(r.startswith("SET-") for r in refs):
        batch_id = refs[0] if refs else "Unknown Batch"
        settlement = matched_settlements[0] if matched_settlements else None
        batch_txns = [t for t in txns if t.get("settlement_batch_id") == batch_id]
        
        verified["Settlement Batch"] = batch_id
        if settlement and settlement.get("credited_amount") is not None:
            verified["Settlement Amount"] = f"{settlement.get('currency', 'INR')} {settlement.get('credited_amount')}"
        else:
            verified["Settlement Amount"] = "Not available in uploaded data"
        verified["Transaction Count"] = str(len(batch_txns))
        verified["Currency"] = str(settlement.get("currency") or "INR") if settlement else "INR"
        verified["Value Date"] = str(settlement.get("value_date") or "Not available in uploaded data") if settlement else "Not available in uploaded data"
        if affected_orders:
            verified["Affected Order IDs"] = ", ".join(affected_orders)

    else:
        order = matched_orders[0] if matched_orders else None
        order_id = order.get("order_id") if order else (refs[0] if refs else "Unknown Order")
        order_txns = [t for t in txns if t.get("order_ref") == order_id]
        batch_ids = list({t.get("settlement_batch_id") for t in order_txns if t.get("settlement_batch_id")})
        settlement_amounts = []
        for b_id in batch_ids:
            s = next((st for st in settlements if st.get("settlement_batch_id") == b_id), None)
            if s and s.get("credited_amount") is not None:
                settlement_amounts.append(f"{s.get('currency', 'INR')} {s.get('credited_amount')}")

        verified["Order ID"] = order_id
        if order and order.get("order_amount") is not None:
            verified["Order Amount"] = f"{order.get('currency', 'INR')} {order.get('order_amount')}"
        else:
            verified["Order Amount"] = "Not available in uploaded data"
        
        verified["Transaction ID(s)"] = ", ".join(t.get("txn_id") for t in order_txns) if order_txns else "Not available in uploaded data"
        verified["Settlement Batch"] = ", ".join(batch_ids) if batch_ids else "Not available in uploaded data"
        verified["Settlement Amount"] = ", ".join(settlement_amounts) if settlement_amounts else "Not available in uploaded data"
        verified["Currency"] = str(order.get("currency") or "INR") if order else "INR"
        if order:
            verified["Relevant Dates"] = f"Ordered: {order.get('order_date', 'N/A')} | Expected SLA: {order.get('expected_settlement_by', 'N/A')}"
        else:
            verified["Relevant Dates"] = "Not available in uploaded data"

    return verified


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
            "scope": e.scope,
            "type": e.exception_type.value,
            "severity": e.severity,
            "reason": e.reason,
            "references": e.refs,
            "affected_orders": e.affected_order_ids or [],
            "verified_fields": build_verified_evidence_fields(e),
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
                "scope": e.scope,
                "type": e.exception_type.value,
                "severity": e.severity,
                "reason": e.reason,
                "references": e.refs,
                "evidence": e.evidence,
                "affected_orders": e.affected_order_ids or [],
                "verified_fields": build_verified_evidence_fields(e),
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


# ============================================================
# TOOL 8 — ANALYZE BATCH EXCEPTIONS (CROSS-RECORD PATTERNS)
# ============================================================

def analyze_batch_exceptions_tool():
    """
    Analyzes all exceptions in the current batch for cross-record patterns.
    Returns verified pattern data suitable for AI synthesis.
    
    This is a bounded, read-only tool that cannot modify reconciliation decisions.
    """
    from app.investigation import analyze_batch_exceptions, explain_cross_exception_patterns
    
    # Get deterministic pattern analysis
    pattern_data = analyze_batch_exceptions()
    
    # Get AI synthesis of patterns
    ai_synthesis = explain_cross_exception_patterns(pattern_data)
    
    # Return unified response
    analysis = pattern_data.get("pattern_analysis", {})
    
    return {
        "status": pattern_data.get("status", "ANALYSIS_COMPLETE"),
        "total_exceptions": analysis.get("total_exceptions", 0),
        "exception_types": analysis.get("grouped_by_type", {}),
        "batches_affected": analysis.get("grouped_by_batch", {}),
        "related_orders": analysis.get("related_orders", []),
        "verified_patterns": analysis.get("verified_patterns", []),
        "ai_analysis_available": ai_synthesis.get("available", False),
        "ai_summary": ai_synthesis.get("summary", ""),
        "ai_cross_record_patterns": ai_synthesis.get("cross_record_patterns", []),
        "ai_possible_causes": ai_synthesis.get("possible_operational_causes", []),
        "ai_recommended_action": ai_synthesis.get("recommended_next_action", ""),
        "ai_confidence": ai_synthesis.get("confidence_in_explanation", "MEDIUM"),
    }


_current_report = None


def get_current_report():
    global _current_report
    return _current_report


def set_current_report(report):
    global _current_report
    _current_report = report