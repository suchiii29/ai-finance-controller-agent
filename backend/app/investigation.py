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


# ============================================================
# AI EXPLANATION LAYER
# ============================================================

def explain_investigation(investigation: dict):
    """
    Uses the local AI model only to explain verified evidence.

    The AI does not retrieve financial data and does not make
    reconciliation decisions.
    """

    # Do not ask AI to explain missing or unverified evidence
    if not investigation.get("evidence_verified"):
        return (
            "No verified evidence is available for an AI explanation. "
            "Please check the investigation result."
        )

    llm = ChatOllama(
        model="qwen2.5:3b",
        temperature=0.1,
    )

    verified_data = json.dumps(
        investigation,
        indent=2,
        default=str,
    )

    prompt = f"""
You are FinanceOS, an AI assistant helping a finance operator.

You are given VERIFIED DATA from a deterministic reconciliation system.

STRICT RULES:
1. Only state facts that appear in the VERIFIED DATA.
2. Do not invent transaction IDs, amounts, orders, batches, or causes.
3. Do not change or override any reconciliation decision.
4. Clearly separate FACTS, EVIDENCE, and RECOMMENDED NEXT STEPS.
5. Recommendations must be practical actions for a human operator.
6. If the root cause is not present in the data, explicitly say:
   "The root cause cannot be confirmed from the available evidence."
7. Do not claim that an incident is resolved.

VERIFIED DATA:
{verified_data}

Explain this investigation clearly and concisely.
"""

    response = llm.invoke(prompt)

    return response.content


# ============================================================
# COMPLETE CONTROLLED INVESTIGATION WORKFLOWS
# ============================================================

def investigate_and_explain_highest_priority():
    """
    Full controlled investigation workflow:

    Deterministic engine
            ↓
    Verified evidence
            ↓
    Local AI explanation
    """

    investigation = investigate_highest_priority()

    explanation = explain_investigation(investigation)

    return {
        "investigation": investigation,
        "ai_explanation": explanation,
    }