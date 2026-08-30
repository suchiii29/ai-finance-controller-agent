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
    get_batch_details_tool,
    get_exception_details_tool,
    get_order_details_tool,
    get_priority_incidents_tool,
    get_reconciliation_summary_tool,
    get_transaction_details_tool,
    run_reconciliation_tool,
    get_reconciliation_result,
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


def ask_finance_agent(question: str):
    """Backward-compatible text response for the existing general agent endpoint."""

    controller = run_controller_agent(question).controller
    return (
        f"STATUS: {controller.status.value}\n"
        f"PRIORITY: {controller.priority_assessment}\n"
        f"FINDINGS: {'; '.join(controller.findings) or 'None reported.'}\n"
        f"NEXT STEPS: {'; '.join(controller.recommended_actions)}"
    )


def run_agent(instruction: str):
    return ask_finance_agent(instruction)


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

    total_seconds = perf_counter() - started
    rec_result = get_reconciliation_result()
    records_processed = rec_result.records_processed
    return BatchControllerReport(
        run_id=rec_result.run_id,
        status=status,
        records_processed=records_processed,
        total_cases=total_cases,
        reconciled_cases=reconciled,
        escalated_cases=escalated,
        match_rate=reconciled / total_cases if total_cases else 0.0,
        unresolved_exceptions=[
            {
                "exception_id": incident["exception_id"],
                "type": incident["type"],
                "severity": incident["severity"],
                "reason": incident["reason"],
                "references": incident["references"],
                "affected_orders": incident.get("affected_orders", []),
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
    )