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

def explain_exception_evidence(incident: dict) -> dict:
    """
    Produces a structured AI explanation for an exception based strictly on verified evidence.
    Does NOT override deterministic decisions or hallucinate references.
    """
    exc_type = incident.get("type", "")
    refs = incident.get("references", [])
    default_rec = get_recommended_action_by_type(exc_type, refs)

    llm = get_llm()
    if llm is None:
        return {
            "available": False,
            "fallback_reason": "AI provider unavailable — deterministic evidence remains available.",
            "explanation": "AI investigation unavailable. Please review deterministic evidence.",
            "summary": incident.get("reason", "Exception surfaced by reconciliation engine"),
            "observed_facts": [incident.get("reason", "Exception surfaced by reconciliation engine")],
            "why_escalated": "Deterministic safety rule triggered.",
            "refusal_rationale": "Deterministic safety rule triggered.",
            "suggested_action": default_rec,
            "recommended_operator_action": default_rec,
        }

    prompt = f"""
You are FinanceOS, an intelligent AI Finance Controller agent.
You are given VERIFIED EVIDENCE for a financial exception that was escalated by a deterministic reconciliation engine.

STRICT SAFETY RULES:
1. State ONLY facts present in the provided evidence.
2. DO NOT invent transaction IDs, amounts, order numbers, or root causes.
3. DO NOT change or override the system's decision (it is ALWAYS an ESCALATED EXCEPTION).
4. Clearly separate OBSERVED FACTS, REASON FOR ESCALATION, and RECOMMENDED HUMAN ACTION.
5. If root cause is unclear, explicitly state: "Root cause cannot be confirmed from available evidence."

EXCEPTION DETAILS:
Exception ID: {incident.get('exception_id')}
Type: {incident.get('type')}
Severity: {incident.get('severity')}
Reason: {incident.get('reason')}
References: {json.dumps(incident.get('references', []))}
Affected Orders: {json.dumps(incident.get('affected_orders', []))}

Provide a concise json response with keys:
"summary": brief summary of the issue (1 sentence)
"observed_facts": list of 2-3 bullet point strings of facts
"why_escalated": 1 sentence explaining why auto-resolution was unsafe
"suggested_action": 1 concise sentence recommending safe next step. Use wording like: "{default_rec}" if appropriate.
"""

    try:
        response = llm.invoke(prompt)
        content = str(response.content).strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        why_esc = parsed.get("why_escalated", parsed.get("refusal_rationale", "Deterministic rules prevented auto-reconciliation."))
        sug_act = parsed.get("suggested_action", parsed.get("recommended_operator_action", default_rec))
        return {
            "available": True,
            "summary": parsed.get("summary", incident.get("reason")),
            "observed_facts": parsed.get("observed_facts", [incident.get("reason")]),
            "why_escalated": why_esc,
            "refusal_rationale": why_esc,
            "suggested_action": sug_act,
            "recommended_operator_action": sug_act,
        }
    except Exception as err:
        logger.warning("Failed to parse LLM structured output for exception %s: %s", incident.get("exception_id"), err)
        return {
            "available": True,
            "summary": incident.get("reason"),
            "observed_facts": [incident.get("reason")],
            "why_escalated": "Deterministic safety rule triggered.",
            "refusal_rationale": "Deterministic safety rule triggered.",
            "suggested_action": default_rec,
            "recommended_operator_action": default_rec,
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


def investigate_and_explain_highest_priority():
    investigation = investigate_highest_priority()
    explanation = explain_investigation(investigation)
    return {
        "investigation": investigation,
        "ai_explanation": explanation,
    }