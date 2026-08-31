"""
Schema-aware CSV Ingestion module for FinanceOS.

Deterministically inspects headers and rows, maps canonical column aliases,
classifies financial record types (orders, gateway transactions, bank settlements),
ignores irrelevant columns, validates required fields, and provides honest ingestion summaries.
"""

from __future__ import annotations

import csv
import io
from typing import Any
from pydantic import BaseModel, Field


class IngestionSummary(BaseModel):
    success: bool
    total_rows_received: int
    usable_orders_count: int = 0
    usable_transactions_count: int = 0
    usable_settlements_count: int = 0
    ignored_columns: list[str] = Field(default_factory=list)
    ignored_rows_count: int = 0
    detected_record_types: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    unprocessable_records: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None


# Canonical Column Aliases
ALIAS_MAP = {
    # Record type discriminator
    "record_type": ["record_type", "type", "source", "entity", "domain", "record_kind"],
    # Identifiers
    "reference_id": ["reference_id"],
    "order_id": ["order_id", "order_number", "order_no", "order"],
    "order_reference": ["order_reference", "order_ref", "linked_order"],
    "transaction_id": ["transaction_id", "txn_id", "payment_id", "tx_id", "bank_txn_id"],
    "settlement_batch": ["settlement_batch", "settlement_batch_id", "batch_id", "settlement_id", "payout_id"],
    # Financial Amounts
    "gross_amount": ["gross_amount", "gross", "charge_amount", "payment_amount", "txn_amount"],
    "fee_amount": ["fee_amount", "fee", "fees", "processing_fee", "charge_fee"],
    "net_amount": ["net_amount", "net", "settled_amount", "payout_amount"],
    "order_amount": ["order_amount", "amount", "total_amount", "order_total", "price", "value"],
    "credited_amount": ["credited_amount", "credit_amount", "bank_credited", "amount_credited"],
    # Other concepts
    "currency": ["currency", "curr", "ccy"],
    "date": ["date", "value_date", "credited_date", "settlement_date", "expected_settlement_by", "expected_date", "due_date", "expected_by", "order_date"],
}


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def map_columns(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    Maps CSV headers to canonical field names using alias matching.
    Returns (mapped_dict, list_of_unrecognized_headers).
    """
    mapped: dict[str, str] = {}
    unrecognized: list[str] = []

    for header in headers:
        norm = _normalize_header(header)
        found = False
        for canonical, aliases in ALIAS_MAP.items():
            if norm == canonical or norm in aliases:
                mapped[header] = canonical
                found = True
                break
        if not found:
            unrecognized.append(header)

    return mapped, unrecognized


def parse_csv_content(content_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """Decodes and parses CSV bytes into rows (as dicts) and original fieldnames."""
    text = content_bytes.decode("utf-8-sig", errors="replace")
    stream = io.StringIO(text)
    reader = csv.DictReader(stream)
    fieldnames = reader.fieldnames or []
    rows = list(reader)
    return rows, fieldnames


def get_field_by_aliases(row: dict[str, str], canonical_key: str, used_headers: set[str] | None = None) -> str:
    """
    Finds the value in the row corresponding to canonical_key aliases.
    If used_headers is provided, registers the raw header that matched.
    Returns the string value (stripped) or empty string.
    """
    aliases = ALIAS_MAP.get(canonical_key, [])
    for raw_header, val in row.items():
        if val is None:
            continue
        norm = _normalize_header(raw_header)
        if norm == canonical_key or norm in aliases:
            if used_headers is not None:
                used_headers.add(raw_header)
            return val.strip()
    return ""


def determine_record_type(row: dict[str, str], used_headers: set[str]) -> str | None:
    # 1. Check explicit record_type column
    rec_type_val = get_field_by_aliases(row, "record_type", used_headers)
    if rec_type_val:
        rec_type_lower = rec_type_val.lower()
        if rec_type_lower in ("order", "orders"):
            return "order"
        elif rec_type_lower in ("transaction", "transactions", "gateway", "gateway_transaction"):
            return "gateway_transaction"
        elif rec_type_lower in ("settlement", "settlements", "bank_settlement", "bank"):
            return "bank_settlement"

    # 2. Structural Inference
    has_txn_id = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["transaction_id"] or _normalize_header(h) == "transaction_id")
    has_settlement_batch = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["settlement_batch"] or _normalize_header(h) == "settlement_batch")
    has_order_id = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["order_id"] or _normalize_header(h) == "order_id")
    has_ref_id = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["reference_id"] or _normalize_header(h) == "reference_id")
    has_credit = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["credited_amount"] or _normalize_header(h) == "credited_amount")

    if has_txn_id:
        return "gateway_transaction"

    if has_settlement_batch and has_credit and not has_order_id:
        return "bank_settlement"

    if has_order_id:
        return "order"

    if has_ref_id:
        has_txn_indicator = any(row.get(h) for h in row if _normalize_header(h) in ALIAS_MAP["order_reference"] + ALIAS_MAP["fee_amount"] + ALIAS_MAP["gross_amount"])
        if has_txn_indicator:
            return "gateway_transaction"
        if has_credit:
            return "bank_settlement"
        return "order"

    return None


def extract_order(row: dict[str, str], used_headers: set[str]) -> dict[str, str] | None:
    order_id = get_field_by_aliases(row, "order_id", used_headers)
    if not order_id:
        order_id = get_field_by_aliases(row, "reference_id", used_headers)

    if not order_id:
        return None

    amount = get_field_by_aliases(row, "order_amount", used_headers)
    if not amount:
        amount = get_field_by_aliases(row, "gross_amount", used_headers)
    if not amount:
        amount = get_field_by_aliases(row, "net_amount", used_headers)
    if not amount:
        amount = "0"

    currency = get_field_by_aliases(row, "currency", used_headers) or "INR"
    expected_settlement_by = get_field_by_aliases(row, "date", used_headers)

    return {
        "order_id": order_id,
        "order_amount": amount,
        "currency": currency,
        "expected_settlement_by": expected_settlement_by,
    }


def extract_transaction(row: dict[str, str], used_headers: set[str]) -> dict[str, str] | None:
    txn_id = get_field_by_aliases(row, "transaction_id", used_headers)
    if not txn_id:
        txn_id = get_field_by_aliases(row, "reference_id", used_headers)

    if not txn_id:
        return None

    order_ref = get_field_by_aliases(row, "order_reference", used_headers)
    if not order_ref:
        order_ref = get_field_by_aliases(row, "order_id", used_headers)

    settlement_batch_id = get_field_by_aliases(row, "settlement_batch", used_headers)

    gross_amount = get_field_by_aliases(row, "gross_amount", used_headers)
    if not gross_amount:
        gross_amount = get_field_by_aliases(row, "order_amount", used_headers)
    if not gross_amount:
        gross_amount = "0"

    fee = get_field_by_aliases(row, "fee_amount", used_headers) or "0"

    net_amount = get_field_by_aliases(row, "net_amount", used_headers)
    if not net_amount:
        try:
            net_amount = str(float(gross_amount) - float(fee))
        except ValueError:
            net_amount = gross_amount

    currency = get_field_by_aliases(row, "currency", used_headers) or "INR"

    return {
        "txn_id": txn_id,
        "order_ref": order_ref,
        "gross_amount": gross_amount,
        "fee": fee,
        "net_amount": net_amount,
        "currency": currency,
        "settlement_batch_id": settlement_batch_id,
    }


def extract_settlement(row: dict[str, str], used_headers: set[str]) -> dict[str, str] | None:
    batch_id = get_field_by_aliases(row, "settlement_batch", used_headers)
    if not batch_id:
        batch_id = get_field_by_aliases(row, "reference_id", used_headers)

    if not batch_id:
        return None

    credited_amount = get_field_by_aliases(row, "credited_amount", used_headers)
    if not credited_amount:
        credited_amount = get_field_by_aliases(row, "net_amount", used_headers)
    if not credited_amount:
        credited_amount = get_field_by_aliases(row, "gross_amount", used_headers)
    if not credited_amount:
        credited_amount = "0"

    value_date = get_field_by_aliases(row, "date", used_headers)
    currency = get_field_by_aliases(row, "currency", used_headers) or "INR"

    return {
        "settlement_batch_id": batch_id,
        "credited_amount": credited_amount,
        "currency": currency,
        "value_date": value_date,
    }


def process_csv_upload(files_content: list[tuple[str, bytes]]) -> tuple[list[dict], list[dict], list[dict], IngestionSummary]:
    """
    Processes one or more uploaded CSV files.
    Identifies order, transaction, and settlement records.
    Returns (orders, txns, settlements, summary).
    """
    total_rows = 0
    orders: list[dict] = []
    txns: list[dict] = []
    settlements: list[dict] = []

    all_raw_headers: set[str] = set()
    used_headers: set[str] = set()
    warnings: list[str] = []
    unprocessable: list[dict] = []
    detected_types: set[str] = set()
    ignored_rows_count = 0

    if not files_content:
        return [], [], [], IngestionSummary(
            success=False,
            total_rows_received=0,
            error_message="No CSV files were uploaded."
        )

    for filename, content in files_content:
        try:
            rows, raw_headers = parse_csv_content(content)
        except Exception as e:
            return [], [], [], IngestionSummary(
                success=False,
                total_rows_received=0,
                error_message=f"Failed to parse CSV file {filename}: {str(e)}"
            )

        if not raw_headers:
            warnings.append(f"File {filename} is empty or missing headers.")
            continue

        all_raw_headers.update(raw_headers)

        for row_idx, raw_row in enumerate(rows):
            total_rows += 1

            rec_type = determine_record_type(raw_row, used_headers)

            if rec_type == "order":
                record = extract_order(raw_row, used_headers)
                if record:
                    orders.append(record)
                    detected_types.add("order")
                else:
                    ignored_rows_count += 1
                    unprocessable.append({
                        "file": filename,
                        "row": row_idx + 1,
                        "reason": "Missing required field: order_id for order",
                        "data": raw_row
                    })
            elif rec_type == "gateway_transaction":
                record = extract_transaction(raw_row, used_headers)
                if record:
                    txns.append(record)
                    detected_types.add("gateway_transaction")
                else:
                    ignored_rows_count += 1
                    unprocessable.append({
                        "file": filename,
                        "row": row_idx + 1,
                        "reason": "Missing required field: txn_id for transaction",
                        "data": raw_row
                    })
            elif rec_type == "bank_settlement":
                record = extract_settlement(raw_row, used_headers)
                if record:
                    settlements.append(record)
                    detected_types.add("bank_settlement")
                else:
                    ignored_rows_count += 1
                    unprocessable.append({
                        "file": filename,
                        "row": row_idx + 1,
                        "reason": "Missing required field: settlement_batch_id for bank_settlement",
                        "data": raw_row
                    })
            else:
                ignored_rows_count += 1
                unprocessable.append({
                    "file": filename,
                    "row": row_idx + 1,
                    "reason": "Could not classify record type structurally and no explicit record_type was provided",
                    "data": raw_row
                })

    # Determine ignored columns
    ignored_columns = []
    for h in all_raw_headers:
        norm = _normalize_header(h)
        # It is ignored if it does not match any entry in ALIAS_MAP and was not added to used_headers
        is_recognized = False
        for canonical, aliases in ALIAS_MAP.items():
            if norm == canonical or norm in aliases:
                is_recognized = True
                break
        if not is_recognized and h not in used_headers:
            ignored_columns.append(h)

    # Validate overall ingestion success: reject only if NO valid records were usable at all
    if not orders and not txns and not settlements:
        return [], [], [], IngestionSummary(
            success=False,
            total_rows_received=total_rows,
            ignored_columns=sorted(list(ignored_columns)),
            ignored_rows_count=ignored_rows_count,
            validation_warnings=warnings,
            unprocessable_records=unprocessable,
            error_message="Uploaded CSV data contains no valid or recognized financial records (orders, transactions, or bank settlements)."
        )

    summary = IngestionSummary(
        success=True,
        total_rows_received=total_rows,
        usable_orders_count=len(orders),
        usable_transactions_count=len(txns),
        usable_settlements_count=len(settlements),
        ignored_columns=sorted(list(ignored_columns)),
        ignored_rows_count=ignored_rows_count,
        detected_record_types=sorted(list(detected_types)),
        validation_warnings=warnings,
        unprocessable_records=unprocessable,
    )

    return orders, txns, settlements, summary
