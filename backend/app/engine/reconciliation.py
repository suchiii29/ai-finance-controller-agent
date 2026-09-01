from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import logging
from time import perf_counter
from uuid import uuid4

from app.models import (
    BatchResult,
    Decision,
    ExceptionRecord,
    ExceptionType,
    OrderDecision,
)

logger = logging.getLogger(__name__)


def D(value) -> Decimal:
    return Decimal(str(value))


def parse_amount(value) -> Decimal:
    if value is None or str(value).strip() == "":
        raise InvalidOperation("blank amount")
    return D(value)


def parse_date(value) -> date:
    if value is None or str(value).strip() == "":
        raise ValueError("blank date")
    val_str = str(value).strip().split("T")[0].split(" ")[0]
    return date.fromisoformat(val_str)


def make_exception(
    scope: str,
    refs: list[str],
    exception_type: ExceptionType,
    reason: str,
    evidence: list[str],
    severity: str = "REVIEW",
    affected_order_ids: list[str] | None = None,
) -> ExceptionRecord:
    return ExceptionRecord(
        exception_id=f"EXC-{uuid4().hex[:8]}",
        scope=scope,
        refs=refs,
        exception_type=exception_type,
        reason=reason,
        evidence=evidence,
        severity=severity,
        affected_order_ids=affected_order_ids,
    )


def run_reconciliation(orders, txns, settlements):
    """
    Deterministic five-stage reconciliation pipeline.

    No LLM participates in validation, grouping, batch integrity,
    evidence assembly, or financial decisions.
    """

    started = perf_counter()
    exceptions: list[ExceptionRecord] = []

    # ============================================================
    # STAGE 1 — RETRIEVAL & INGESTION VALIDATION
    # ============================================================

    validation_status: dict[int, str] = {}
    validation_exception_type: dict[int, ExceptionType] = {}

    txn_id_counts = Counter(
        txn.get("txn_id")
        for txn in txns
        if txn.get("txn_id") not in (None, "")
    )
    duplicate_ids = {
        txn_id for txn_id, count in txn_id_counts.items()
        if count > 1
    }

    for index, txn in enumerate(txns):
        record_id = txn.get("txn_id") or f"row-{index}"
        validation_status[id(txn)] = "OK"

        try:
            gross = parse_amount(txn.get("gross_amount"))
            fee = parse_amount(txn.get("fee"))
            net = parse_amount(txn.get("net_amount"))

            if gross < 0 or fee < 0 or net < 0:
                validation_status[id(txn)] = "MALFORMED"
                validation_exception_type[id(txn)] = (
                    ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT
                )

                exceptions.append(
                    make_exception(
                        "SOURCE_RECORD",
                        [record_id],
                        ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT,
                        "Unexpected negative amount in a schema with no refund flow.",
                        [f"txn_id={record_id}"],
                    )
                )

        except (InvalidOperation, ValueError, TypeError):
            validation_status[id(txn)] = "MALFORMED"
            validation_exception_type[id(txn)] = ExceptionType.MALFORMED_VALUE

            exceptions.append(
                make_exception(
                    "SOURCE_RECORD",
                    [record_id],
                    ExceptionType.MALFORMED_VALUE,
                    "Transaction contains a missing or non-numeric amount.",
                    [f"txn_id={record_id}"],
                )
            )

        # Duplicate primary key overrides validation status to MALFORMED
        # but preserves the duplicate-key source incident separately.
        if txn.get("txn_id") in duplicate_ids:
            validation_status[id(txn)] = "MALFORMED"
            validation_exception_type[id(txn)] = ExceptionType.DUPLICATE_KEY

            exceptions.append(
                make_exception(
                    "SOURCE_RECORD",
                    [record_id],
                    ExceptionType.DUPLICATE_KEY,
                    "Duplicate transaction primary key detected.",
                    [f"txn_id={record_id}"],
                    severity="URGENT",
                )
            )

    # ============================================================
    # STAGE 2 — GROUPING
    # ============================================================

    order_map = {order["order_id"]: order for order in orders}
    candidates = defaultdict(list)

    # Each batch retains two membership lists.
    batch_groups = defaultdict(
        lambda: {
            "trusted_members": [],
            "quarantined_members": [],
        }
    )

    for txn in txns:
        txn_id = txn.get("txn_id") or "unknown"
        order_ref = txn.get("order_ref")
        batch_id = txn.get("settlement_batch_id")

        # 2a — Link transactions to orders
        if order_ref not in order_map:
            exceptions.append(
                make_exception(
                    "SOURCE_RECORD",
                    [txn_id],
                    ExceptionType.UNRESOLVABLE_REFERENCE,
                    "Gateway transaction references an order that does not exist.",
                    [f"order_ref={order_ref}"],
                )
            )
        else:
            candidates[order_ref].append(txn)

        # 2b — Batch grouping.
        # Blank/null batch IDs are intentionally NOT groups.
        if batch_id is None or str(batch_id).strip() == "":
            continue

        if validation_status.get(id(txn)) == "OK":
            batch_groups[batch_id]["trusted_members"].append(txn)
        else:
            batch_groups[batch_id]["quarantined_members"].append(txn)

    settlement_map = {
        settlement["settlement_batch_id"]: settlement
        for settlement in settlements
        if settlement.get("settlement_batch_id") not in (None, "")
    }

    # ============================================================
    # STAGE 2b — ORPHAN SETTLEMENT DETECTION
    # ============================================================

    for batch_id, settlement in settlement_map.items():
        group = batch_groups.get(batch_id)

        if group is None:
            exceptions.append(
                make_exception(
                    "BATCH",
                    [batch_id],
                    ExceptionType.ORPHAN_SETTLEMENT,
                    "Bank settlement has no linked gateway transactions.",
                    [f"batch_id={batch_id}"],
                    severity="URGENT",
                )
            )

    # ============================================================
    # STAGE 3 — BATCH INTEGRITY CHECK
    # ============================================================

    batch_status: dict[str, str] = {}
    isolated_order_ids: set[str] = set()
    batch_exception_id: dict[str, str] = {}

    for batch_id, group in batch_groups.items():
        trusted_members = group["trusted_members"]
        quarantined_members = group["quarantined_members"]
        bank = settlement_map.get(batch_id)

        # A batch without a bank credit cannot be verified.
        if bank is None:
            affected_orders = sorted(
                {
                    txn.get("order_ref")
                    for txn in trusted_members + quarantined_members
                    if txn.get("order_ref") in order_map
                }
            )

            batch_status[batch_id] = "MISMATCH_UNRESOLVED"

            incident = make_exception(
                "BATCH",
                [batch_id],
                ExceptionType.BATCH_SUM_MISMATCH_UNRESOLVED,
                "No bank settlement exists for this gateway settlement batch.",
                [
                    f"batch_id={batch_id}",
                    f"trusted_members={len(trusted_members)}",
                    f"quarantined_members={len(quarantined_members)}",
                ],
                severity="URGENT",
                affected_order_ids=affected_orders,
            )

            exceptions.append(incident)
            batch_exception_id[batch_id] = incident.exception_id
            continue

        # Only trusted members contribute to expected arithmetic.
        try:
            trusted_sum = sum(
                (parse_amount(txn.get("net_amount")) for txn in trusted_members),
                Decimal("0"),
            )
            actual_credit = parse_amount(bank.get("credited_amount"))
        except (InvalidOperation, ValueError, TypeError):
            trusted_sum = None
            actual_credit = None

        if trusted_sum is not None and trusted_sum == actual_credit:
            batch_status[batch_id] = "OK"
            continue

        # Structural isolation:
        # exactly one quarantined member and trusted members are clean
        # (trusted membership itself guarantees validation OK).
        if len(quarantined_members) == 1:
            batch_status[batch_id] = "MISMATCH_ISOLATED"

            isolated_order_ref = quarantined_members[0].get("order_ref")
            if isolated_order_ref in order_map:
                isolated_order_ids.add(isolated_order_ref)

            continue

        # Safety rule: never guess under uncertainty.
        affected_orders = sorted(
            {
                txn.get("order_ref")
                for txn in trusted_members + quarantined_members
                if txn.get("order_ref") in order_map
            }
        )

        batch_status[batch_id] = "MISMATCH_UNRESOLVED"

        incident = make_exception(
            "BATCH",
            [batch_id],
            ExceptionType.BATCH_SUM_MISMATCH_UNRESOLVED,
            "Trusted gateway net total does not equal the bank credit; cause is not safely attributable.",
            [
                f"trusted_sum={trusted_sum}",
                f"actual_credit={actual_credit}",
                f"trusted_members={len(trusted_members)}",
                f"quarantined_members={len(quarantined_members)}",
            ],
            severity="URGENT",
            affected_order_ids=affected_orders,
        )

        exceptions.append(incident)
        batch_exception_id[batch_id] = incident.exception_id

    # ============================================================
    # STAGE 4 + 5 — EVIDENCE ASSEMBLY & STRICT DECISION PRECEDENCE
    # ============================================================

    decisions: list[OrderDecision] = []

    for order in orders:
        order_id = order["order_id"]
        order_candidates = candidates.get(order_id, [])

        evidence = [
            f"order_id={order_id}",
            f"candidate_count={len(order_candidates)}",
        ]

        decision = Decision.RECONCILED
        exception_type = None
        reason = "All deterministic reconciliation checks passed."
        rule_id = "R10"
        batch_blocked = False
        linked_exception_id = None

        # We inspect the candidate's batch only when exactly one exists.
        txn = order_candidates[0] if len(order_candidates) == 1 else None
        batch_id = txn.get("settlement_batch_id") if txn else None

        if txn is not None:
            evidence.extend(
                [
                    f"txn_id={txn.get('txn_id')}",
                    f"batch_id={batch_id or ''}",
                ]
            )

        candidate_malformed = any(
            validation_status.get(id(candidate)) == "MALFORMED"
            for candidate in order_candidates
        )
        malformed_source_type = next(
            (
                validation_exception_type.get(id(candidate), ExceptionType.MALFORMED_VALUE)
                for candidate in order_candidates
                if validation_status.get(id(candidate)) == "MALFORMED"
            ),
            None,
        )

        # --------------------------------------------------------
        # RULE 1 — Unresolved batch block
        # --------------------------------------------------------
        if (
            txn is not None
            and batch_id
            and batch_status.get(batch_id) == "MISMATCH_UNRESOLVED"
        ):
            decision = Decision.EXCEPTION
            exception_type = ExceptionType.BATCH_SUM_MISMATCH_UNRESOLVED
            reason = "Batch integrity check blocks auto-reconciliation."
            rule_id = "R1"
            batch_blocked = True
            linked_exception_id = batch_exception_id.get(batch_id)

        # --------------------------------------------------------
        # RULE 2 — Missing counterpart
        # --------------------------------------------------------
        elif len(order_candidates) == 0:
            decision = Decision.EXCEPTION
            exception_type = ExceptionType.MISSING_COUNTERPART
            reason = "No gateway transaction links to this order."
            rule_id = "R2"

        # --------------------------------------------------------
        # RULE 4 — Malformed transaction (highest precedence within candidate set)
        # --------------------------------------------------------
        elif candidate_malformed:
            exception_type = (
                ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT
                if malformed_source_type == ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT
                else ExceptionType.MALFORMED_VALUE
            )
            decision = Decision.EXCEPTION
            reason = "Linked transaction failed ingestion validation."
            rule_id = "R4"

        # --------------------------------------------------------
        # RULE 3 — Duplicate charge
        # --------------------------------------------------------
        elif len(order_candidates) == 2:
            decision = Decision.EXCEPTION
            exception_type = ExceptionType.DUPLICATE_CHARGE
            reason = "More than one gateway transaction links to this order."
            rule_id = "R3"

        # Defensive handling for unexpected >2 candidates.
        elif len(order_candidates) > 2:
            decision = Decision.EXCEPTION
            exception_type = ExceptionType.DUPLICATE_CHARGE
            reason = "More than one gateway transaction links to this order."
            rule_id = "R3"

        else:
            # Exactly one candidate from here onward.

            # ----------------------------------------------------
            # RULE 4 — Malformed transaction
            # ----------------------------------------------------
            if validation_status.get(id(txn)) == "MALFORMED":
                source_type = validation_exception_type.get(
                    id(txn),
                    ExceptionType.MALFORMED_VALUE,
                )

                exception_type = (
                    ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT
                    if source_type == ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT
                    else ExceptionType.MALFORMED_VALUE
                )

                decision = Decision.EXCEPTION
                reason = "Linked transaction failed ingestion validation."
                rule_id = "R4"

            # ----------------------------------------------------
            # RULE 5 — Isolated batch cause
            # ----------------------------------------------------
            elif (
                order_id in isolated_order_ids
                and batch_id
                and batch_status.get(batch_id) == "MISMATCH_ISOLATED"
            ):
                decision = Decision.EXCEPTION
                exception_type = ExceptionType.BATCH_SUM_MISMATCH_ISOLATED
                reason = (
                    "This order's independently quarantined transaction "
                    "is the isolated structural cause of the batch mismatch."
                )
                rule_id = "R5"

            # ----------------------------------------------------
            # RULE 6 — Broken batch link
            # ----------------------------------------------------
            elif batch_id is None or str(batch_id).strip() == "":
                decision = Decision.EXCEPTION
                exception_type = ExceptionType.BROKEN_BATCH_LINK
                reason = "Transaction has no settlement batch link."
                rule_id = "R6"

            # ----------------------------------------------------
            # RULE 7 — Currency mismatch
            # ----------------------------------------------------
            elif order.get("currency") != txn.get("currency"):
                decision = Decision.EXCEPTION
                exception_type = ExceptionType.CURRENCY_MISMATCH
                reason = "Order and transaction currencies differ."
                rule_id = "R7"

            else:
                try:
                    gross = parse_amount(txn.get("gross_amount"))
                    fee = parse_amount(txn.get("fee"))
                    net = parse_amount(txn.get("net_amount"))
                    order_amount = parse_amount(order.get("order_amount"))

                    # ------------------------------------------------
                    # RULE 8 — Amount mismatch
                    # ------------------------------------------------
                    if gross != order_amount or gross - fee != net:
                        decision = Decision.EXCEPTION
                        exception_type = ExceptionType.AMOUNT_MISMATCH
                        reason = "Amount or fee arithmetic does not reconcile."
                        rule_id = "R8"

                    else:
                        bank = settlement_map.get(batch_id)

                        # --------------------------------------------
                        # RULE 9 — Settlement date outside SLA
                        # --------------------------------------------
                        if bank is None:
                            decision = Decision.EXCEPTION
                            exception_type = (
                                ExceptionType.BATCH_SUM_MISMATCH_UNRESOLVED
                            )
                            reason = (
                                "No bank settlement exists for this "
                                "gateway settlement batch."
                            )
                            rule_id = "R1"
                            batch_blocked = True
                            linked_exception_id = batch_exception_id.get(batch_id)

                        elif (
                            parse_date(bank.get("value_date"))
                            > parse_date(order.get("expected_settlement_by"))
                        ):
                            decision = Decision.EXCEPTION
                            exception_type = ExceptionType.DATE_OUTSIDE_SLA
                            reason = (
                                "Settlement occurred after the allowed "
                                "settlement date."
                            )
                            rule_id = "R9"

                except (InvalidOperation, ValueError, TypeError):
                    decision = Decision.EXCEPTION
                    exception_type = ExceptionType.MALFORMED_VALUE
                    reason = "Required evidence could not be parsed."
                    rule_id = "R4"

        # --------------------------------------------------------
        # Create the OrderDecision
        # --------------------------------------------------------
        order_decision = OrderDecision(
            order_id=order_id,
            decision=decision,
            decision_reason=reason,
            rule_id=rule_id,
            exception_type=exception_type,
            evidence=evidence,
            batch_blocked=batch_blocked,
            linked_exception_id=linked_exception_id,
        )

        decisions.append(order_decision)

        # --------------------------------------------------------
        # Unified exception queue
        #
        # Do NOT duplicate shared batch-level incidents.
        # --------------------------------------------------------
        if (
            decision == Decision.EXCEPTION
            and not batch_blocked
            and exception_type is not None
        ):
            severity = (
                "URGENT"
                if exception_type == ExceptionType.DUPLICATE_KEY
                else "REVIEW"
            )

            exceptions.append(
                make_exception(
                    "ORDER",
                    [order_id],
                    exception_type,
                    reason,
                    evidence,
                    severity=severity,
                    affected_order_ids=None,
                )
            )

    # ============================================================
    # FINAL RESULT
    # ============================================================

    elapsed = perf_counter() - started
    logger.info(
        "deterministic reconciliation took %.3fs for %d records",
        elapsed,
        len(orders) + len(txns) + len(settlements),
    )
    decision_counts = Counter(
        decision.decision.value for decision in decisions
    )

    exception_type_counts = Counter(
        exception.exception_type.value
        for exception in exceptions
    )

    malformed_count = sum(
        1
        for status in validation_status.values()
        if status == "MALFORMED"
    )

    total_records = len(orders) + len(txns) + len(settlements)

    return BatchResult(
        run_id=f"RUN-{uuid4().hex[:8]}",
        generated_at=datetime.utcnow(),
        records_processed=total_records,
        decisions=decisions,
        exceptions=exceptions,
        runtime_counts={
            "total_orders_decided": len(decisions),
            "reconciled_count": decision_counts["RECONCILED"],
            "exception_count": decision_counts["EXCEPTION"],
            "exception_incident_count": len(exceptions),
            "exception_count_by_type": dict(exception_type_counts),
            "malformed_rows_encountered": malformed_count,
            "malformed_rows_surfaced_as_exceptions": sum(
                1
                for exception in exceptions
                if exception.exception_type
                in {
                    ExceptionType.MALFORMED_VALUE,
                    ExceptionType.UNFLAGGED_NEGATIVE_AMOUNT,
                    ExceptionType.DUPLICATE_KEY,
                }
            ),
            "pipeline_errors": 0,
        },
        throughput={
            "seconds": elapsed,
            "records_per_second": total_records / max(elapsed, 0.0001),
        },
    )