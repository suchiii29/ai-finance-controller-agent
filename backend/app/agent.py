import json
import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from langchain_core.messages import ToolMessage

from app.llm import get_llm, is_llm_available

from app.models import BatchControllerReport, ControllerOutcome, ControllerResponse, ControllerStatus
from app.tools import (
    analyze_batch_exceptions_tool,
    get_batch_details_tool,
    get_exception_details_tool,
    get_order_details_tool,
    get_priority_incidents_tool,
    get_reconciliation_summary_tool,
    get_transaction_details_tool,
    run_reconciliation_tool,
    get_reconciliation_result,
    get_current_ingestion_summary,
    get_current_data,
    is_custom_upload,
)

MAX_TOOL_CALLS = 6
MAX_INVALID_TOOL_REQUESTS = 2
MODEL_TIMEOUT_SECONDS = 20
CONTROLLER_GOAL = (
    "Assess the current reconciliation state, prioritize operational risks, "
    "gather only the evidence needed, and recommend safe human next steps."
)

APPROVED_TOOLS: dict[str, Callable[..., Any]] = {
    "run_reconciliation": run_reconciliation_tool,
    "get_reconciliation_summary": get_reconciliation_summary_tool,
    "analyze_batch_exceptions": analyze_batch_exceptions_tool,
    "get_priority_incidents": get_priority_incidents_tool,
    "get_exception_details": get_exception_details_tool,
    "get_order_details": get_order_details_tool,
    "get_batch_details": get_batch_details_tool,
    "get_transaction_details": get_transaction_details_tool,
}

SYSTEM_PROMPT = """
You are the FinanceOS Finance Controller Agent. Your operational goal is to
assess verified reconciliation state and prepare safe human-operable next
steps. You are an investigation coordinator, not a payment or ledger system.

Use the approved read-only tools to observe state and gather evidence. Choose
the next tool based on the returned evidence; do not follow a fixed sequence.

Approved tools:
- get_reconciliation_summary: Get overall batch metrics and exception counts.
- analyze_batch_exceptions: Analyze cross-record patterns across all exceptions.
- get_priority_incidents: Get high-priority exceptions requiring review.
- get_exception_details: Get detailed evidence for a specific exception.
- get_order_details: Get reconciliation decision for a specific order.
- get_batch_details: Get settlement batch details and linkage analysis.
- get_transaction_details: Get gateway transaction and related evidence.

Stop when the evidence is sufficient or when more evidence cannot establish a
safe conclusion. You may call at most the tool-call limit supplied by the
runtime. Never invent IDs, amounts, causes, or statuses. Never change or
override deterministic decisions, and never claim a financial action was
taken. Unknown root causes must remain unknown.
"""


logger = logging.getLogger(__name__)


def get_local_llm():
    """Return the centralized LLM instance or raise if unavailable."""
    llm = get_llm()
    if llm is None:
        raise RuntimeError("LLM provider is not available")
    return llm


def _tool_description(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    function.__name__ = name
    function.__doc__ = function.__doc__ or f"Read-only FinanceOS tool: {name}."
    return function


def _build_outcome(
    goal: str,
    tool_results: list[dict[str, Any]],
    tools_used: list[str],
    model_summary: str,
) -> ControllerOutcome:
    incidents: list[dict[str, Any]] = []
    priority_observed = False
    for result in tool_results:
        value = result.get("result")
        if result["tool"] == "get_priority_incidents" and isinstance(value, list):
            incidents = value
            priority_observed = True
            break

    urgent = [incident for incident in incidents if incident.get("severity") == "URGENT"]
    if not priority_observed:
        status = ControllerStatus.NEEDS_HUMAN_REVIEW
        priority = "Priority incidents were not observed within the controller tool-call limit."
        actions = ["Review the reconciliation state manually before taking consequential action."]
        uncertainties = ["The controller lacks sufficient evidence to assess incident priority."]
        escalation_required = True
    elif not incidents:
        status = ControllerStatus.MONITORING
        priority = "No reconciliation incidents were returned by the deterministic engine."
        actions = ["Continue routine monitoring and run the next scheduled reconciliation."]
        uncertainties = []
        escalation_required = False
    elif urgent:
        status = ControllerStatus.NEEDS_HUMAN_REVIEW
        priority = f"{len(urgent)} urgent incident(s) require attention before routine review items."
        actions = [
            "Review the verified evidence for the highest-priority incident.",
            "Hold any consequential financial adjustment until a finance operator approves it.",
        ]
        uncertainties = ["Root cause is not established unless explicitly present in verified evidence."]
        escalation_required = True
    else:
        status = ControllerStatus.OPEN
        priority = f"{len(incidents)} review incident(s) are open; none are marked urgent."
        actions = ["Assign the highest-priority review incident to a finance operator."]
        uncertainties = ["Root cause is not established unless explicitly present in verified evidence."]
        escalation_required = False

    findings = [
        f"{incident.get('severity', 'UNKNOWN')} {incident.get('type', 'UNKNOWN')}: "
        f"{incident.get('reason', 'No reason provided by the engine.')}"
        for incident in incidents[:3]
    ]
    return ControllerOutcome(
        status=status,
        goal=goal,
        priority_assessment=priority,
        findings=findings,
        verified_evidence=tool_results,
        tools_used=tools_used,
        recommended_actions=actions,
        escalation_required=escalation_required,
        uncertainties=uncertainties,
        financial_action_taken=False,
    )


def _observed_references(tool_results: list[dict[str, Any]], key: str) -> set[str]:
    """Collect identifiers exposed by earlier successful evidence results."""

    references: set[str] = set()
    for item in tool_results:
        result = item.get("result")
        values = result if isinstance(result, list) else [result]
        for value in values:
            if isinstance(value, dict):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    references.add(candidate)
                for nested_key in ("references", "refs", "affected_orders"):
                    nested = value.get(nested_key, [])
                    if key in {"order_id", "batch_id", "txn_id"} and isinstance(nested, list):
                        references.update(item for item in nested if isinstance(item, str))
    return references


def _validate_tool_arguments(
    name: str,
    arguments: dict[str, Any],
    tool_results: list[dict[str, Any]],
) -> str | None:
    """Reject model guesses that were not returned by the evidence layer."""

    required_keys = {
        "get_exception_details": ("exception_id", "exception_id"),
        "get_order_details": ("order_id", "order_id"),
        "get_batch_details": ("batch_id", "batch_id"),
        "get_transaction_details": ("txn_id", "txn_id"),
    }
    contract = required_keys.get(name)
    if contract is None:
        return None
    argument_key, result_key = contract
    value = arguments.get(argument_key)
    if not isinstance(value, str) or not value:
        return f"{name} requires a non-empty {argument_key}."
    if value not in _observed_references(tool_results, result_key):
        return f"{argument_key} {value!r} was not returned by an earlier evidence tool."
    return None


def run_controller_agent(goal: str = CONTROLLER_GOAL, max_tool_calls: int = MAX_TOOL_CALLS) -> ControllerResponse:
    """Run the bounded observe-plan-investigate-assess controller loop."""

    max_tool_calls = max(1, min(max_tool_calls, MAX_TOOL_CALLS))
    trace = ["Controller goal received: assess reconciliation risk and next steps."]
    tool_results: list[dict[str, Any]] = []
    tools_used: list[str] = []
    invalid_requests = 0
    timings: dict[str, float] = {}
    request_started = perf_counter()
    messages: list[Any] = [
        ("system", SYSTEM_PROMPT),
        ("human", f"Operational goal: {goal}\nTool-call limit: {max_tool_calls}"),
    ]

    try:
        model_started = perf_counter()
        llm = get_local_llm().bind_tools(
            [_tool_description(name, function) for name, function in APPROVED_TOOLS.items()]
        )
        timings["model_initialization_seconds"] = perf_counter() - model_started
        model_summary = ""
        for _ in range(max_tool_calls):
            inference_started = perf_counter()
            response = llm.invoke(messages)
            inference_seconds = perf_counter() - inference_started
            timings["last_llm_inference_seconds"] = inference_seconds
            timings["llm_calls"] = timings.get("llm_calls", 0) + 1
            logger.info("controller LLM inference took %.3fs", inference_seconds)
            messages.append(response)
            calls = getattr(response, "tool_calls", []) or []
            if not calls:
                model_summary = str(getattr(response, "content", "")).strip()
                trace.append("Controller stopped: model determined that available evidence was sufficient.")
                break

            for call in calls:
                if len(tools_used) >= max_tool_calls:
                    break
                name = call.get("name", "")
                arguments = call.get("args") or {}
                function = APPROVED_TOOLS.get(name)
                if function is None:
                    trace.append(f"Rejected unapproved tool request: {name or 'unknown'}.")
                    continue
                validation_error = _validate_tool_arguments(name, arguments, tool_results)
                if validation_error:
                    invalid_requests += 1
                    trace.append(f"Rejected invalid evidence request: {validation_error}")
                    messages.append(
                        ToolMessage(
                            content=json.dumps({"error": validation_error}),
                            tool_call_id=call.get("id", name),
                        )
                    )
                    if invalid_requests >= MAX_INVALID_TOOL_REQUESTS:
                        trace.append("Controller stopped safely after repeated invalid evidence requests.")
                        break
                    continue
                tool_started = perf_counter()
                try:
                    result = function(**arguments)
                except Exception as error:
                    result = {"error": f"Tool failed safely: {error}"}
                tool_seconds = perf_counter() - tool_started
                timings["last_tool_seconds"] = tool_seconds
                logger.info("controller tool %s took %.3fs", name, tool_seconds)
                tools_used.append(name)
                tool_results.append({"tool": name, "arguments": arguments, "result": result})
                trace.append(f"Executed read-only tool: {name}.")
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, default=str),
                        tool_call_id=call.get("id", name),
                    )
                )
            if invalid_requests >= MAX_INVALID_TOOL_REQUESTS:
                break
        else:
            trace.append(f"Controller stopped at the maximum of {max_tool_calls} tool calls.")

        if not tools_used:
            trace.append("No verified evidence was retrieved from the approved tool layer.")
        outcome = _build_outcome(goal, tool_results, tools_used, model_summary)
        if outcome.escalation_required:
            trace.append("Urgent deterministic evidence requires human review.")
        timings["total_controller_seconds"] = perf_counter() - request_started
        logger.info("total controller request took %.3fs", timings["total_controller_seconds"])
        return ControllerResponse(controller=outcome, activity_trace=trace, timings=timings)
    except Exception as error:
        trace.append("Controller unavailable: local model or tool orchestration failed safely.")
        outcome = ControllerOutcome(
            status=ControllerStatus.NEEDS_HUMAN_REVIEW,
            goal=goal,
            priority_assessment="The controller could not complete its assessment.",
            findings=[],
            verified_evidence=tool_results,
            tools_used=tools_used,
            recommended_actions=["Retry the controller assessment or review reconciliation manually."],
            escalation_required=True,
            uncertainties=[f"Controller error: {error}"],
            financial_action_taken=False,
        )
        timings["total_controller_seconds"] = perf_counter() - request_started
        logger.info("total controller request failed after %.3fs", timings["total_controller_seconds"])
        return ControllerResponse(controller=outcome, activity_trace=trace, timings=timings)


def get_broad_operational_summary_text(rec_result) -> tuple[str, dict[str, Any]]:
    total_orders = len(rec_result.decisions)
    reconciled_orders = sum(1 for d in rec_result.decisions if d.decision.value == "RECONCILED")
    escalated_orders = total_orders - reconciled_orders
    safe_rate = (reconciled_orders / total_orders * 100.0) if total_orders > 0 else 0.0

    total_incidents = len(rec_result.exceptions)
    urgent_incidents = sum(1 for e in rec_result.exceptions if (getattr(e.severity, 'value', e.severity) == "URGENT"))
    review_incidents = total_incidents - urgent_incidents

    category_counts = {}
    for e in rec_result.exceptions:
        exc_type = e.exception_type.value if hasattr(e.exception_type, "value") else str(e.exception_type)
        category_counts[exc_type] = category_counts.get(exc_type, 0) + 1

    cat_lines = "\n".join(f"{cat} — {cnt}" for cat, cnt in category_counts.items()) if category_counts else "None"

    from app.investigation import get_recommended_action_by_type
    actions = []
    seen_types = set()
    for e in rec_result.exceptions:
        exc_type = e.exception_type.value if hasattr(e.exception_type, "value") else str(e.exception_type)
        if exc_type not in seen_types:
            seen_types.add(exc_type)
            actions.append(get_recommended_action_by_type(exc_type, e.refs))
        if len(actions) >= 4:
            break

    if not actions:
        actions = ["Continue routine monitoring; no unresolved exception incidents detected."]

    ingestion = get_current_ingestion_summary()
    ingestion_lines = ""
    if ingestion:
        ingestion_lines = (
            f"\nIngestion Context\n\n"
            f"Raw rows received: {ingestion.total_rows_received}\n"
            f"Usable orders: {ingestion.usable_orders_count}\n"
            f"Gateway transactions: {ingestion.usable_transactions_count}\n"
            f"Bank settlements: {ingestion.usable_settlements_count}\n"
            f"Ignored columns: {', '.join(ingestion.ignored_columns) if ingestion.ignored_columns else 'None'}\n"
            f"Unprocessable rows: {len(ingestion.unprocessable_records)}"
        )

    findings_lines = "\n\n".join(
        f"[{e.exception_id}] ({getattr(e.severity, 'value', e.severity)}) {e.reason}"
        for e in rec_result.exceptions[:4]
    ) if rec_result.exceptions else "All deterministic checks passed without exception."

    ans = (
        f"Overall Batch Outcome\n\n"
        f"Reconciled\n{reconciled_orders} of {total_orders} orders\n\n"
        f"Escalated\n{escalated_orders} orders\n\n"
        f"Safe resolution rate\n{safe_rate:.2f}%\n\n"
        f"Exception Overview\n\n"
        f"{escalated_orders} escalated orders contain {total_incidents} exception incidents:\n"
        f"{urgent_incidents} urgent and {review_incidents} review-level.\n\n"
        f"Exception Categories\n\n"
        f"{cat_lines}\n\n"
        f"Operational Findings\n\n"
        f"{findings_lines}\n\n"
        f"Recommended Operator Actions\n\n" +
        "\n\n".join(act for act in actions) +
        ingestion_lines
    )

    details = {
        "run_id": rec_result.run_id,
        "reconciled_orders": reconciled_orders,
        "total_orders": total_orders,
        "escalated_orders": escalated_orders,
        "safe_resolution_rate": safe_rate,
        "total_incidents": total_incidents,
        "urgent_incidents": urgent_incidents,
        "review_incidents": review_incidents,
        "category_counts": category_counts,
        "findings": [
            {
                "exception_id": e.exception_id,
                "severity": getattr(e.severity, 'value', e.severity),
                "reason": e.reason
            }
            for e in rec_result.exceptions
        ],
        "recommended_actions": actions,
        "ingestion": {
            "total_rows_received": ingestion.total_rows_received,
            "usable_orders_count": ingestion.usable_orders_count,
            "usable_transactions_count": ingestion.usable_transactions_count,
            "usable_settlements_count": ingestion.usable_settlements_count,
            "ignored_columns": ingestion.ignored_columns,
            "ignored_rows_count": ingestion.ignored_rows_count,
            "unprocessable_records_count": len(ingestion.unprocessable_records),
        } if ingestion else None
    }

    return ans, details


import re

def ask_finance_agent(question: str) -> dict[str, Any]:
    """
    Answers questions dynamically against the CURRENT reconciliation run.
    Uses deterministic backend tool retrieval first before falling back to LLM.
    """
    q_lower = question.lower()
    rec_result = get_reconciliation_result()

    # Generic Transaction Failure lookup
    if "why couldn't this transaction be reconciled" in q_lower or "why couldn't the transaction be reconciled" in q_lower:
        failed_txn_id = None
        for exc in rec_result.exceptions:
            for ref in exc.refs:
                if ref.startswith("TXN-"):
                    failed_txn_id = ref
                    break
            if failed_txn_id:
                break
        
        if not failed_txn_id:
            exception_decisions = [d for d in rec_result.decisions if d.decision.value == "EXCEPTION"]
            for d in exception_decisions:
                for ev in d.evidence:
                    if ev.startswith("txn_id="):
                        failed_txn_id = ev.split("=")[1]
                        break
                if failed_txn_id:
                    break
        
        if failed_txn_id:
            question = f"Why couldn't transaction {failed_txn_id} be reconciled?"
        else:
            return {
                "question": question,
                "answer": "No transaction exceptions or failures were found in the current run.",
                "evidence_verified": True,
                "type": "TRANSACTION_LOOKUP",
            }

    # 1. Transaction ID Lookup (normalized TXN-008 -> TXN-0008)
    txn_match = re.search(r'\b(TXN-[\w-]+)\b', question, re.IGNORECASE) or re.search(r'\btransaction\s+([\w-]+)\b', question, re.IGNORECASE)
    if txn_match:
        raw_id = txn_match.group(1)
        if not raw_id.upper().startswith("TXN-") and txn_match.lastindex and txn_match.lastindex >= 2:
            raw_id = txn_match.group(2)
        raw_id = raw_id.upper()
        if not raw_id.startswith("TXN-"):
            raw_id = f"TXN-{raw_id}"

        orders_data, txns_data, settlements_data = get_current_data()
        normalized_id = raw_id
        if txns_data:
            found = False
            for t in txns_data:
                tid = str(t.get("txn_id", "")).upper()
                if tid == raw_id:
                    normalized_id = t.get("txn_id")
                    found = True
                    break
            if not found:
                m = re.match(r'^TXN-(\d+)$', raw_id, re.IGNORECASE)
                if m:
                    num_val = int(m.group(1))
                    for t in txns_data:
                        tid = str(t.get("txn_id", "")).upper()
                        tm = re.match(r'^TXN-(\d+)$', tid, re.IGNORECASE)
                        if tm and int(tm.group(1)) == num_val:
                            normalized_id = t.get("txn_id")
                            found = True
                            break

        details = get_transaction_details_tool(normalized_id)
        if details.get("error"):
            return {
                "question": question,
                "answer": f"{raw_id} was not found in the current batch.",
                "evidence_verified": False,
                "type": "TRANSACTION_LOOKUP",
                "details": details,
            }
        
        tx = details["transaction"]
        order_ref = tx.get("order_ref") or "None"
        batch_id = tx.get("settlement_batch_id") or "None"
        gross = tx.get("gross_amount", "N/A")
        fee = tx.get("fee", "N/A")
        net = tx.get("net_amount", "N/A")
        curr = tx.get("currency", "INR")

        ans = (
            f"Transaction {normalized_id} verified evidence:\n"
            f"• Transaction ID: {normalized_id}\n"
            f"• Linked Order Reference: {order_ref}\n"
            f"• Settlement Batch: {batch_id}\n"
            f"• Amounts: Gross={curr} {gross}, Fee={curr} {fee}, Net={curr} {net}\n"
        )
        
        decisions = details.get("related_decisions", [])
        exceptions = details.get("related_exceptions", [])
        
        if decisions:
            ans += "\nRelated Reconciliation Decisions:\n"
            for d in decisions:
                ans += f"• Order {d['order_id']} is {d['decision']}. Reason: {d['reason']}\n"
                
        if exceptions:
            ans += "\nRelated Exceptions:\n"
            for e in exceptions:
                ans += f"• [{e['exception_id']}] Severity: {e['severity']} | Type: {e['type']} | Reason: {e['reason']}\n"
                
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "TRANSACTION_LOOKUP",
            "details": details,
        }

    # 2. Order ID Lookup
    order_match = re.search(r'\b(ORD-[\w-]+)\b', question, re.IGNORECASE) or re.search(r'\border\s+([\w-]+)\b', question, re.IGNORECASE)
    if order_match:
        raw_id = order_match.group(1)
        if not raw_id.upper().startswith("ORD-") and order_match.lastindex and order_match.lastindex >= 2:
            raw_id = order_match.group(2)
        raw_id = raw_id.upper()
        if not raw_id.startswith("ORD-"):
            raw_id = f"ORD-{raw_id}"

        orders_data, txns_data, settlements_data = get_current_data()
        normalized_id = raw_id
        if orders_data:
            found = False
            for o in orders_data:
                oid = str(o.get("order_id", "")).upper()
                if oid == raw_id:
                    normalized_id = o.get("order_id")
                    found = True
                    break
            if not found:
                m = re.match(r'^ORD-(\d+)$', raw_id, re.IGNORECASE)
                if m:
                    num_val = int(m.group(1))
                    for o in orders_data:
                        oid = str(o.get("order_id", "")).upper()
                        om = re.match(r'^ORD-(\d+)$', oid, re.IGNORECASE)
                        if om and int(om.group(1)) == num_val:
                            normalized_id = o.get("order_id")
                            found = True
                            break

        details = get_order_details_tool(normalized_id)
        if details.get("error"):
            return {
                "question": question,
                "answer": f"{raw_id} was not found in the current batch.",
                "evidence_verified": False,
                "type": "ORDER_LOOKUP",
                "details": details,
            }
        
        status_str = "Reconciled" if details["decision"] == "RECONCILED" else "Escalated"
        ans = (
            f"Order {normalized_id} status: {status_str}.\n"
            f"Rule applied: {details['rule_id']} — {details['reason']}.\n"
            f"Evidence: {', '.join(details['evidence'])}."
        )
        if details.get("linked_exception_id"):
            ans += f" Linked Exception ID: {details['linked_exception_id']}."
            
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "ORDER_LOOKUP",
            "details": details,
        }

    # 2b. Settlement Batch ID Lookup (normalized SET-02 -> SETT-0002)
    sett_match = re.search(r'\b(SETT?-\d+)\b', question, re.IGNORECASE) or re.search(r'\bsettlement\s+batch\s+([\w-]+)\b', question, re.IGNORECASE)
    if sett_match:
        raw_id = sett_match.group(1)
        if not raw_id.upper().startswith(("SET-", "SETT-")) and sett_match.lastindex and sett_match.lastindex >= 2:
            raw_id = sett_match.group(2)
        raw_id = raw_id.upper()
        if not raw_id.startswith(("SET-", "SETT-")):
            raw_id = f"SET-{raw_id}"

        orders_data, txns_data, settlements_data = get_current_data()
        normalized_id = raw_id
        known_batches = set()
        if settlements_data:
            known_batches.update(s.get("settlement_batch_id") for s in settlements_data if s.get("settlement_batch_id"))
        if txns_data:
            known_batches.update(t.get("settlement_batch_id") for t in txns_data if t.get("settlement_batch_id"))

        found = False
        for b_id in known_batches:
            if b_id.upper() == raw_id:
                normalized_id = b_id
                found = True
                break
        if not found:
            m = re.match(r'^SETT?-(\d+)$', raw_id, re.IGNORECASE)
            if m:
                num_val = int(m.group(1))
                for b_id in known_batches:
                    bm = re.match(r'^SETT?-(\d+)$', b_id, re.IGNORECASE)
                    if bm and int(bm.group(1)) == num_val:
                        normalized_id = b_id
                        found = True
                        break

        details = get_batch_details_tool(normalized_id)
        if not details.get("transactions") and not details.get("settlement"):
            return {
                "question": question,
                "answer": f"Settlement batch {raw_id} was not found in the current batch.",
                "evidence_verified": False,
                "type": "BATCH_LOOKUP",
                "details": details,
            }

        s_info = details.get("settlement")
        tx_count = details.get("transactions_found", 0)
        s_amount = f"{s_info.get('currency', 'INR')} {s_info.get('credited_amount')}" if s_info and s_info.get('credited_amount') is not None else "No bank credit record"
        v_date = s_info.get('value_date', 'N/A') if s_info else 'N/A'

        ans = (
            f"Settlement Batch {normalized_id} verified evidence:\n"
            f"• Batch ID: {normalized_id}\n"
            f"• Linked Transactions Count: {tx_count}\n"
            f"• Bank Settlement Amount: {s_amount}\n"
            f"• Value Date: {v_date}\n"
        )
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "BATCH_LOOKUP",
            "details": details,
        }

    # 3. Incident vs Record counts query
    if any(k in q_lower for k in ("how many exception incidents", "incidents and orders", "affected orders count", "incident count")):
        total_orders = len(rec_result.decisions)
        reconciled_orders = sum(1 for d in rec_result.decisions if d.decision.value == "RECONCILED")
        escalated_orders = total_orders - reconciled_orders
        total_incidents = len(rec_result.exceptions)
        urgent_incidents = sum(1 for e in rec_result.exceptions if (getattr(e.severity, 'value', e.severity) == "URGENT"))
        review_incidents = total_incidents - urgent_incidents
        
        ans = f"{escalated_orders} escalated orders contain {total_incidents} exception incidents: {urgent_incidents} urgent and {review_incidents} review-level."
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "INCIDENT_COUNT",
            "details": {
                "escalated_orders": escalated_orders,
                "total_incidents": total_incidents,
                "urgent_incidents": urgent_incidents,
                "review_incidents": review_incidents,
            },
        }

    # 4. Safe Resolution Rate query
    if any(k in q_lower for k in ("resolution rate", "safe resolution rate", "match rate", "reconciliation rate")):
        total_orders = len(rec_result.decisions)
        reconciled_orders = sum(1 for d in rec_result.decisions if d.decision.value == "RECONCILED")
        rate = (reconciled_orders / total_orders * 100.0) if total_orders > 0 else 0.0
        ans = f"The safe resolution rate for the current batch is {rate:.2f}% ({reconciled_orders} of {total_orders} orders safely reconciled)."
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "RESOLUTION_RATE",
            "details": {"safe_resolution_rate": rate, "reconciled": reconciled_orders, "total": total_orders},
        }

    # 5. Escalated / Attention Orders Query
    if any(k in q_lower for k in (
        "show me all escalated orders",
        "show escalated orders",
        "which orders require",
        "orders requiring attention",
        "escalated orders list",
        "escalated orders",
    )):
        escalated_decisions = [d for d in rec_result.decisions if d.decision.value == "EXCEPTION"]
        if not escalated_decisions:
            ans = "No orders currently require operator attention. All orders in this batch are safely reconciled."
        else:
            ans = f"Found {len(escalated_decisions)} order(s) requiring operator attention:\n" + "\n".join(
                f"• Order {d.order_id}: {d.decision_reason} (Rule: {d.rule_id})" for d in escalated_decisions[:10]
            )
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "ESCALATED_ORDERS",
            "details": [d.model_dump(mode="json") for d in escalated_decisions],
        }

    # 6. Pattern-level investigation queries
    pattern_query = any(k in q_lower for k in (
        "patterns across the exceptions",
        "what is the biggest operational risk in this batch",
        "which exceptions should finance investigate first",
        "do these discrepancies appear related",
        "what is the likely operational issue affecting the most records",
        "related exceptions",
        "cross-exception",
        "exception patterns"
    ))

    if pattern_query and rec_result.exceptions:
        from app.investigation import explain_cross_exception_patterns, analyze_batch_exceptions
        pattern_data = analyze_batch_exceptions()
        batch_analysis = explain_cross_exception_patterns(pattern_data)
        summary_lines = [
            "AI Cross-Exception Investigation",
            f"Priority: {batch_analysis.get('priority_assessment', {}).get('priority', 'MEDIUM')}",
            f"Reason: {batch_analysis.get('priority_assessment', {}).get('reason', 'Batch pattern review completed.')}",
            "",
            "Verified Facts",
        ]
        for fact in batch_analysis.get("verified_facts", [])[:5]:
            summary_lines.append(f"• {fact}")
        summary_lines.extend(["", "Observed Patterns"])
        for pattern in batch_analysis.get("observed_patterns", [])[:5]:
            summary_lines.append(f"• {pattern}")
        summary_lines.extend(["", "Possible Hypotheses"])
        for h in batch_analysis.get("possible_hypotheses", [])[:5]:
            summary_lines.append(f"• {h}")
        summary_lines.extend(["", "Recommended Next Actions"])
        for act in batch_analysis.get("recommended_actions", [])[:5]:
            summary_lines.append(f"• {act}")
        summary_lines.extend(["", "Limitations"])
        for limit in batch_analysis.get("limitations", [])[:3]:
            summary_lines.append(f"• {limit}")
        ans = "\n".join(summary_lines)
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "CROSS_EXCEPTION_ANALYSIS",
            "details": batch_analysis,
        }

    # 7. Broad Operational Queries (Summary, biggest issues, operator attention)
    if any(k in q_lower for k in (
        "biggest issue", "biggest issues", "main issue", "requires attention", "operator attention",
        "operational summary", "batch summary", "summary of this run", "overview of this run",
        "how did reconciliation go", "what needs attention", "summary of the batch", "biggest problem"
    )):
        ans, summary_details = get_broad_operational_summary_text(rec_result)
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "OPERATIONAL_SUMMARY",
            "details": summary_details,
        }

    # 8. Ingestion Summary Query
    if any(k in q_lower for k in ("ingest", "ingested", "ignored", "usable records", "columns ignored", "unprocessable")):
        summary = get_current_ingestion_summary()
        if not summary:
            return {
                "question": question,
                "answer": "No ingestion summary is available for the current batch.",
                "evidence_verified": False,
                "type": "INGESTION_SUMMARY",
            }
        ans = (
            f"Ingestion Summary for Current Batch:\n"
            f"• Total Rows Received: {summary.total_rows_received}\n"
            f"• Usable Records: {summary.usable_orders_count} orders, {summary.usable_transactions_count} gateway transactions, {summary.usable_settlements_count} bank settlements\n"
            f"• Ignored Columns: {', '.join(summary.ignored_columns) if summary.ignored_columns else 'None'}\n"
            f"• Ignored Rows: {summary.ignored_rows_count}\n"
            f"• Unprocessable Records: {len(summary.unprocessable_records)}"
        )
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "INGESTION_SUMMARY",
            "details": summary.model_dump(mode="json"),
        }

    # 10. Amount Mismatches Query
    if "amount mismatch" in q_lower or "mismatches" in q_lower:
        mismatches = [
            d for d in rec_result.decisions 
            if d.exception_type and d.exception_type.value == "AMOUNT_MISMATCH"
        ]
        if not mismatches:
            ans = "No amount mismatches were found in the current reconciliation batch."
        else:
            ans = f"Found {len(mismatches)} amount mismatch exception(s):\n" + "\n".join(
                f"• Order {m.order_id}: {m.decision_reason} (Rule: {m.rule_id})" for m in mismatches[:10]
            )
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "AMOUNT_MISMATCHES",
            "details": [m.model_dump(mode="json") for m in mismatches],
        }

    # 11. Settlement Batch Integrity Query
    if any(k in q_lower for k in ("settlement batch", "batch integrity", "failed batch", "batch fail")):
        batch_exceptions = [
            e for e in rec_result.exceptions 
            if e.scope == "BATCH" or e.exception_type.value in ("BATCH_SUM_MISMATCH_UNRESOLVED", "BATCH_SUM_MISMATCH_ISOLATED", "ORPHAN_SETTLEMENT")
        ]
        if not batch_exceptions:
            ans = "All settlement batches passed integrity checks successfully."
        else:
            ans = f"Found {len(batch_exceptions)} settlement batch exception(s):\n" + "\n".join(
                f"• [{e.exception_id}] Severity: {e.severity} | Type: {e.exception_type.value} | Reason: {e.reason}"
                for e in batch_exceptions[:10]
            )
        return {
            "question": question,
            "answer": ans,
            "evidence_verified": True,
            "type": "BATCH_INTEGRITY",
            "details": [e.model_dump(mode="json") for e in batch_exceptions],
        }

    # 12. Fallback to Agent Controller Reasoning
    controller_resp = run_controller_agent(question)
    controller = controller_resp.controller
    findings_str = "; ".join(controller.findings) if controller.findings else ""
    actions_str = "; ".join(controller.recommended_actions) if controller.recommended_actions else ""

    if not findings_str or "None reported" in findings_str or "could not complete" in findings_str:
        ans, _ = get_broad_operational_summary_text(rec_result)
    else:
        ans = (
            f"Operational Status: {controller.status.value}\n"
            f"Priority Assessment: {controller.priority_assessment}\n"
            f"Verified Findings: {findings_str}\n"
            f"Recommended Action: {actions_str}"
        )

    return {
        "question": question,
        "answer": ans,
        "evidence_verified": True,
        "type": "CONTROLLER_AGENT",
        "details": controller.model_dump(mode="json"),
    }


def run_agent(instruction: str) -> dict:
    """Run a single Ask FinanceOS query and return the grounded response."""
    res = ask_finance_agent(instruction)
    return res


def run_batch_controller() -> BatchControllerReport:
    """Close one complete batch loop with deterministic finance authority.

    The optional LLM controller remains available for adaptive evidence review,
    but batch reconciliation never depends on model availability.
    """

    started = perf_counter()
    trace: list[dict[str, Any]] = []

    def event(state: str, action: str, tool: str | None = None, outcome: str = ""):
        trace.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": state,
            "action": action,
            "tool": tool,
            "outcome": outcome,
        })

    event("OBSERVING", "Loaded the complete current batch.")
    deterministic_started = perf_counter()
    result = get_reconciliation_summary_tool()
    priority = get_priority_incidents_tool()
    deterministic_seconds = perf_counter() - deterministic_started
    event(
        "ANALYZING",
        "Observed deterministic reconciliation summary and priority incidents.",
        "get_reconciliation_summary + get_priority_incidents",
        f"{result['total_incidents']} unresolved incidents found",
    )

    reconciled = sum(decision.decision.value == "RECONCILED" for decision in get_reconciliation_result().decisions)
    total_cases = len(get_reconciliation_result().decisions)
    escalated = total_cases - reconciled
    status = "COMPLETED" if not priority else "NEEDS_HUMAN_REVIEW"
    event(
        "VERIFYING",
        "Verified final deterministic decisions across every order in the batch.",
        "get_reconciliation_summary",
        f"{reconciled} reconciled, {escalated} escalated",
    )
    # ── AI exception investigation ──────────────────────────────
    ai_available = is_llm_available()
    fallback_used = False
    llm_calls = 0
    exception_explanations: dict[str, dict[str, Any]] = {}

    if ai_available and priority:
        from app.investigation import explain_exception_evidence

        event(
            "INVESTIGATING",
            "AI investigating escalated exceptions using structured evidence.",
            tool="explain_exception_evidence",
        )
        for incident in priority[:8]:
            exc_id = incident["exception_id"]
            try:
                explanation = explain_exception_evidence(incident)
                exception_explanations[exc_id] = explanation
                llm_calls += 1
            except Exception as exc:
                logger.warning("AI explanation failed for %s: %s", exc_id, exc)
                exception_explanations[exc_id] = {
                    "available": False,
                    "fallback_reason": "AI investigation unavailable — deterministic evidence remains available.",
                }
                fallback_used = True

        event(
            "ANALYZING",
            f"AI investigated {len(exception_explanations)} exceptions without changing deterministic decisions.",
            outcome=f"{llm_calls} AI calls succeeded" if llm_calls else "AI unavailable; deterministic report retained",
        )
    elif not ai_available:
        fallback_used = True
        event(
            "ANALYZING",
            "AI provider unavailable — deterministic evidence report retained.",
            outcome="fallback",
        )

    if priority:
        event("NEEDS_HUMAN_REVIEW", "Preserved unresolved incidents for finance operators.", outcome=f"{len(priority)} incidents")
    else:
        event("COMPLETED", "Completed batch with no unresolved incidents.")

    cross_exception_analysis = None
    if priority:
        from app.investigation import analyze_batch_exceptions, explain_cross_exception_patterns
        pattern_data = analyze_batch_exceptions()
        cross_exception_analysis = explain_cross_exception_patterns(pattern_data)

    total_seconds = perf_counter() - started
    rec_result = get_reconciliation_result()
    records_processed = rec_result.records_processed
    # match_rate is strictly: reconciled_orders / total_order_decisions
    # total_cases = len(decisions) = number of usable orders processed
    safe_match_rate = reconciled / total_cases if total_cases else 0.0
    return BatchControllerReport(
        run_id=rec_result.run_id,
        status=status,
        records_processed=records_processed,
        total_cases=total_cases,
        reconciled_cases=reconciled,
        escalated_cases=escalated,
        match_rate=safe_match_rate,
        unresolved_exceptions=[
            {
                "exception_id": incident["exception_id"],
                "type": incident["type"],
                "severity": incident["severity"],
                "reason": incident["reason"],
                "references": incident["references"],
                "affected_orders": incident.get("affected_orders", []),
                "verified_fields": incident.get("verified_fields", {}),
                "ai_investigation": exception_explanations.get(incident["exception_id"]),
            }
            for incident in priority
        ],
        activity_trace=trace,
        timings={
            "deterministic_reconciliation_seconds": deterministic_seconds,
            "controller_total_seconds": total_seconds,
            "records_per_second": records_processed / max(total_seconds, 0.0001),
        },
        throughput=rec_result.throughput,
        llm_calls=llm_calls,
        tool_calls=2 + llm_calls,
        ai_available=ai_available,
        fallback_used=fallback_used,
        financial_action_taken=False,
        is_custom_batch=is_custom_upload(),
        ingestion_summary=get_current_ingestion_summary().model_dump(mode="json") if get_current_ingestion_summary() else None,
        cross_exception_analysis=cross_exception_analysis,
    )