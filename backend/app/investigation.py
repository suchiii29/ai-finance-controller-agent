import json

from langchain_ollama import ChatOllama

from app.tools import (
    get_priority_incidents_tool,
    get_exception_details_tool,
    get_order_details_tool,
    get_batch_details_tool,
)


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

    details = get_exception_details_tool(
        incident["exception_id"]
    )

    return create_investigation_result(
        investigation_type="HIGHEST_PRIORITY_INCIDENT",
        incident=incident,
        details=details,
    )


def investigate_exception(exception_id: str):
    """
    Retrieves verified evidence for a specific exception.
    """

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

    incident = incidents[0]
    details = get_exception_details_tool(incident["exception_id"])
    return create_investigation_result(
        investigation_type="HIGHEST_PRIORITY_INCIDENT",
        incident=incident,
        details=details,
    )


def investigate_exception(exception_id: str):
    details = get_exception_details_tool(exception_id)
    return create_investigation_result(
        investigation_type="EXCEPTION",
        details=details,
    )


def investigate_order(order_id: str):
    details = get_order_details_tool(order_id)
    return create_investigation_result(
        investigation_type="ORDER",
        details=details,
    )


def investigate_batch(batch_id: str):
    details = get_batch_details_tool(batch_id)
    return create_investigation_result(
        investigation_type="BATCH",
        details=details,
    )


# ============================================================
# AI EXPLANATION LAYER
# ============================================================

def explain_exception_evidence(incident: dict) -> dict:
    """
    Produces a structured AI explanation for an exception based strictly on verified evidence.
    Does NOT override deterministic decisions or hallucinate references.
    """
    llm = get_llm()
    if llm is None:
        return {
            "available": False,
            "fallback_reason": "AI provider unavailable — deterministic evidence remains available.",
            "explanation": "AI investigation unavailable. Please review deterministic evidence.",
            "observed_facts": [incident.get("reason", "Exception surfaced by reconciliation engine")],
            "suggested_action": "Review evidence references manually."
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
"suggested_action": 1 concise sentence recommending safe next step
"""

    try:
        response = llm.invoke(prompt)
        content = str(response.content).strip()
        # Attempt JSON parse or handle text response
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        return {
            "available": True,
            "summary": parsed.get("summary", incident.get("reason")),
            "observed_facts": parsed.get("observed_facts", [incident.get("reason")]),
            "why_escalated": parsed.get("why_escalated", "Deterministic rules prevented auto-reconciliation."),
            "suggested_action": parsed.get("suggested_action", "Review references with finance team.")
        }
    except Exception as err:
        logger.warning("Failed to parse LLM structured output for exception %s: %s", incident.get('exception_id'), err)
        return {
            "available": True,
            "summary": str(response.content) if 'response' in locals() else incident.get("reason"),
            "observed_facts": [incident.get("reason")],
            "why_escalated": "Deterministic safety rule triggered.",
            "suggested_action": "Manually inspect linked transaction and batch records."
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