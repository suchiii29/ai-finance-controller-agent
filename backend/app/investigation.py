import json
import logging

from app.llm import get_llm, is_llm_available
from app.tools import (
    get_priority_incidents_tool,
    get_exception_details_tool,
    get_order_details_tool,
    get_batch_details_tool,
)

logger = logging.getLogger(__name__)


# ============================================================
# INVESTIGATION RESPONSE HELPERS
# ============================================================

def create_investigation_result(
    investigation_type: str,
    details: dict,
    incident: dict = None,
):
    """
    Creates a consistent investigation response.

    All financial facts inside this response come from
    deterministic reconciliation tools.
    """
    if details.get("error"):
        return {
            "status": "NOT_FOUND",
            "investigation_type": investigation_type,
            "evidence_verified": False,
            "message": details["error"],
            "incident": incident,
            "details": details,
        }

    return {
        "status": "OPEN",
        "investigation_type": investigation_type,
        "evidence_verified": True,
        "incident": incident,
        "details": details,
    }


# ============================================================
# DETERMINISTIC INVESTIGATION FUNCTIONS
# ============================================================

def investigate_highest_priority():
    """
    Deterministically selects and investigates the highest-priority
    incident from the current reconciliation run.
    """
    incidents = get_priority_incidents_tool()

    if not incidents:
        return {
            "status": "NO_INCIDENTS",
            "investigation_type": "HIGHEST_PRIORITY_INCIDENT",
            "evidence_verified": False,
            "message": "No reconciliation incidents were found.",
            "incident": None,
            "details": None,
        }

    # Priority ordering is determined by the reconciliation system,
    # not by the AI model.
    incident = incidents[0]
    details = get_exception_details_tool(incident["exception_id"])
    return create_investigation_result(
        investigation_type="HIGHEST_PRIORITY_INCIDENT",
        incident=incident,
        details=details,
    )


def investigate_exception(exception_id: str):
    """Retrieves verified evidence for a specific exception."""
    details = get_exception_details_tool(exception_id)
    return create_investigation_result(
        investigation_type="EXCEPTION",
        details=details,
    )


def investigate_order(order_id: str):
    """
    Retrieves the deterministic reconciliation decision
    and evidence for a specific order.
    """
    details = get_order_details_tool(order_id)
    return create_investigation_result(
        investigation_type="ORDER",
        details=details,
    )


def investigate_batch(batch_id: str):
    """
    Retrieves verified transaction and settlement evidence
    for a specific batch.
    """
    details = get_batch_details_tool(batch_id)
    return create_investigation_result(
        investigation_type="BATCH",
        details=details,
    )


# ============================================================
# CROSS-EXCEPTION PATTERN ANALYSIS
# ============================================================

def _analyze_exception_patterns(incidents: list[dict]) -> dict:
    """
    Deterministically analyzes patterns across multiple exceptions.
    Returns verified facts only—no hypotheses.
    """
    if not incidents:
        return {
            "total_exceptions": 0,
            "grouped_by_type": {},
            "grouped_by_batch": {},
            "related_orders": [],
            "amount_anomalies": [],
            "date_clusters": [],
            "verified_patterns": [],
        }

    # GROUP BY EXCEPTION TYPE
    by_type = {}
    for incident in incidents:
        exc_type = incident.get("type", "UNKNOWN")
        if exc_type not in by_type:
            by_type[exc_type] = []
        by_type[exc_type].append(incident)

    # GROUP BY SETTLEMENT BATCH
    by_batch = {}
    for incident in incidents:
        refs = incident.get("references", [])
        for ref in refs:
            if str(ref).startswith("SET-") or str(ref).startswith("BATCH-"):
                if ref not in by_batch:
                    by_batch[ref] = []
                by_batch[ref].append(incident)

    # EXTRACT RELATED ORDERS
    related_orders = set()
    for incident in incidents:
        affected = incident.get("affected_orders", [])
        if isinstance(affected, list):
            related_orders.update(affected)

    # ANALYZE AMOUNT ANOMALIES
    amount_anomalies = []
    for incident in incidents:
        vf = incident.get("verified_fields", {})
        if isinstance(vf, dict):
            order_amt = _parse_decimal_amount(vf.get("Order Amount") or vf.get("Order ID"))
            settlement_amt = _parse_decimal_amount(vf.get("Settlement Amount") or vf.get("Credited Amount"))
            if order_amt is not None and settlement_amt is not None:
                diff = abs(settlement_amt - order_amt)
                if diff > 0.01:
                    amount_anomalies.append({
                        "exception_id": incident.get("exception_id"),
                        "order_id": incident.get("verified_fields", {}).get("Order ID"),
                        "difference": diff,
                        "type": "AMOUNT_DISCREPANCY",
                    })

    # DETECT PATTERNS (FACTS ONLY)
    verified_patterns = []
    
    # Pattern 1: Multiple exceptions of same type
    for exc_type, incs in by_type.items():
        if len(incs) >= 2:
            verified_patterns.append(
                f"VERIFIED FACT: {len(incs)} exceptions of type '{exc_type}' detected."
            )

    # Pattern 2: Exceptions clustered in same batch
    for batch_id, incs in by_batch.items():
        if len(incs) >= 2:
            verified_patterns.append(
                f"VERIFIED FACT: {len(incs)} exceptions linked to settlement batch '{batch_id}'."
            )

    # Pattern 3: Amount discrepancies
    if amount_anomalies:
        verified_patterns.append(
            f"VERIFIED FACT: {len(amount_anomalies)} exceptions contain amount discrepancies."
        )

    return {
        "total_exceptions": len(incidents),
        "grouped_by_type": {k: len(v) for k, v in by_type.items()},
        "grouped_by_batch": {k: len(v) for k, v in by_batch.items()},
        "related_orders": sorted(list(related_orders)),
        "amount_anomalies": amount_anomalies,
        "verified_patterns": verified_patterns,
    }


def analyze_batch_exceptions() -> dict:
    """
    Analyzes all exceptions in the current batch for cross-record patterns.
    Returns deterministic pattern analysis suitable for AI synthesis.
    """
    incidents = get_priority_incidents_tool()
    
    if not incidents:
        return {
            "status": "NO_EXCEPTIONS",
            "investigation_type": "BATCH_EXCEPTION_ANALYSIS",
            "evidence_verified": True,
            "message": "No reconciliation exceptions detected in current batch.",
            "pattern_analysis": {
                "total_exceptions": 0,
                "verified_patterns": [],
            },
        }

    patterns = _analyze_exception_patterns(incidents)
    
    return {
        "status": "PATTERNS_ANALYZED",
        "investigation_type": "BATCH_EXCEPTION_ANALYSIS",
        "evidence_verified": True,
        "total_incidents": len(incidents),
        "pattern_analysis": patterns,
        "raw_incidents": incidents,
    }


def get_recommended_action_by_type(exc_type: str, refs: list[str]) -> str:
    ref_str = f" ({', '.join(refs)})" if refs else ""
    if exc_type == "DUPLICATE_KEY":
        return f"Investigate duplicate transaction records and verify which transaction is authoritative{ref_str}."
    elif exc_type == "ORPHAN_SETTLEMENT":
        return f"Match settlement batch ID against gateway settlement records{ref_str}."
    elif exc_type == "BATCH_SUM_MISMATCH_UNRESOLVED":
        return f"Verify gateway net total against the corresponding bank credit before reconciling affected orders{ref_str}."
    elif exc_type == "BATCH_SUM_MISMATCH_ISOLATED":
        return f"Inspect quarantined transaction amounts in flagged settlement batch{ref_str}."
    elif exc_type == "DATE_OUTSIDE_SLA":
        return f"Review settlement value date against expected settlement SLA{ref_str}."
    elif exc_type == "MISSING_COUNTERPART":
        return f"Investigate the missing gateway/order counterpart{ref_str}."
    elif exc_type == "UNRESOLVABLE_REFERENCE":
        return f"Verify the referenced order/payment record{ref_str}."
    elif exc_type == "BROKEN_BATCH_LINK":
        return f"Verify transaction settlement batch mapping and link{ref_str}."
    elif exc_type == "DUPLICATE_CHARGE":
        return f"Investigate duplicate transaction charges for this order{ref_str}."
    elif exc_type == "MALFORMED_VALUE":
        return f"Inspect malformed amount formats or missing fields in source input{ref_str}."
    elif exc_type == "UNFLAGGED_NEGATIVE_AMOUNT":
        return f"Audit raw input for unflagged negative amounts or unrecorded refund flows{ref_str}."
    elif exc_type == "CURRENCY_MISMATCH":
        return f"Resolve currency code mismatch between order and gateway transaction{ref_str}."
    elif exc_type == "AMOUNT_MISMATCH":
        return f"Investigate amount and fee arithmetic mismatch between order and transaction{ref_str}."
    return f"Review references{ref_str} manually with the finance team."


# ============================================================
# AI EXPLANATION LAYER
# ============================================================

def _parse_decimal_amount(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    text = str(raw_value).strip()
    if not text:
        return None
    match = __import__("re").search(r"[-+]?\d[\d,]*\.?\d*", text)
    if not match:
        return None
    cleaned = match.group(0).replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_currency_amount(value: float | int | str | None) -> str | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return f"₹{numeric:,.2f}"


def build_recovery_proposal_for_exception(incident: dict) -> dict:
    """Build an advisory recovery proposal only from verified fields.

    The deterministic reconciliation engine keeps the financial decision authority.
    Each proposal is advisory, human-approved, and cannot alter the order state.
    """
    incident_id = incident.get("exception_id", "UNKNOWN")
    exc_type = incident.get("type", "")
    refs = incident.get("references", []) or []
    verified_fields = incident.get("verified_fields") or {}
    evidence_refs = refs

    order_amount = None
    net_amount = None
    settlement_amount = None
    if isinstance(verified_fields, dict):
        order_amount = next(
            (
                _parse_decimal_amount(v)
                for k, v in verified_fields.items()
                if str(k).lower() in {"order amount", "order_amount", "gross amount", "gross_amount"}
            ),
            None,
        )
        net_amount = next(
            (
                _parse_decimal_amount(v)
                for k, v in verified_fields.items()
                if str(k).lower() in {"net amount", "net_amount"}
            ),
            None,
        )
        settlement_amount = next(
            (
                _parse_decimal_amount(v)
                for k, v in verified_fields.items()
                if str(k).lower() in {"settlement amount", "settlement_amount", "credited amount", "bank settlement", "bank settlement amount"}
            ),
            None,
        )

    base = {
        "proposal_id": f"PROP-{incident_id}",
        "exception_id": incident_id,
        "proposal_type": "NOT_APPLICABLE",
        "status": "NOT_APPLICABLE",
        "verified_facts": [],
        "proposed_amount": None,
        "explanation": "No safe automated recovery proposal available.",
        "recommended_action": get_recommended_action_by_type(exc_type, refs),
        "confidence": "Low",
        "limitations": ["No safe automated recovery proposal available."],
        "requires_human_approval": True,
        "evidence_refs": evidence_refs,
    }

    if isinstance(verified_fields, dict):
        for key in [
            "Order ID",
            "Order Amount",
            "Net Amount",
            "Settlement Amount",
            "Gross Amount",
            "Settlement Batch",
            "Currency",
        ]:
            if key in verified_fields and verified_fields[key] not in (None, "", "Not available in uploaded data"):
                base["verified_facts"].append(f"{key}: {verified_fields[key]}")

    if exc_type == "AMOUNT_MISMATCH" and order_amount is not None and net_amount is not None:
        difference = abs(order_amount - net_amount)
        if difference > 0.01:
            base.update(
                {
                    "proposal_type": "POSSIBLE_GATEWAY_FEE_ADJUSTMENT",
                    "status": "PROPOSED",
                    "verified_facts": base["verified_facts"] or [
                        f"Order amount {order_amount} and net amount {net_amount} captured in verified evidence."
                    ],
                    "proposed_amount": _format_currency_amount(difference),
                    "explanation": (
                        f"The verified difference between the order and net amount is {difference:.2f}. "
                        "This is consistent with a gateway or fee deduction, but the engine has not automatically posted or reconciled it."
                    ),
                    "recommended_action": "Review gateway fee records and approve an adjusting entry only if independently verified.",
                    "confidence": "High",
                    "limitations": [
                        "Proposal is advisory only. Human approval is required.",
                        "The available evidence supports a fee-style delta, but does not prove the final accounting treatment.",
                    ],
                    "requires_human_approval": True,
                }
            )
            return base

    if exc_type in {"BATCH_SUM_MISMATCH_UNRESOLVED", "BATCH_SUM_MISMATCH_ISOLATED", "BROKEN_BATCH_LINK", "ORPHAN_SETTLEMENT"}:
        if settlement_amount is not None and order_amount is not None:
            residual = abs(settlement_amount - order_amount)
            base.update(
                {
                    "proposal_type": "REVIEW_BATCH_SETTLEMENT_LINK",
                    "status": "PROPOSED",
                    "proposed_amount": _format_currency_amount(residual),
                    "explanation": (
                        "Verified settlement and order evidence indicate a residual amount in the batch. "
                        "The recommendation is to review batch membership and seek confirmation before any adjustment is approved."
                    ),
                    "recommended_action": "Review settlement batch membership and confirm whether a missing or duplicate transaction caused the residual.",
                    "confidence": "Medium",
                    "limitations": [
                        "Proposal is advisory only. Human approval is required.",
                        "The current evidence identifies a likely residual, but does not prove the missing entry or duplicate scenario.",
                    ],
                    "requires_human_approval": True,
                }
            )
            return base

    base.update(
        {
            "proposal_type": "INSUFFICIENT_EVIDENCE_FOR_SAFE_RECOVERY",
            "status": "INSUFFICIENT_EVIDENCE",
            "explanation": (
                "Insufficient evidence for a safe automated recovery proposal. The current deterministic evidence does not support a safe fee adjustment or batch-level recovery action."
            ),
            "recommended_action": get_recommended_action_by_type(exc_type, refs),
            "confidence": "Low",
            "limitations": [
                "Insufficient evidence for safe recovery.",
                "The available records do not isolate a single verifiable recovery action without operator review.",
            ],
            "requires_human_approval": True,
        }
    )
    return base


def _structured_fallback_for_exception(incident: dict) -> dict:
    exc_type = incident.get("type", "")
    refs = incident.get("references", [])
    default_rec = get_recommended_action_by_type(exc_type, refs)
    verified_fields = incident.get("verified_fields") or {}

    fact_entries = []
    if isinstance(verified_fields, dict):
        for key in [
            "Order ID",
            "Order Amount",
            "Transaction ID",
            "Transaction ID(s)",
            "Settlement Batch",
            "Settlement Amount",
            "Gross Amount",
            "Net Amount",
            "Fee",
            "Relevant Date",
            "Value Date",
        ]:
            if key in verified_fields and verified_fields[key] not in (None, "", "Not available in uploaded data"):
                fact_entries.append(f"{key}: {verified_fields[key]}")

    if not fact_entries:
        fact_entries = [incident.get("reason", "Exception surfaced by reconciliation engine")]

    summary = incident.get("reason", "Exception surfaced by reconciliation engine")
    if not summary.endswith("."):
        summary = f"{summary}."

    discrepancy_analysis = "No numeric discrepancy could be calculated from the available evidence."
    order_amt = None
    settlement_amt = None
    if isinstance(verified_fields, dict):
        order_amt = next(
            (
                _parse_decimal_amount(v)
                for k, v in verified_fields.items()
                if k.lower() in {"order amount", "order_amount", "gross amount", "gross_amount", "gateway amount"}
            ),
            None,
        )
        settlement_amt = next(
            (
                _parse_decimal_amount(v)
                for k, v in verified_fields.items()
                if k.lower() in {"settlement amount", "credited amount", "bank settlement", "bank settlement amount"}
            ),
            None,
        )

    if order_amt is not None and settlement_amt is not None:
        difference = settlement_amt - order_amt
        suffix = "excess" if difference > 0 else "shortfall"
        discrepancy_analysis = (
            f"The available evidence shows a {abs(difference):.2f} difference between the order and settlement values "
            f"({suffix} relative to the order amount)."
        )

    escalation_reason = (
        "Deterministic reconciliation rules blocked auto-reconciliation because the engine classified this "
        "order as an EXCEPTION requiring operator review."
    )
    structured = {
        "summary": summary,
        "verified_facts": fact_entries[:5],
        "discrepancy_analysis": discrepancy_analysis,
        "possible_causes": [
            "Possible explanation: an unlinked or mismatched settlement entry in the batch.",
            "Possible explanation: a fee, adjustment, or duplicate amount not represented in the currently available records.",
            "Possible explanation: insufficient evidence exists to attribute a single root cause without operator review.",
        ],
        "recommended_action": default_rec,
        "escalation_reason": escalation_reason,
        "available": False,
        "fallback_reason": "AI provider unavailable — deterministic evidence remains available.",
        "explanation": "AI investigation unavailable. Deterministic evidence remains available for operator review.",
        "observed_facts": fact_entries[:5],
        "why_escalated": escalation_reason,
        "refusal_rationale": escalation_reason,
        "suggested_action": default_rec,
        "recommended_operator_action": default_rec,
    }
    return structured


def _validate_structured_ai_output(raw_data: dict, fallback: dict) -> dict:
    if not isinstance(raw_data, dict):
        return fallback

    validated = dict(fallback)
    validated["summary"] = str(raw_data.get("summary") or raw_data.get("headline") or fallback["summary"])
    validated["verified_facts"] = [
        str(item) for item in (raw_data.get("verified_facts") or raw_data.get("observed_facts") or fallback["verified_facts"])
    ]
    validated["discrepancy_analysis"] = str(
        raw_data.get("discrepancy_analysis") or raw_data.get("difference_analysis") or fallback["discrepancy_analysis"]
    )
    validated["possible_causes"] = [
        str(item) for item in (raw_data.get("possible_causes") or fallback["possible_causes"])
    ]
    validated["recommended_action"] = str(
        raw_data.get("recommended_action") or raw_data.get("suggested_action") or raw_data.get("recommended_operator_action") or fallback["recommended_action"]
    )
    validated["escalation_reason"] = str(
        raw_data.get("escalation_reason") or raw_data.get("why_escalated") or raw_data.get("refusal_rationale") or fallback["escalation_reason"]
    )
    validated["available"] = True
    validated["observed_facts"] = validated["verified_facts"]
    validated["why_escalated"] = validated["escalation_reason"]
    validated["refusal_rationale"] = validated["escalation_reason"]
    validated["suggested_action"] = validated["recommended_action"]
    validated["recommended_operator_action"] = validated["recommended_action"]
    return validated


def explain_exception_evidence(incident: dict) -> dict:
    """
    Produces a structured AI explanation for an exception based strictly on verified evidence.
    Does NOT override deterministic decisions or hallucinate references.
    """
    exc_type = incident.get("type", "")
    refs = incident.get("references", [])
    default_rec = get_recommended_action_by_type(exc_type, refs)
    fallback = _structured_fallback_for_exception(incident)

    llm = get_llm()
    if llm is None:
        fallback["available"] = False
        fallback["fallback_reason"] = "AI provider unavailable — deterministic evidence remains available."
        return fallback

    verified_fields = incident.get("verified_fields") or {}
    issue_summary = incident.get("reason", "Exception surfaced by reconciliation engine")
    order_amount = None
    settlement_amount = None
    if isinstance(verified_fields, dict):
        order_amount = next((v for k, v in verified_fields.items() if k.lower() in {"order amount", "order_amount"}), None)
        settlement_amount = next((v for k, v in verified_fields.items() if k.lower() in {"settlement amount", "settlement_amount", "bank settlement", "credited amount"}), None)

    prompt = f"""
You are FinanceOS, an AI investigation assistant working alongside a deterministic reconciliation engine.
Your task is to explain verified exception evidence without changing the financial decision.

STRICT SAFETY RULES:
1. Only state facts present in the provided evidence.
2. Never invent transaction IDs, amounts, order numbers, or root causes.
3. The deterministic engine decides the financial outcome; the AI explains and recommends investigation.
4. Keep the response structured as JSON with these keys:
   summary, verified_facts, discrepancy_analysis, possible_causes, recommended_action, escalation_reason
5. Clearly separate verified facts from possible explanations.
6. If the evidence is insufficient to prove a root cause, say so clearly.
7. If a numerical discrepancy is available, calculate it explicitly and explain it.

EXCEPTION DETAILS:
Exception ID: {incident.get('exception_id')}
Type: {incident.get('type')}
Severity: {incident.get('severity')}
Reason: {incident.get('reason')}
References: {json.dumps(incident.get('references', []), ensure_ascii=False)}
Affected Orders: {json.dumps(incident.get('affected_orders', []), ensure_ascii=False)}
Verified Fields: {json.dumps(verified_fields, ensure_ascii=False, default=str)}
Order Amount: {order_amount}
Settlement Amount: {settlement_amount}

Return valid JSON only.
"""

    try:
        response = llm.invoke(prompt)
        content = str(response.content).strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        validated = _validate_structured_ai_output(parsed, fallback)
        validated["available"] = True
        return validated
    except Exception as err:
        logger.warning("Failed to parse LLM structured output for exception %s: %s", incident.get("exception_id"), err)
        return {
            **fallback,
            "available": True,
            "fallback_reason": "AI output was not valid JSON — deterministic evidence remains available.",
        }


def explain_investigation(investigation: dict):
    if not investigation.get("evidence_verified"):
        return (
            "No verified evidence is available for an AI explanation. "
            "Please check the investigation result."
        )

    llm = get_llm()
    if llm is None:
        return "AI investigation unavailable — deterministic evidence remains available."

    verified_data = json.dumps(investigation, indent=2, default=str)

    prompt = f"""
You are FinanceOS, an AI assistant helping a finance operator.
Given VERIFIED DATA from a deterministic reconciliation system:

STRICT RULES:
1. Only state facts in VERIFIED DATA. Do not invent transaction IDs or amounts.
2. Never override any reconciliation decision.
3. Clearly separate FACTS, EVIDENCE, and RECOMMENDED NEXT STEPS.
4. If root cause is missing, state: "The root cause cannot be confirmed from available evidence."

VERIFIED DATA:
{verified_data}

Explain this investigation clearly and concisely.
"""
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as err:
        return f"AI explanation unavailable due to provider error: {err}"


def _as_list(value, fallback):
    if value is None:
        return list(fallback)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _determine_priority(patterns: dict) -> dict:
    total = patterns.get("total_exceptions", 0)
    grouped_by_type = patterns.get("grouped_by_type", {})
    grouped_by_batch = patterns.get("grouped_by_batch", {})
    amount_anomalies = patterns.get("amount_anomalies", [])
    max_type_count = max(grouped_by_type.values(), default=0)
    max_batch_count = max(grouped_by_batch.values(), default=0)

    if total == 0:
        return {"priority": "LOW", "reason": "No unresolved exceptions were detected in the current batch."}
    if total >= 10 or max_type_count >= 4 or max_batch_count >= 3 or len(amount_anomalies) >= 3:
        return {
            "priority": "HIGH",
            "reason": "Multiple exceptions are concentrated in a narrow set of rules, batches, or amount anomalies and should be reviewed first.",
        }
    if total >= 4 or max_type_count >= 2 or max_batch_count >= 2:
        return {
            "priority": "MEDIUM",
            "reason": "The batch shows operational clustering but no single dominant root cause is yet verified.",
        }
    return {
        "priority": "LOW",
        "reason": "The exception pattern is sparse and does not currently indicate a high-operational-risk cluster.",
    }


def _validate_cross_exception_analysis(raw_data: dict, fallback: dict) -> dict:
    if not isinstance(raw_data, dict):
        return fallback

    validated = dict(fallback)
    validated["summary"] = str(raw_data.get("summary") or fallback["summary"])
    validated["verified_facts"] = _as_list(raw_data.get("verified_facts") or fallback["verified_facts"], fallback["verified_facts"])
    validated["observed_patterns"] = _as_list(raw_data.get("observed_patterns") or raw_data.get("cross_record_patterns") or fallback["observed_patterns"], fallback["observed_patterns"])
    validated["possible_hypotheses"] = _as_list(raw_data.get("possible_hypotheses") or raw_data.get("possible_operational_causes") or fallback["possible_hypotheses"], fallback["possible_hypotheses"])
    validated["recommended_actions"] = _as_list(raw_data.get("recommended_actions") or raw_data.get("recommended_next_action") or fallback["recommended_actions"], fallback["recommended_actions"])
    validated["limitations"] = _as_list(raw_data.get("limitations") or fallback["limitations"], fallback["limitations"])
    priority_obj = raw_data.get("priority_assessment") or fallback["priority_assessment"]
    if isinstance(priority_obj, dict):
        validated["priority_assessment"] = {
            "priority": str(priority_obj.get("priority") or fallback["priority_assessment"]["priority"]),
            "reason": str(priority_obj.get("reason") or fallback["priority_assessment"]["reason"]),
        }
    else:
        validated["priority_assessment"] = {
            "priority": str(priority_obj or fallback["priority_assessment"]["priority"]),
            "reason": fallback["priority_assessment"]["reason"],
        }
    validated["activity_trace"] = _as_list(raw_data.get("activity_trace") or fallback["activity_trace"], fallback["activity_trace"])
    for idx, item in enumerate(validated["possible_hypotheses"]):
        if not item.upper().startswith("POSSIBLE HYPOTHESIS:"):
            validated["possible_hypotheses"][idx] = f"POSSIBLE HYPOTHESIS: {item}"
    for idx, item in enumerate(validated["observed_patterns"]):
        if not item.upper().startswith("OBSERVED PATTERN:"):
            validated["observed_patterns"][idx] = f"OBSERVED PATTERN: {item}"
    return validated


def explain_cross_exception_patterns(pattern_data: dict) -> dict:
    """
    Uses AI to synthesize cross-exception pattern analysis into operational guidance.
    Keeps AI output grounded in verified patterns and facts.
    """
    if not pattern_data or pattern_data.get("status") == "NO_EXCEPTIONS":
        return {
            "available": True,
            "summary": "No exception patterns to analyze.",
            "verified_facts": [],
            "observed_patterns": [],
            "possible_hypotheses": [],
            "priority_assessment": {"priority": "LOW", "reason": "No unresolved exceptions were detected in the current batch."},
            "recommended_actions": ["Continue routine monitoring."],
            "limitations": ["No exceptions detected in current batch."],
            "activity_trace": [
                "Loaded verified exception records.",
                "Grouped records by exception type and settlement batch.",
                "No recurring batch clusters were found.",
                "Generated a no-op grounded investigation summary.",
            ],
        }

    patterns = pattern_data.get("pattern_analysis", {})
    type_breakdown = patterns.get("grouped_by_type", {})
    amount_anomalies = patterns.get("amount_anomalies", [])
    verified_facts = patterns.get("verified_patterns", [])
    priority = _determine_priority(patterns)

    fallback = {
        "available": False,
        "summary": f"Batch contains {patterns.get('total_exceptions', 0)} exceptions across {len(type_breakdown)} types.",
        "verified_facts": verified_facts,
        "observed_patterns": [
            f"OBSERVED PATTERN: Type breakdown: {type_breakdown}",
            f"OBSERVED PATTERN: Affected orders: {len(patterns.get('related_orders', []))} unique orders",
        ],
        "possible_hypotheses": [
            "POSSIBLE HYPOTHESIS: Multiple exceptions suggest a batch-level processing anomaly.",
            "POSSIBLE HYPOTHESIS: Clustering by exception type indicates a systemic rule-trigger condition.",
            "POSSIBLE HYPOTHESIS: Cross-record patterns may reflect a settlement or data quality issue upstream.",
        ],
        "priority_assessment": priority,
        "recommended_actions": [
            "Review the highest-volume exception type and settlement batch before any consequential operator action.",
            "Compare batch totals and linked records to verify whether the issue is concentrated in one settlement flow.",
        ],
        "limitations": [
            "AI synthesis not available; deterministic pattern facts above remain valid.",
            "Root cause attribution requires operator context and domain knowledge.",
            "Patterns reflect the current batch only and do not prove a systemic issue.",
        ],
        "activity_trace": [
            "Loaded verified exception records.",
            "Grouped records by exception type and settlement batch.",
            "Identified recurring clusters across the current batch.",
            "Generated grounded investigation hypotheses without altering reconciliation decisions.",
            "Ranked operator priorities based on volume and concentration.",
        ],
    }

    llm = get_llm()
    if llm is None:
        fallback["available"] = False
        fallback["fallback_reason"] = "AI provider unavailable — deterministic pattern facts above remain available."
        return fallback

    verified_facts_str = "\n".join(verified_facts)
    type_breakdown_str = ", ".join(f"{t}: {c}" for t, c in type_breakdown.items()) or "None"
    prompt = f"""
You are FinanceOS, an AI investigation assistant.
Your job is to analyze multiple verified exception records together and prioritize investigation work.

CRITICAL SAFETY RULES:
1. Only use facts present in the verified data below.
2. Keep all hypotheses clearly labeled as "POSSIBLE HYPOTHESIS:".
3. Keep all observed patterns clearly labeled as "OBSERVED PATTERN:".
4. Never invent IDs, amounts, or evidence.
5. Never change any reconciliation decision.
6. Never claim a hypothesis is a fact.
7. Return valid JSON with keys: summary, verified_facts, observed_patterns, possible_hypotheses, priority_assessment, recommended_actions, limitations, activity_trace.

VERIFIED FACTS:
{verified_facts_str}

VERIFIED BREAKDOWN:
- Total exceptions: {patterns.get('total_exceptions', 0)}
- Exception types: {type_breakdown_str}
- Related orders affected: {len(patterns.get('related_orders', []))}
- Amount discrepancies found: {len(amount_anomalies)}
- Batches affected: {patterns.get('grouped_by_batch', {})}

Return only JSON.
"""

    try:
        response = llm.invoke(prompt)
        content = str(getattr(response, "content", response)).strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        validated = _validate_cross_exception_analysis(
            parsed,
            fallback,
        )
        validated["available"] = True
        return validated
    except Exception as err:
        logger.warning("Failed to parse cross-exception pattern synthesis: %s", err)
        fallback["available"] = True
        fallback["fallback_reason"] = "AI synthesis not available; deterministic patterns above remain valid."
        return fallback


def build_cross_exception_analysis(incidents: list[dict] | None = None) -> dict:
    """Build a strict, read-only cross-exception analysis from verified incident data."""
    source_incidents = incidents if incidents is not None else get_priority_incidents_tool()
    if not source_incidents:
        return {
            "available": True,
            "summary": "No exception patterns to analyze.",
            "verified_facts": [],
            "observed_patterns": [],
            "possible_hypotheses": [],
            "priority_assessment": {"priority": "LOW", "reason": "No unresolved exceptions were detected in the current batch."},
            "recommended_actions": ["Continue routine monitoring."],
            "limitations": ["No exceptions detected in current batch."],
            "activity_trace": [
                "Loaded verified exception records.",
                "Grouped records by exception type and settlement batch.",
                "No recurring batch clusters were found.",
                "Generated a no-op grounded investigation summary.",
            ],
        }
    pattern_data = analyze_batch_exceptions()
    return explain_cross_exception_patterns(pattern_data)


def investigate_and_explain_highest_priority():
    investigation = investigate_highest_priority()
    explanation = explain_investigation(investigation)
    return {
        "investigation": investigation,
        "ai_explanation": explanation,
    }


def investigate_and_explain_batch_patterns():
    """
    Complete batch-level investigation: pattern analysis + AI synthesis.
    """
    pattern_data = analyze_batch_exceptions()
    pattern_synthesis = explain_cross_exception_patterns(pattern_data)
    return {
        "batch_analysis": pattern_data,
        "ai_pattern_synthesis": pattern_synthesis,
    }