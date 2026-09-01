from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Decision(str, Enum):
    RECONCILED = "RECONCILED"
    EXCEPTION = "EXCEPTION"


class ExceptionType(str, Enum):
    MISSING_COUNTERPART = "MISSING_COUNTERPART"
    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"

    MALFORMED_VALUE = "MALFORMED_VALUE"
    UNFLAGGED_NEGATIVE_AMOUNT = "UNFLAGGED_NEGATIVE_AMOUNT"
    DUPLICATE_KEY = "DUPLICATE_KEY"

    BATCH_SUM_MISMATCH_ISOLATED = "BATCH_SUM_MISMATCH_ISOLATED"
    BATCH_SUM_MISMATCH_UNRESOLVED = "BATCH_SUM_MISMATCH_UNRESOLVED"

    BROKEN_BATCH_LINK = "BROKEN_BATCH_LINK"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    DATE_OUTSIDE_SLA = "DATE_OUTSIDE_SLA"

    ORPHAN_SETTLEMENT = "ORPHAN_SETTLEMENT"
    UNRESOLVABLE_REFERENCE = "UNRESOLVABLE_REFERENCE"


class OrderDecision(BaseModel):
    order_id: str
    decision: Decision
    decision_reason: str
    rule_id: str
    exception_type: ExceptionType | None = None
    evidence: list[str] = Field(min_length=1)

    batch_blocked: bool = False
    linked_exception_id: str | None = None

    decided_at: datetime = Field(default_factory=datetime.utcnow)


class ExceptionRecord(BaseModel):
    exception_id: str
    scope: str
    refs: list[str]
    exception_type: ExceptionType
    reason: str
    evidence: list[str] = Field(min_length=1)
    severity: str = "REVIEW"

    # Used by one shared batch-level incident.
    affected_order_ids: list[str] | None = None


class BatchResult(BaseModel):
    run_id: str
    generated_at: datetime
    records_processed: int

    decisions: list[OrderDecision]
    exceptions: list[ExceptionRecord]

    runtime_counts: dict[str, Any]
    throughput: dict[str, float]


class EvaluationMetrics(BaseModel):
    total_cases_evaluated: int
    correctly_reconciled: int
    correctly_escalated: int
    incorrect_auto_resolutions: int
    missed_resolvable_cases: int
    precision: float
    recall: float
    f1: float
    safe_resolution_rate: float
    exception_escalation_accuracy: float
    ground_truth_cases: int


class BatchControllerReport(BaseModel):
    run_id: str
    status: str
    records_processed: int
    total_cases: int
    reconciled_cases: int
    escalated_cases: int
    match_rate: float
    unresolved_exceptions: list[dict[str, Any]] = Field(default_factory=list)
    activity_trace: list[dict[str, Any]] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    throughput: dict[str, float] = Field(default_factory=dict)
    llm_calls: int = 0
    tool_calls: int = 0
    ai_available: bool = False
    fallback_used: bool = False
    financial_action_taken: bool = False
    is_custom_batch: bool = False
    ingestion_summary: dict[str, Any] | None = None
    cross_exception_analysis: dict[str, Any] | None = None
    evaluation: EvaluationMetrics | None = None


class ControllerStatus(str, Enum):
    OPEN = "OPEN"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    MONITORING = "MONITORING"
    RESOLVED_BY_ENGINE = "RESOLVED_BY_ENGINE"


class ControllerOutcome(BaseModel):
    status: ControllerStatus
    goal: str
    priority_assessment: str
    findings: list[str] = Field(default_factory=list)
    verified_evidence: list[dict[str, Any]] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    escalation_required: bool = False
    uncertainties: list[str] = Field(default_factory=list)
    financial_action_taken: bool = False


class ControllerResponse(BaseModel):
    controller: ControllerOutcome
    activity_trace: list[str] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)