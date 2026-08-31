from langchain_core.messages import AIMessage

from app import agent


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.invocations = 0

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.invocations += 1
        return next(self.responses)


def tool_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def test_controller_can_iterate_across_tools(monkeypatch):
    fake_llm = FakeLLM(
        [
            tool_call("get_priority_incidents", {}, "call-1"),
            tool_call("get_exception_details", {"exception_id": "EXC-1"}, "call-2"),
            AIMessage(content="Evidence gathered."),
        ]
    )
    monkeypatch.setattr(agent, "get_local_llm", lambda: fake_llm)
    monkeypatch.setitem(
        agent.APPROVED_TOOLS,
        "get_priority_incidents",
        lambda: [{"exception_id": "EXC-1", "severity": "URGENT", "type": "DUPLICATE_KEY", "reason": "Duplicate key."}],
    )
    monkeypatch.setitem(
        agent.APPROVED_TOOLS,
        "get_exception_details",
        lambda exception_id: {"exception_id": exception_id, "evidence": ["txn_id=TXN-1"]},
    )

    response = agent.run_controller_agent("Investigate the critical issue", max_tool_calls=4)

    assert response.controller.status.value == "NEEDS_HUMAN_REVIEW"
    assert response.controller.escalation_required is True
    assert response.controller.financial_action_taken is False
    assert response.controller.tools_used == ["get_priority_incidents", "get_exception_details"]
    assert all("The model cannot change" not in finding for finding in response.controller.findings)
    assert fake_llm.invocations == 3


def test_controller_respects_tool_call_limit(monkeypatch):
    fake_llm = FakeLLM([tool_call("get_reconciliation_summary", {}, f"call-{index}") for index in range(5)])
    monkeypatch.setattr(agent, "get_local_llm", lambda: fake_llm)
    monkeypatch.setitem(agent.APPROVED_TOOLS, "get_reconciliation_summary", lambda: {"total_incidents": 0})

    response = agent.run_controller_agent(max_tool_calls=2)

    assert len(response.controller.tools_used) == 2
    assert any("maximum of 2" in item for item in response.activity_trace)


def test_no_incidents_stays_in_monitoring(monkeypatch):
    response = agent._build_outcome(
        "Assess state",
        [{"tool": "get_priority_incidents", "arguments": {}, "result": []}],
        ["get_priority_incidents"],
        "The model cannot change this result.",
    )

    assert response.status.value == "MONITORING"
    assert response.escalation_required is False
    assert response.financial_action_taken is False


def test_invalid_exception_id_is_rejected_before_tool_execution(monkeypatch):
    fake_llm = FakeLLM(
        [
            tool_call("get_priority_incidents", {}, "call-1"),
            tool_call("get_exception_details", {"exception_id": "DUPLICATE_KEY"}, "call-2"),
            AIMessage(content="No further evidence is available."),
        ]
    )
    detail_calls = []
    monkeypatch.setattr(agent, "get_local_llm", lambda: fake_llm)
    monkeypatch.setitem(
        agent.APPROVED_TOOLS,
        "get_priority_incidents",
        lambda: [{"exception_id": "EXC-1", "severity": "URGENT", "type": "DUPLICATE_KEY"}],
    )
    monkeypatch.setitem(
        agent.APPROVED_TOOLS,
        "get_exception_details",
        lambda exception_id: detail_calls.append(exception_id),
    )

    response = agent.run_controller_agent(max_tool_calls=4)

    assert detail_calls == []
    assert response.controller.tools_used == ["get_priority_incidents"]
    assert any("was not returned" in item for item in response.activity_trace)


def test_llm_failure_returns_honest_fallback(monkeypatch):
    class FailingLLM:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            raise TimeoutError("model timed out")

    monkeypatch.setattr(agent, "get_local_llm", lambda: FailingLLM())

    response = agent.run_controller_agent()

    assert response.controller.status.value == "NEEDS_HUMAN_REVIEW"
    assert response.controller.findings == []
    assert response.controller.financial_action_taken is False
    assert response.controller.escalation_required is True
    assert any("failed safely" in item for item in response.activity_trace)


def test_fake_model_can_choose_different_paths(monkeypatch):
    monkeypatch.setattr(
        agent,
        "get_local_llm",
        lambda: FakeLLM([
            tool_call("get_reconciliation_summary", {}, "summary"),
            AIMessage(content="Monitoring is sufficient."),
        ]),
    )
    monkeypatch.setitem(agent.APPROVED_TOOLS, "get_reconciliation_summary", lambda: {"total_incidents": 0})
    healthy = agent.run_controller_agent(max_tool_calls=2)

    monkeypatch.setattr(
        agent,
        "get_local_llm",
        lambda: FakeLLM([
            tool_call("get_priority_incidents", {}, "priority"),
            AIMessage(content="Escalate."),
        ]),
    )
    monkeypatch.setitem(
        agent.APPROVED_TOOLS,
        "get_priority_incidents",
        lambda: [{"exception_id": "EXC-9", "severity": "URGENT", "type": "ORPHAN_SETTLEMENT", "reason": "Unlinked settlement."}],
    )
    urgent = agent.run_controller_agent(max_tool_calls=2)

    assert healthy.controller.tools_used != urgent.controller.tools_used
    assert urgent.controller.escalation_required is True


def test_batch_controller_processes_all_cases_and_never_takes_action():
    report = agent.run_batch_controller()

    assert report.records_processed >= 50
    assert report.total_cases == 60
    assert report.reconciled_cases + report.escalated_cases == report.total_cases
    assert report.status == "NEEDS_HUMAN_REVIEW"
    assert report.financial_action_taken is False
    states = [event["state"] for event in report.activity_trace]
    assert "OBSERVING" in states
    assert "ANALYZING" in states
    assert "VERIFYING" in states
    assert "NEEDS_HUMAN_REVIEW" in states


# ============================================================
# Ask FinanceOS: Broad Operational Query & Missing Record Tests
# ============================================================

from app.agent import ask_finance_agent
from app.tools import set_demo_batch


def test_ask_financeos_broad_operational_summary():
    """Broad query must return dynamic grounded summary, not generic fallback."""
    set_demo_batch()
    res = ask_finance_agent("What are the biggest issues in this batch?")

    assert res["evidence_verified"] is True
    assert res["type"] == "OPERATIONAL_SUMMARY"
    # Must include batch outcome facts
    assert "Overall Batch Outcome" in res["answer"]
    assert "Reconciled" in res["answer"]
    assert "Escalated" in res["answer"]
    # Must include exception categories
    assert "Exception Categories" in res["answer"] or "Recommended Operator Actions" in res["answer"]
    # Must NOT be the generic fallback strings
    assert "None reported." not in res["answer"]
    assert "could not complete" not in res["answer"]


def test_ask_financeos_operational_summary_variant():
    """Alternate phrasing of broad query also returns grounded operational summary."""
    set_demo_batch()
    res = ask_finance_agent("Give me an operational summary of this run.")

    assert res["evidence_verified"] is True
    assert res["type"] == "OPERATIONAL_SUMMARY"
    assert "Overall Batch Outcome" in res["answer"]


def test_ask_financeos_missing_order_returns_clear_not_found():
    """Non-existent order ID must return a clear not-found response, no hallucination."""
    set_demo_batch()
    res = ask_finance_agent("Why was order ORD-DOESNOTEXIST-99999 escalated?")

    assert res["evidence_verified"] is False
    assert "not found" in res["answer"].lower()
    assert "ORD-DOESNOTEXIST-99999" in res["answer"]


def test_ask_financeos_missing_transaction_returns_clear_not_found():
    """Non-existent transaction ID must return a clear not-found response."""
    set_demo_batch()
    res = ask_finance_agent("Tell me about transaction TXN-DOESNOTEXIST-00000")

    assert res["evidence_verified"] is False
    assert "not found" in res["answer"].lower()


def test_ask_financeos_settlement_batch_lookup_normalization():
    """Settlement batch query with shorthand SET-02 resolves to canonical SET-002."""
    set_demo_batch()
    res = ask_finance_agent("Tell me about settlement batch SET-02")

    assert res["evidence_verified"] is True
    assert res["type"] == "BATCH_LOOKUP"
    assert "SET-002" in res["answer"]


def test_ask_financeos_missing_batch_returns_clear_not_found():
    """Non-existent settlement batch ID returns a clear not-found response."""
    set_demo_batch()
    res = ask_finance_agent("Tell me about settlement batch SETT-DOESNOTEXIST-999")

    assert res["evidence_verified"] is False
    assert "not found" in res["answer"].lower()