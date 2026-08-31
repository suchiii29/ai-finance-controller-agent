"""
HTML Report Generator for FinanceOS Run Reports.
Generates a printable, professional, easy-to-scan HTML snapshot of reconciliation runs.
"""

from __future__ import annotations
from datetime import datetime, timezone
from app.models import BatchControllerReport


def generate_html_report(report: BatchControllerReport) -> str:
    """Generates a professional, audit-ready HTML report for a reconciliation run."""
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    batch_type = "Custom Uploaded Batch" if report.is_custom_batch else "Synthetic Demo Batch"
    
    # Calculate measured throughput
    # Records processed divided by max of execution time
    total_sec = report.timings.get("controller_total_seconds", 0.0) or report.timings.get("deterministic_reconciliation_seconds", 0.0)
    measured_throughput = 0.0
    if total_sec > 0:
        measured_throughput = report.records_processed / total_sec

    # Safe resolution / match rate
    match_rate_pct = report.match_rate * 100.0

    # Ingestion summary
    ing = report.ingestion_summary or {}
    total_raw = ing.get("total_rows_received", 0)
    orders_count = ing.get("usable_orders_count", 0)
    txns_count = ing.get("usable_transactions_count", 0)
    settlements_count = ing.get("usable_settlements_count", 0)
    ignored_cols = ing.get("ignored_columns", [])
    ignored_rows = ing.get("ignored_rows_count", 0)
    unprocessable = ing.get("unprocessable_records", [])

    # HTML Header
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>FinanceOS Run Report - Run {report.run_id}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #2d3748;
            background-color: #fafafa;
            margin: 0;
            padding: 40px 20px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
            padding: 40px;
        }}
        header {{
            border-bottom: 2px solid #edf2f7;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header-meta {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-top: 10px;
        }}
        h1 {{
            font-size: 24px;
            font-weight: 700;
            color: #1a202c;
            margin: 0;
        }}
        .badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 4px 10px;
            border-radius: 9999px;
        }}
        .badge-demo {{
            background-color: #ebf8ff;
            color: #2b6cb0;
        }}
        .badge-custom {{
            background-color: #faf5ff;
            color: #553c9a;
        }}
        .badge-review {{
            background-color: #fffaf0;
            color: #dd6b20;
        }}
        .badge-completed {{
            background-color: #f0fff4;
            color: #38a169;
        }}
        
        h2 {{
            font-size: 18px;
            font-weight: 600;
            color: #2d3748;
            border-bottom: 1px solid #edf2f7;
            padding-bottom: 8px;
            margin-top: 35px;
            margin-bottom: 15px;
        }}
        
        .grid-4 {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }}
        .metric-card {{
            background-color: #f8fafc;
            border: 1px solid #edf2f7;
            border-radius: 6px;
            padding: 15px;
            text-align: left;
        }}
        .metric-label {{
            font-size: 11px;
            color: #718096;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: 700;
            color: #1a202c;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        th, td {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 13px;
        }}
        th {{
            background-color: #f7fafc;
            font-weight: 600;
            color: #4a5568;
            text-transform: uppercase;
            font-size: 11px;
        }}
        
        .exception-card {{
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
            background-color: #ffffff;
        }}
        .exception-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .exception-id {{
            font-weight: 700;
            color: #e53e3e;
            font-size: 14px;
        }}
        .exception-title {{
            font-weight: 600;
            font-size: 13px;
        }}
        .exception-meta {{
            font-size: 12px;
            color: #718096;
            margin-bottom: 8px;
        }}
        .exception-reason {{
            font-size: 13px;
            color: #4a5568;
            margin-bottom: 10px;
        }}
        .exception-action {{
            font-size: 12px;
            background-color: #fffaf0;
            border-left: 3px solid #dd6b20;
            padding: 8px 12px;
            color: #793e10;
        }}
        
        .safety-box {{
            background-color: #ebf8ff;
            border: 1px solid #bee3f8;
            border-radius: 6px;
            padding: 15px;
            margin-top: 30px;
            font-size: 13px;
            color: #2b6cb0;
        }}
        .safety-box strong {{
            color: #2c5282;
        }}
        
        .evaluation-table {{
            margin-top: 15px;
        }}
        
        .no-eval-alert {{
            background-color: #f7fafc;
            border: 1px solid #edf2f7;
            color: #718096;
            padding: 15px;
            border-radius: 6px;
            font-size: 13px;
            text-align: center;
        }}
        
        @media print {{
            body {{
                background-color: #ffffff;
                padding: 0;
            }}
            .container {{
                box-shadow: none;
                border: none;
                padding: 0;
                max-width: 100%;
            }}
            .no-print {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h1>FinanceOS Reconciliation Run Report</h1>
                <span class="badge {'badge-custom' if report.is_custom_batch else 'badge-demo'}">{batch_type}</span>
            </div>
            <div class="header-meta">
                <div>
                    <div style="font-size: 12px; color: #718096;">Run ID: <strong style="color: #2d3748;">{report.run_id}</strong></div>
                    <div style="font-size: 12px; color: #718096;">Generated: <strong style="color: #2d3748;">{run_date}</strong></div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 12px; color: #718096;">Status:</div>
                    <span class="badge {'badge-review' if report.status == 'NEEDS_HUMAN_REVIEW' else 'badge-completed'}">{report.status}</span>
                </div>
            </div>
        </header>

        <h2>1. Run Summary</h2>
        <div class="grid-4">
            <div class="metric-card">
                <div class="metric-label">Total Records</div>
                <div class="metric-value">{report.records_processed}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Safely Reconciled</div>
                <div class="metric-value">{report.reconciled_cases}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Escalated / Review</div>
                <div class="metric-value">{report.escalated_cases}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Measured Throughput</div>
                <div class="metric-value" style="font-size: 16px; margin-top: 4px;">{measured_throughput:.1f} rec/sec</div>
            </div>
        </div>

        <h2>2. Reconciliation Outcome</h2>
        <div style="margin-bottom: 25px; font-size: 14px;">
            <p>• <strong>Safe Resolution Rate:</strong> {match_rate_pct:.2f}% of orders in this batch were successfully verified using deterministic multi-source reconciliation rules.</p>
            <p>• <strong>Automatically Verified:</strong> {report.reconciled_cases} cases passed all reconciliation logic (matching order, gateway transaction, and bank settlement amount/SLA checks).</p>
            <p>• <strong>Operator Action Required:</strong> {report.escalated_cases} cases failed matching checks or batch integrity requirements and require manual investigation.</p>
        </div>

        <h2>3. Ingestion Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Raw rows received</td>
                    <td>{total_raw}</td>
                </tr>
                <tr>
                    <td>Usable Orders detected</td>
                    <td>{orders_count}</td>
                </tr>
                <tr>
                    <td>Usable Gateway Transactions detected</td>
                    <td>{txns_count}</td>
                </tr>
                <tr>
                    <td>Usable Bank Settlements detected</td>
                    <td>{settlements_count}</td>
                </tr>
                <tr>
                    <td>Unprocessable rows / skipped</td>
                    <td>{ignored_rows}</td>
                </tr>
                <tr>
                    <td>Ignored columns (unused fields)</td>
                    <td>{", ".join(ignored_cols) if ignored_cols else "None"}</td>
                </tr>
            </tbody>
        </table>
        
        {"" if not unprocessable else f'''
        <div style="margin-top: 15px; max-height: 200px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; background-color: #f8fafc;">
            <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #718096; margin-bottom: 8px;">Unprocessable Row Breakdown</div>
            {"".join(f'<div style="font-size: 12px; margin-bottom: 6px; border-bottom: 1px solid #edf2f7; padding-bottom: 4px;"><strong>Row {item.get("row")} (File: {item.get("file")}):</strong> {item.get("reason")}</div>' for item in unprocessable[:20])}
            {f'<div style="font-size: 11px; color: #a0aec0;">Showing first 20 of {len(unprocessable)} unprocessable rows</div>' if len(unprocessable) > 20 else ""}
        </div>
        '''}

        <h2>4. Exception Register</h2>
        """

    if not report.unresolved_exceptions:
        html += """
        <div style="text-align: center; color: #718096; padding: 30px; border: 1px dashed #e2e8f0; border-radius: 6px; font-size: 14px;">
            No exceptions recorded in this reconciliation batch.
        </div>
        """
    else:
        for exc in report.unresolved_exceptions:
            from app.investigation import get_recommended_action_by_type
            rec_action = get_recommended_action_by_type(exc["type"], exc.get("references", []))
            
            html += f"""
            <div class="exception-card">
                <div class="exception-header">
                    <div class="exception-id">{exc["exception_id"]}</div>
                    <div class="exception-title" style="color: #2d3748;">{exc["type"]}</div>
                    <span class="badge" style="background-color: #fff5f5; color: #c53030; font-size: 10px;">{exc["severity"]}</span>
                </div>
                <div class="exception-meta">
                    <strong>Scope:</strong> {exc.get("scope", "RECORD")} | 
                    <strong>Affected:</strong> {", ".join(exc["references"])}
                </div>
                <div class="exception-reason">{exc["reason"]}</div>
                <div class="exception-action">
                    <strong>Recommended operator action:</strong> {rec_action}
                </div>
            </div>
            """

    # 5. Evaluation Results
    html += """
        <h2>5. Evaluation & Audit Benchmarks</h2>
    """
    if report.is_custom_batch or report.evaluation is None:
        html += f"""
        <table class="evaluation-table">
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Measured Value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Precision</td>
                    <td><strong>N/A</strong></td>
                </tr>
                <tr>
                    <td>Recall</td>
                    <td><strong>N/A</strong></td>
                </tr>
                <tr>
                    <td>F1 Score</td>
                    <td><strong>N/A</strong></td>
                </tr>
                <tr>
                    <td>Exception Escalation Accuracy</td>
                    <td><strong>N/A</strong></td>
                </tr>
                <tr>
                    <td>Safe Resolution Rate (Operational)</td>
                    <td><strong>{match_rate_pct:.2f}%</strong> ({report.reconciled_cases} of {report.total_cases} orders)</td>
                </tr>
                <tr>
                    <td>Ground Truth Cases</td>
                    <td>None (Custom Upload)</td>
                </tr>
            </tbody>
        </table>
        <div class="no-eval-alert" style="margin-top: 10px; text-align: left;">
            Ground-truth benchmark metrics are unavailable for this uploaded batch because no labeled ground truth was provided. FinanceOS does not fabricate Precision, Recall, or F1. Operational reconciliation metrics are still reported from the current run.
        </div>
        """
    else:
        ev = report.evaluation
        html += f"""
        <table class="evaluation-table">
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Measured Value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Precision</td>
                    <td><strong>{ev.precision * 100.0:.2f}%</strong></td>
                </tr>
                <tr>
                    <td>Recall</td>
                    <td><strong>{ev.recall * 100.0:.2f}%</strong></td>
                </tr>
                <tr>
                    <td>F1 Score</td>
                    <td><strong>{ev.f1 * 100.0:.2f}%</strong></td>
                </tr>
                <tr>
                    <td>Safe Resolution Rate</td>
                    <td><strong>{ev.safe_resolution_rate * 100.0:.2f}%</strong></td>
                </tr>
                <tr>
                    <td>Exception Escalation Accuracy</td>
                    <td><strong>{ev.exception_escalation_accuracy * 100.0:.2f}%</strong></td>
                </tr>
                <tr>
                    <td>Total Ground Truth Cases</td>
                    <td>{ev.ground_truth_cases}</td>
                </tr>
            </tbody>
        </table>
        """

    # 6. Audit & Safety Boundary
    html += """
        <div class="safety-box">
            <strong>Audit & Safety Boundary Statement:</strong><br>
            Financial reconciliation decisions were made entirely by deterministic rules. AI-generated investigation provides evidence-grounded explanations and does not override financial decisions.
        </div>
        
        <div class="no-print" style="margin-top: 30px; text-align: center;">
            <button onclick="window.print()" style="background-color: #0f172a; color: white; border: none; padding: 10px 24px; font-size: 13px; font-weight: 600; border-radius: 4px; cursor: pointer; letter-spacing: 0.2px;">
                Print Report / Save as PDF
            </button>
        </div>
    </div>
</body>
</html>
"""
    return html
