from app.ingestion import process_csv_upload, map_columns
from app.agent import ask_finance_agent, run_batch_controller
from app.tools import set_demo_batch, set_custom_batch, is_custom_upload


def test_map_columns_aliases():
    raw_headers = ["Order_Number", "TOTAL_AMOUNT", "curr", "random_extra_col"]
    mapped, unrecognized = map_columns(raw_headers)

    assert mapped["Order_Number"] == "order_id"
    assert mapped["TOTAL_AMOUNT"] == "order_amount"
    assert mapped["curr"] == "currency"
    assert "random_extra_col" in unrecognized


def test_process_valid_mixed_csv():
    csv_data = (
        "record_type,order_id,txn_id,settlement_batch_id,amount,gross_amount,fee,net_amount,credited_amount,currency,date\n"
        "order,ORD-901,,100.00,,,,,,INR,2026-08-01\n"
        "gateway_transaction,,TXN-901,SETT-901,,100.00,2.00,98.00,,INR,2026-08-01\n"
        "bank_settlement,,,SETT-901,,,,,,98.00,INR,2026-08-02\n"
    ).encode("utf-8")

    orders, txns, settlements, summary = process_csv_upload([("test_mixed.csv", csv_data)])

    assert summary.success is True
    assert summary.usable_orders_count == 1
    assert summary.usable_transactions_count == 1
    assert summary.usable_settlements_count == 1
    assert orders[0]["order_id"] == "ORD-901"
    assert txns[0]["txn_id"] == "TXN-901"
    assert settlements[0]["settlement_batch_id"] == "SETT-901"


def test_process_csv_with_extra_columns():
    csv_data = (
        "record_type,order_id,amount,currency,date,internal_note,marketing_source\n"
        "order,ORD-902,250.00,INR,2026-08-01,VIP customer,Google Ads\n"
    ).encode("utf-8")

    orders, txns, settlements, summary = process_csv_upload([("test_extra.csv", csv_data)])

    assert summary.success is True
    assert summary.usable_orders_count == 1
    assert "internal_note" in summary.ignored_columns
    assert "marketing_source" in summary.ignored_columns


def test_ambiguous_unrecognized_csv_fails_honestly():
    csv_data = (
        "foo_bar_header,random_column_1,random_column_2\n"
        "val1,val2,val3\n"
    ).encode("utf-8")

    orders, txns, settlements, summary = process_csv_upload([("invalid.csv", csv_data)])

    assert summary.success is False
    assert "no valid or recognized financial records" in summary.error_message.lower()


def test_ask_financeos_order_lookup():
    set_demo_batch()
    res = ask_finance_agent("Why was order ORD-0021 escalated?")

    assert res["evidence_verified"] is True
    assert res["type"] == "ORDER_LOOKUP"
    assert "ORD-0021" in res["answer"]


def test_ask_financeos_nonexistent_order():
    set_demo_batch()
    res = ask_finance_agent("Why was order ORD-99999 escalated?")

    assert res["evidence_verified"] is False
    assert "not found" in res["answer"].lower()


def test_partial_ingestion_safety():
    """Verify that partial ingestion processes valid rows and lists unprocessable rows with explicit reasons."""
    csv_data = (
        "record_type,order_id,amount,currency,date\n"
        "order,ORD-VALID-01,150.00,INR,2026-08-01\n"
        "order,,200.00,INR,2026-08-01\n"
        ",,,,\n"
    ).encode("utf-8")

    orders, txns, settlements, summary = process_csv_upload([("partial.csv", csv_data)])

    assert summary.success is True
    assert summary.usable_orders_count == 1
    assert len(orders) == 1
    assert orders[0]["order_id"] == "ORD-VALID-01"
    assert summary.ignored_rows_count == 2
    assert len(summary.unprocessable_records) == 2
    assert any("order_id" in rec["reason"] for rec in summary.unprocessable_records)

