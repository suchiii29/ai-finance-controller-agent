import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tools import set_demo_batch

client = TestClient(app)


def test_flow_1_existing_demo_batch():
    """Verify demo batch reconciliation and controller report endpoints."""
    # Step 1: reconcile resets to demo batch
    rec_resp = client.post("/api/reconcile", json={"instruction": "Process synthetic demo batch"})
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert "result" in rec_data

    result = rec_data["result"]
    # Real field name: runtime_counts
    assert result["runtime_counts"]["total_orders_decided"] == 60
    assert result["runtime_counts"]["reconciled_count"] == 38

    # Step 2: controller batch report
    ctrl_resp = client.post("/api/controller/run")
    assert ctrl_resp.status_code == 200
    report = ctrl_resp.json()

    assert report["total_cases"] == 60
    assert report["reconciled_cases"] == 38
    assert report["escalated_cases"] == 22
    assert report["is_custom_batch"] is False
    # Evaluation must be populated with ground truth for demo batch
    assert report["evaluation"] is not None
    assert report["evaluation"]["precision"] == 1.0


def test_flow_2_valid_custom_csv_upload():
    """Verify uploading a valid custom CSV batch through the full pipeline."""
    csv_content = (
        "record_type,order_id,txn_id,settlement_batch_id,order_amount,gross_amount,fee,net_amount,credited_amount,currency,date\n"
        "order,CUSTOM-ORD-01,,SETT-100,150.00,,,,,,INR,2026-08-01\n"
        "gateway_transaction,,CUSTOM-TXN-01,SETT-100,,150.00,3.00,147.00,,INR,2026-08-01\n"
        "bank_settlement,,,SETT-100,,,,,,147.00,INR,2026-08-02\n"
    ).encode("utf-8")

    response = client.post(
        "/api/upload",
        files=[("files", ("custom_batch.csv", csv_content, "text/csv"))]
    )
    assert response.status_code == 200
    data = response.json()

    ingestion = data["ingestion_summary"]
    assert ingestion["success"] is True
    assert ingestion["usable_orders_count"] == 1
    assert ingestion["usable_transactions_count"] == 1
    assert ingestion["usable_settlements_count"] == 1

    report = data["report"]
    assert report["is_custom_batch"] is True
    # Ground-truth evaluation MUST be None for custom upload
    assert report["evaluation"] is None
    # Records processed = orders + txns + settlements
    assert report["records_processed"] == 3

    # Verify result has the runtime_counts structure
    result = data["result"]
    assert "runtime_counts" in result
    assert result["runtime_counts"]["total_orders_decided"] == 1


def test_flow_3_csv_with_extra_irrelevant_columns():
    """Verify CSV with extra non-financial columns are silently ignored."""
    csv_content = (
        "record_type,order_id,order_amount,currency,expected_settlement_by,internal_referrer,marketing_campaign_id\n"
        "order,CUSTOM-ORD-02,500.00,INR,2026-08-05,partner_abc,summer_sale_2026\n"
    ).encode("utf-8")

    response = client.post(
        "/api/upload",
        files=[("files", ("extra_cols.csv", csv_content, "text/csv"))]
    )
    assert response.status_code == 200
    data = response.json()
    summary = data["ingestion_summary"]

    assert summary["success"] is True
    assert summary["usable_orders_count"] == 1
    assert "internal_referrer" in summary["ignored_columns"]
    assert "marketing_campaign_id" in summary["ignored_columns"]


def test_flow_4_ambiguous_unsupported_csv_failure():
    """Verify ambiguous or unsupported CSV headers return honest 400 error."""
    csv_content = (
        "unknown_column_a,unknown_column_b,unknown_column_c\n"
        "foo,bar,baz\n"
    ).encode("utf-8")

    response = client.post(
        "/api/upload",
        files=[("files", ("unsupported.csv", csv_content, "text/csv"))]
    )
    assert response.status_code == 400
    data = response.json()

    assert "detail" in data
    assert "no valid or recognized financial records" in str(data["detail"]).lower()


def test_flow_5_ask_financeos_against_current_batch():
    """Verify Ask FinanceOS queries answer dynamically from active batch data."""
    # Reset to demo batch with known data
    set_demo_batch()

    # Query 1: Specific Order Lookup (ORD-0021 is in the demo batch)
    res1 = client.post("/api/ask", json={"question": "Why was order ORD-0021 escalated?"})
    assert res1.status_code == 200
    body1 = res1.json()
    ans1 = body1["response"]
    assert ans1["evidence_verified"] is True
    assert "ORD-0021" in ans1["answer"]
    assert ans1["type"] == "ORDER_LOOKUP"

    # Query 2: Amount Mismatches (deterministic retrieval)
    res2 = client.post("/api/ask", json={"question": "Show me all amount mismatches."})
    assert res2.status_code == 200
    ans2 = res2.json()["response"]
    assert ans2["evidence_verified"] is True
    assert ans2["type"] == "AMOUNT_MISMATCHES"

    # Query 3: Ingestion Summary
    res3 = client.post("/api/ask", json={"question": "How many records were ignored during ingestion?"})
    assert res3.status_code == 200
    ans3 = res3.json()["response"]
    assert ans3["evidence_verified"] is True
    assert "Ingestion Summary" in ans3["answer"]


def test_flow_6_report_download_run_snapshot():
    """Verify /api/report/download generates HTML report snapshot from current run state without re-running reconciliation."""
    set_demo_batch()
    # Run batch controller to generate snapshot
    client.post("/api/controller/run")

    resp = client.get("/api/report/download")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "attachment; filename=financeos_report_" in resp.headers.get("content-disposition", "")
    html = resp.text
    assert "<!DOCTYPE html>" in html
    assert "FinanceOS Reconciliation Run Report" in html
    assert "Run Summary" in html
    assert "Exception Register" in html


def test_flow_7_ask_financeos_broad_operational_query():
    """Verify broad Ask FinanceOS queries return evidence-grounded operational summaries, not generic fallbacks."""
    set_demo_batch()

    # Broad operational summary
    res = client.post("/api/ask", json={"question": "What are the biggest issues in this batch?"})
    assert res.status_code == 200
    body = res.json()["response"]
    assert body["evidence_verified"] is True
    assert body["type"] == "OPERATIONAL_SUMMARY"
    assert "Overall Batch Outcome" in body["answer"]
    assert "Escalated" in body["answer"]
    assert "None reported." not in body["answer"]
    assert "could not complete" not in body["answer"]


