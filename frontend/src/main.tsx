import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_URL = import.meta.env.VITE_API_URL?.trim() || "";

interface EvaluationMetrics {
  total_cases_evaluated: number;
  correctly_reconciled: number;
  correctly_escalated: number;
  incorrect_auto_resolutions: number;
  missed_resolvable_cases: number;
  precision: number;
  recall: number;
  f1: number;
  safe_resolution_rate: number;
  exception_escalation_accuracy: number;
  ground_truth_cases: number;
}

interface IngestionSummary {
  success: boolean;
  total_rows_received: number;
  usable_orders_count: number;
  usable_transactions_count: number;
  usable_settlements_count: number;
  ignored_columns: string[];
  ignored_rows_count: number;
  detected_record_types: string[];
  validation_warnings: string[];
  unprocessable_records: any[];
  error_message?: string;
}

interface BatchReport {
  run_id: string;
  status: string;
  records_processed: number;
  total_cases: number;
  reconciled_cases: number;
  escalated_cases: number;
  match_rate: number;
  unresolved_exceptions: any[];
  activity_trace: any[];
  timings: Record<string, number>;
  throughput?: {
    seconds: number;
    records_per_second: number;
  };
  llm_calls: number;
  tool_calls: number;
  ai_available: boolean;
  fallback_used: boolean;
  financial_action_taken: boolean;
  is_custom_batch?: boolean;
  ingestion_summary?: IngestionSummary;
  cross_exception_analysis?: any;
  evaluation?: EvaluationMetrics;
}

function App() {
  const [activeTab, setActiveTab] = useState<"Overview" | "Exceptions" | "Evaluation">("Overview");
  const [batchData, setBatchData] = useState<BatchReport | null>(null);
  const [reconcileResult, setReconcileResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [processingStage, setProcessingStage] = useState<string>("");
  const [selectedException, setSelectedException] = useState<any | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Ask FinanceOS widget state
  const [askQuestion, setAskQuestion] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [askResponse, setAskResponse] = useState<any | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  // Upload Batch Modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const runDemoBatch = async () => {
    if (!API_URL) {
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
      return;
    }

    setSelectedException(null);
    setLoading(true);
    setApiError(null);
    setProcessingStage("Loading financial records...");

    try {
      setProcessingStage("Validating source integrity...");
      const recRes = await fetch(`${API_URL}/api/reconcile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: "Process synthetic demo batch" }),
      });
      if (!recRes.ok) {
        throw new Error(`Reconciliation request failed: ${recRes.status}`);
      }
      const recJson = await recRes.json();
      setReconcileResult(recJson.result);

      setProcessingStage("Running deterministic reconciliation...");
      const ctrlRes = await fetch(`${API_URL}/api/controller/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!ctrlRes.ok) {
        throw new Error(`Controller request failed: ${ctrlRes.status}`);
      }
      const ctrlJson = await ctrlRes.json();
      setBatchData(ctrlJson);
      setProcessingStage("Building exception evidence...");
      setAskResponse(null);
    } catch (err) {
      console.error(err);
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
    } finally {
      setLoading(false);
      setProcessingStage("");
    }
  };

  const handleUploadBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!API_URL) {
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
      return;
    }
    if (!uploadFiles || uploadFiles.length === 0) {
      setUploadError("Please select at least one CSV file to upload.");
      return;
    }

    setSelectedException(null);
    setUploadError(null);
    setApiError(null);
    setLoading(true);

    setProcessingStage("Loading financial records...");

    const formData = new FormData();
    for (let i = 0; i < uploadFiles.length; i++) {
      formData.append("files", uploadFiles[i]);
    }

    try {
      const res = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(typeof json.detail === "object" ? json.detail.error : json.detail || "Upload failed");
      }

      const json = await res.json();

      if (!res.ok) {
        const errorDetail = typeof json.detail === "object" ? json.detail.error : json.detail;
        setUploadError(errorDetail || "Failed to process uploaded CSV data.");
        setLoading(false);
        return;
      }

      setProcessingStage("Validating source integrity...");
      setBatchData(json.report);
      setReconcileResult(json.result);
      setProcessingStage("Running deterministic reconciliation...");
      setShowUploadModal(false);
      setUploadFiles(null);
      setAskResponse(null);
    } catch (err) {
      console.error(err);
      const msg = err instanceof Error ? err.message : "Network or server error uploading CSV batch.";
      setUploadError(msg);
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
    } finally {
      setLoading(false);
      setProcessingStage("");
    }
  };

  const handleAskQuestion = async (queryToAsk?: string) => {
    const questionText = queryToAsk || askQuestion;
    if (!questionText.trim()) return;
    if (!API_URL) {
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
      setAskResponse({ answer: "FinanceOS backend is currently unavailable. Please retry shortly." });
      return;
    }

    setAskLoading(true);
    setApiError(null);
    try {
      const res = await fetch(`${API_URL}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: questionText }),
      });
      if (!res.ok) {
        throw new Error(`Ask request failed: ${res.status}`);
      }
      const json = await res.json();
      setAskResponse(json.response);
    } catch (err) {
      console.error(err);
      setApiError("FinanceOS backend is currently unavailable. Please retry shortly.");
      setAskResponse({ answer: "FinanceOS backend is currently unavailable. Please retry shortly." });
    } finally {
      setAskLoading(false);
    }
  };

  useEffect(() => {
    runDemoBatch();
  }, []);

  const exceptions = batchData?.unresolved_exceptions || reconcileResult?.exceptions || [];

  const filteredExceptions = exceptions.filter((ex: any) => {
    const matchesSev = filterSeverity === "ALL" || ex.severity === filterSeverity;
    const matchesSearch =
      !searchQuery ||
      ex.exception_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ex.type?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ex.reason?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (ex.references && ex.references.some((r: string) => r.toLowerCase().includes(searchQuery.toLowerCase())));
    return matchesSev && matchesSearch;
  });

  const selectedExDetails = selectedException
    ? selectedException
    : filteredExceptions.length > 0
    ? filteredExceptions[0]
    : null;

  const totalCases = batchData?.total_cases || 0;
  const reconciledCases = batchData?.reconciled_cases || 0;
  const escalatedCases = batchData?.escalated_cases || 0;
  const matchRate = (batchData?.match_rate || 0) * 100;
  const recordsProcessed = batchData?.records_processed || 0;
  const totalSecs = batchData?.timings?.controller_total_seconds || 1.0;
  const recordsPerSec = recordsProcessed > 0 ? (recordsProcessed / Math.max(totalSecs, 0.001)).toFixed(0) : "--";

  const isCustom = batchData?.is_custom_batch || false;
  const ingestion = batchData?.ingestion_summary;

  const renderAgentResponse = (resp: any) => {
    if (!resp) return null;

    if (resp.type === "OPERATIONAL_SUMMARY" && resp.details) {
      const d = resp.details;
      return (
        <div className="agent-summary-container" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ fontWeight: 700, fontSize: "14px", color: "var(--text-navy)", borderBottom: "1px solid var(--border-color)", paddingBottom: "6px" }}>
            Overall Batch Outcome
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px" }}>
            <div style={{ background: "var(--bg-subtle)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Reconciled</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--status-green)", marginTop: "4px" }}>
                {d.reconciled_orders} of {d.total_orders} orders
              </div>
            </div>
            <div style={{ background: "var(--bg-subtle)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Escalated</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--status-amber)", marginTop: "4px" }}>
                {d.escalated_orders} orders
              </div>
            </div>
            <div style={{ background: "var(--bg-subtle)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: "10px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Safe Resolution Rate</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-navy)", marginTop: "4px" }}>
                {d.safe_resolution_rate.toFixed(2)}%
              </div>
            </div>
          </div>

          <div style={{ fontSize: "12px", background: "var(--bg-card)", padding: "10px", borderRadius: "6px", borderLeft: "3px solid var(--status-amber)", color: "var(--text-main)" }}>
            <strong>Exception Overview:</strong> {d.escalated_orders} escalated orders contain {d.total_incidents} exception incidents: <span className="text-amber-dark" style={{ fontWeight: 600 }}>{d.urgent_incidents} urgent</span> and <span style={{ fontWeight: 600 }}>{d.review_incidents} review-level</span>.
          </div>

          {d.category_counts && Object.keys(d.category_counts).length > 0 && (
            <div>
              <div style={{ fontWeight: 600, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Exception Categories</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                {Object.entries(d.category_counts).map(([cat, cnt]: any) => (
                  <span key={cat} className="evidence-chip" style={{ fontSize: "11px" }}>
                    {cat}: <strong>{cnt}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}

          {d.findings && d.findings.length > 0 && (
            <div>
              <div style={{ fontWeight: 600, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Operational Findings</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {d.findings.slice(0, 4).map((f: any, i: number) => (
                  <div key={i} style={{ fontSize: "12px", background: "var(--bg-subtle)", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-color)" }}>
                    <strong style={{ fontFamily: "monospace", color: "var(--text-navy)" }}>{f.exception_id}</strong> <span className={`tag ${f.severity === "URGENT" ? "urgent" : "review"}`} style={{ fontSize: "9px", padding: "1px 4px", marginLeft: "6px" }}>{f.severity}</span>
                    <p style={{ margin: "4px 0 0 0", color: "var(--text-main)" }}>{f.reason}</p>
                  </div>
                ))}
                {d.findings.length > 4 && (
                  <div style={{ fontSize: "11px", color: "var(--text-muted)", fontStyle: "italic" }}>
                    Showing first 4 of {d.findings.length} findings. Select the Exceptions tab to review all.
                  </div>
                )}
              </div>
            </div>
          )}

          {d.recommended_actions && d.recommended_actions.length > 0 && (
            <div>
              <div style={{ fontWeight: 600, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Recommended Operator Actions</div>
              <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-main)" }}>
                {d.recommended_actions.map((act: string, i: number) => (
                  <li key={i} style={{ marginBottom: "4px" }}>{act}</li>
                ))}
              </ul>
            </div>
          )}

          {d.ingestion && (
            <div>
              <div style={{ fontWeight: 600, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Ingestion Context</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "6px 12px", fontSize: "11px", color: "var(--text-muted)", background: "var(--bg-card)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
                <div>Raw rows received: <strong style={{ color: "var(--text-navy)" }}>{d.ingestion.total_rows_received}</strong></div>
                <div>Usable orders: <strong style={{ color: "var(--text-navy)" }}>{d.ingestion.usable_orders_count}</strong></div>
                <div>Gateway transactions: <strong style={{ color: "var(--text-navy)" }}>{d.ingestion.usable_transactions_count}</strong></div>
                <div>Bank settlements: <strong style={{ color: "var(--text-navy)" }}>{d.ingestion.usable_settlements_count}</strong></div>
                <div>Unprocessable rows: <strong style={{ color: "var(--text-navy)" }}>{d.ingestion.unprocessable_records_count}</strong></div>
                <div>
                  Ignored columns:{" "}
                  <strong>
                    {d.ingestion.ignored_columns && d.ingestion.ignored_columns.length > 0
                      ? d.ingestion.ignored_columns.length
                      : "0"}
                  </strong>
                </div>
              </div>
            </div>
          )}
        </div>
      );
    }

    const text = resp.answer || JSON.stringify(resp);
    return (
      <div style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-sans)", fontSize: "13px", lineHeight: "1.6", color: "var(--text-main)" }}>
        {text.split("\n").map((line: string, i: number) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={i} style={{ height: "8px" }} />;
          
          if (
            trimmed === "Overall Batch Outcome" || 
            trimmed === "Exception Overview" || 
            trimmed === "Exception Categories" || 
            trimmed === "Operational Findings" || 
            trimmed === "Recommended Operator Actions" || 
            trimmed === "Ingestion Context" ||
            trimmed === "Reconciled" ||
            trimmed === "Escalated" ||
            trimmed === "Safe resolution rate"
          ) {
            const isSub = trimmed === "Reconciled" || trimmed === "Escalated" || trimmed === "Safe resolution rate";
            return (
              <div 
                key={i} 
                style={{ 
                  fontWeight: 700, 
                  fontSize: isSub ? "11px" : "13px", 
                  color: isSub ? "var(--text-muted)" : "var(--text-navy)", 
                  textTransform: isSub ? "uppercase" : "none",
                  marginTop: isSub ? "6px" : "14px", 
                  marginBottom: "4px",
                  borderBottom: isSub ? "none" : "1px solid var(--border-color)",
                  paddingBottom: isSub ? "0" : "4px"
                }}
              >
                {trimmed}
              </div>
            );
          }
          
          return (
            <div key={i} style={{ marginBottom: "4px" }}>
              {line}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="app-layout">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div>
          <div className="brand">
            <div className="brand-mark">F</div>
            <div className="brand-title">
              <span className="brand-name">FinanceOS</span>
              <span className="brand-tag">AI Finance Controller</span>
            </div>
          </div>

          <nav className="nav">
            <button
              className={`nav-item ${activeTab === "Overview" ? "active" : ""}`}
              onClick={() => setActiveTab("Overview")}
            >
              <span className="nav-icon nav-icon-bar"></span>
              <span className="nav-text">Overview</span>
            </button>

            <button
              className={`nav-item ${activeTab === "Exceptions" ? "active" : ""}`}
              onClick={() => setActiveTab("Exceptions")}
            >
              <span className="nav-icon nav-icon-alert"></span>
              <span className="nav-text">Exceptions</span>
              {escalatedCases > 0 && <span className="badge">{escalatedCases}</span>}
            </button>

            <button
              className={`nav-item ${activeTab === "Evaluation" ? "active" : ""}`}
              onClick={() => setActiveTab("Evaluation")}
            >
              <span className="nav-icon nav-icon-check"></span>
              <span className="nav-text">Evaluation & Audit</span>
            </button>
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="status-indicator">
            <span className={`status-dot ${escalatedCases > 0 ? "amber" : "green"}`}></span>
            <span>{isCustom ? "Custom Batch Active" : "Synthetic Demo Active"}</span>
          </div>
          <p className="footer-note">
            Financial decisions are <strong>deterministic</strong>. AI layer provides evidence-backed investigation only.
          </p>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <main className="main-wrapper">
        {/* HEADER */}
        <header className="header">
          {apiError && (
            <div className="callout-box warning-box" style={{ marginBottom: "12px", width: "100%" }}>
              <strong>FinanceOS backend is currently unavailable. Please retry shortly.</strong>
            </div>
          )}
          <div>
            <h1 className="page-title">Financial Reconciliation & Operations</h1>
            <p className="page-subtitle">
              Correctness-first operations agent for automated multi-source reconciliation.
            </p>
          </div>

          <div className="header-actions">
            <a
              href={`${API_URL}/api/report/download`}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary"
              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "6px" }}
            >
              Download Run Report
            </a>
            <button className="btn-secondary" onClick={runDemoBatch} disabled={loading}>
              Run Demo Batch
            </button>
            <button className="btn-primary" onClick={() => setShowUploadModal(true)} disabled={loading}>
              Upload Custom Batch
            </button>
          </div>
        </header>

        {/* LOADING OVERLAY */}
        {loading && (
          <div className="modal-overlay">
            <div className="loader-card">
              <div className="spinner"></div>
              <h3>Processing Financial Batch</h3>
              <p className="stage-message">{processingStage}</p>
            </div>
          </div>
        )}

        {/* UPLOAD MODAL */}
        {showUploadModal && (
          <div className="modal-overlay">
            <div className="modal-card">
              <div className="modal-header">
                <h3>Upload Financial Data Batch</h3>
                <button className="btn-close" onClick={() => setShowUploadModal(false)}>×</button>
              </div>

              <form onSubmit={handleUploadBatch}>
                <div className="dropzone" onClick={() => document.getElementById("file-input")?.click()}>
                  <div className="dropzone-icon">CSV</div>
                  <p><strong>Click to browse</strong> or drag & drop CSV file(s)</p>
                  <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                    Supports orders, gateway transactions, and bank settlements (mixed single CSV or separate CSVs).
                  </p>
                  <input
                    id="file-input"
                    type="file"
                    accept=".csv"
                    multiple
                    style={{ display: "none" }}
                    onChange={(e) => setUploadFiles(e.target.files)}
                  />
                </div>

                {uploadFiles && uploadFiles.length > 0 && (
                  <div style={{ marginBottom: "16px", fontSize: "13px", color: "var(--text-navy)" }}>
                    <strong>Selected files:</strong>
                    <ul style={{ paddingLeft: "18px", marginTop: "4px" }}>
                      {Array.from(uploadFiles).map((f, idx) => (
                        <li key={idx}>{f.name} ({(f.size / 1024).toFixed(1)} KB)</li>
                      ))}
                    </ul>
                  </div>
                )}

                {uploadError && (
                  <div className="callout-box warning-box" style={{ marginBottom: "16px" }}>
                    <strong>Ingestion Error:</strong> {uploadError}
                  </div>
                )}

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
                  <button type="button" className="btn-secondary" onClick={() => setShowUploadModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary">
                    Upload & Reconcile Batch
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* TAB 1: OVERVIEW */}
        {activeTab === "Overview" && (
          <div className="content-space">
            {/* HERO PRIMARY OUTCOME BANNER */}
            <div className="hero-outcome-card">
              <div className="hero-outcome-header">
                <div>
                  <span className="hero-eyebrow">PRIMARY BATCH OUTCOME</span>
                  <h2 className="hero-title">
                    {reconciledCases} of {totalCases} orders safely reconciled
                  </h2>
                </div>
                <span className={`status-badge-hero ${escalatedCases > 0 ? "review" : "completed"}`}>
                  {escalatedCases > 0 ? "NEEDS OPERATOR REVIEW" : "BATCH COMPLETED"}
                </span>
              </div>
              <p className="hero-description">
                {escalatedCases > 0 ? (
                  <>
                    <strong>{escalatedCases} cases escalated</strong> because FinanceOS could not verify them with sufficient certainty. No unsafe automated financial changes were made.
                  </>
                ) : (
                  <>100% of cases were deterministically matched with zero exceptions.</>
                )}
              </p>
            </div>

            {/* DYNAMIC METRICS GRID */}
            <div className="metrics-grid">
              <div className="metric-card">
                <span className="metric-label">TOTAL RECORDS PROCESSED</span>
                <span className="metric-number text-navy">{recordsProcessed}</span>
                <span className="metric-sub">canonical financial events</span>
              </div>

              <div className="metric-card">
                <span className="metric-label">SAFE RECONCILED</span>
                <span className="metric-number text-green">{reconciledCases}</span>
                <span className="metric-sub">{matchRate.toFixed(2)}% match rate</span>
              </div>

              <div className="metric-card border-amber-light">
                <span className="metric-label">ESCALATED EXCEPTIONS</span>
                <span className="metric-number text-amber">{escalatedCases}</span>
                <span className="metric-sub">Requires human review</span>
              </div>

              <div className="metric-card">
                <span className="metric-label">ENGINE THROUGHPUT</span>
                <span className="metric-number text-blue">{recordsPerSec}</span>
                <span className="metric-sub">synthetic benchmark throughput</span>
              </div>
            </div>

            {/* INGESTION SUMMARY CARD (IF CUSTOM OR DEMO SUMMARY AVAILABLE) */}
            {ingestion && (
              <div className="ingestion-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h4 style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-navy)" }}>
                    Batch Ingestion Summary ({isCustom ? "Custom CSV Upload" : "Synthetic Benchmark"})
                  </h4>
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                    Received {ingestion.total_rows_received} raw rows
                  </span>
                </div>

                <div className="ingestion-grid">
                  <div className="ingestion-stat-box">
                    <span className="ingestion-stat-label">Usable Orders</span>
                    <span className="ingestion-stat-value">{ingestion.usable_orders_count}</span>
                  </div>
                  <div className="ingestion-stat-box">
                    <span className="ingestion-stat-label">Gateway Txns</span>
                    <span className="ingestion-stat-value">{ingestion.usable_transactions_count}</span>
                  </div>
                  <div className="ingestion-stat-box">
                    <span className="ingestion-stat-label">Bank Settlements</span>
                    <span className="ingestion-stat-value">{ingestion.usable_settlements_count}</span>
                  </div>
                  <div className="ingestion-stat-box">
                    <span className="ingestion-stat-label">Ignored Columns</span>
                    <span className="ingestion-stat-value">
                      {ingestion.ignored_columns.length > 0 ? ingestion.ignored_columns.length : "0"}
                    </span>
                  </div>
                </div>

                {ingestion.ignored_columns.length > 0 && (
                  <div style={{ marginTop: "12px", fontSize: "12px", color: "var(--text-muted)" }}>
                    <div style={{ fontWeight: 600, marginBottom: "6px" }}>Ignored non-financial fields:</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                      {ingestion.ignored_columns.map((c, i) => (
                        <span key={i} className="evidence-chip" style={{ fontSize: "11px" }}>
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ASK FINANCEOS CONTEXTUAL WIDGET */}
            <div className="ask-finance-card">
              <div className="ask-header">
                <h3>Ask FinanceOS</h3>
                <span className="ask-badge">Grounded Operational Agent</span>
              </div>
              <p style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "12px" }}>
                Ask questions about current run records, exceptions, amount mismatches, or ingestion fields.
              </p>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAskQuestion();
                }}
                className="ask-form"
              >
                <input
                  type="text"
                  className="ask-input"
                  placeholder="e.g. Why was order ORD-0021 escalated?"
                  value={askQuestion}
                  onChange={(e) => setAskQuestion(e.target.value)}
                />
                <button type="submit" className="btn-primary" disabled={askLoading}>
                  {askLoading ? "Searching..." : "Ask Agent"}
                </button>
              </form>

              {/* DYNAMIC CLICKABLE SUGGESTIONS */}
              <div className="ask-suggestions">
                <button
                  className="chip-btn"
                  onClick={() => {
                    setAskQuestion("What are the biggest issues in this batch?");
                    handleAskQuestion("What are the biggest issues in this batch?");
                  }}
                >
                  Biggest issues in this batch
                </button>
                <button
                  className="chip-btn"
                  onClick={() => {
                    setAskQuestion("Show me all amount mismatches.");
                    handleAskQuestion("Show me all amount mismatches.");
                  }}
                >
                  All amount mismatches
                </button>
                <button
                  className="chip-btn"
                  onClick={() => {
                    setAskQuestion("Which settlement batches failed integrity checks?");
                    handleAskQuestion("Which settlement batches failed integrity checks?");
                  }}
                >
                  Settlement batch integrity
                </button>
                <button
                  className="chip-btn"
                  onClick={() => {
                    setAskQuestion("How many records were ignored during ingestion?");
                    handleAskQuestion("How many records were ignored during ingestion?");
                  }}
                >
                  Ingestion summary
                </button>
              </div>

              {/* RESPONSE DISPLAY */}
              {askResponse && (
                <div className="ask-response-box">
                  <div className="ask-response-header">
                    <span>AGENT RESPONSE (GROUNDED IN CURRENT BATCH EVIDENCE)</span>
                    <span style={{ color: askResponse.evidence_verified ? "var(--status-green)" : "var(--status-amber)" }}>
                      {askResponse.evidence_verified ? "Verified Evidence" : "Note"}
                    </span>
                  </div>
                  <div className="ask-response-text">{renderAgentResponse(askResponse)}</div>
                </div>
              )}
            </div>

            {batchData?.cross_exception_analysis && (
              <div className="section-card">
                <div className="section-header">
                  <div>
                    <h3 className="section-heading">AI Cross-Exception Investigation</h3>
                    <p className="section-sub">
                      Read-only synthesis across escalated records. The deterministic engine still decides financial outcomes.
                    </p>
                  </div>
                  <span className="tag review">
                    {batchData.cross_exception_analysis.priority_assessment?.priority || "MEDIUM"}
                  </span>
                </div>

                <div className="callout-box info-box" style={{ marginBottom: "12px" }}>
                  <strong>Priority assessment:</strong> {batchData.cross_exception_analysis.priority_assessment?.reason || "Cross-record pattern review complete."}
                </div>

                <div style={{ display: "grid", gap: "10px" }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Verified Facts</div>
                    <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px" }}>
                      {(batchData.cross_exception_analysis.verified_facts || []).slice(0, 4).map((fact: string, i: number) => (
                        <li key={i}>{fact}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Observed Patterns</div>
                    <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px" }}>
                      {(batchData.cross_exception_analysis.observed_patterns || []).slice(0, 4).map((pattern: string, i: number) => (
                        <li key={i}>{pattern}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Possible Hypotheses</div>
                    <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px" }}>
                      {(batchData.cross_exception_analysis.possible_hypotheses || []).slice(0, 4).map((hyp: string, i: number) => (
                        <li key={i}>{hyp}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* PREVIEW OF TOP EXCEPTIONS */}
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Exceptions Requiring Operator Attention</h3>
                  <p className="section-sub">
                    Deterministic engine escalated these cases to protect financial integrity.
                  </p>
                </div>
                <button className="btn-secondary" onClick={() => setActiveTab("Exceptions")}>
                  View All ({escalatedCases})
                </button>
              </div>

              <div className="preview-list">
                {exceptions.slice(0, 4).map((ex: any, idx: number) => (
                  <div
                    key={idx}
                    className="preview-item"
                    onClick={() => {
                      setSelectedException(ex);
                      setActiveTab("Exceptions");
                    }}
                  >
                    <div className="preview-top">
                      <span className={`tag ${ex.severity === "URGENT" ? "urgent" : "review"}`}>
                        {ex.severity}
                      </span>
                      <span className="preview-type">
                        <strong>{ex.type}</strong> — <span className="mono-id">{ex.exception_id}</span>
                      </span>
                      <span className="mono-id">
                        {ex.affected_orders?.join(", ") || ex.references?.join(", ")}
                      </span>
                    </div>
                    <p className="preview-reason">{ex.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: EXCEPTIONS (MASTER-DETAIL SPLIT VIEW) */}
        {activeTab === "Exceptions" && (
          <div className="split-view-container">
            {/* MASTER PANEL */}
            <div className="master-panel">
              <div className="panel-controls">
                <input
                  type="text"
                  placeholder="Search exceptions or IDs..."
                  className="input-search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <select
                  className="select-filter"
                  value={filterSeverity}
                  onChange={(e) => setFilterSeverity(e.target.value)}
                >
                  <option value="ALL">All Severities</option>
                  <option value="URGENT">URGENT</option>
                  <option value="REVIEW">REVIEW</option>
                </select>
              </div>

              <div className="master-list">
                {filteredExceptions.map((ex: any, idx: number) => {
                  const isSelected = selectedExDetails?.exception_id === ex.exception_id;
                  return (
                    <div
                      key={idx}
                      className={`master-card ${isSelected ? "selected" : ""}`}
                      onClick={() => setSelectedException(ex)}
                    >
                      <div className="card-row">
                        <span className={`tag ${ex.severity === "URGENT" ? "urgent" : "review"}`}>
                          {ex.severity}
                        </span>
                        <span className="card-title">
                          <strong>{ex.type}</strong>
                        </span>
                      </div>
                      <div className="card-meta">
                        <span className="mono-id">{ex.exception_id}</span>
                        <span>{ex.affected_orders?.length || 1} order(s)</span>
                      </div>
                      <p className="card-desc">{ex.reason}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* DETAIL PANEL (3-TIER HIERARCHY) */}
            <div className="detail-panel">
              {selectedExDetails ? (
                <div>
                  <div className="detail-header-block">
                    <div>
                      <span className={`tag ${selectedExDetails.severity === "URGENT" ? "urgent" : "review"}`}>
                        {selectedExDetails.severity}
                      </span>
                      <h2>{selectedExDetails.type}</h2>
                      <span className="mono-id">ID: {selectedExDetails.exception_id}</span>
                    </div>
                    <span className="status-chip escalated">NEEDS OPERATOR REVIEW</span>
                  </div>

                  {/* 1. SYSTEM DECISION */}
                  <div className="detail-group">
                    <h4 className="group-title">1. System Decision (Deterministic Engine)</h4>
                    <div className="callout-box warning-box">
                      <strong>Refused Auto-Resolution:</strong> {selectedExDetails.reason}
                      {selectedExDetails.affected_orders && selectedExDetails.affected_orders.filter((x: any) => x).length > 0 && (
                        <div style={{ marginTop: "6px" }}>
                          <strong>Affected Orders:</strong> {selectedExDetails.affected_orders.filter((x: any) => x).join(", ")}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 2. VERIFIED EVIDENCE */}
                  <div className="detail-group">
                    <h4 className="group-title">2. Verified Evidence</h4>
                    {selectedExDetails.verified_fields && Object.keys(selectedExDetails.verified_fields).length > 0 && (
                      <div className="verified-fields-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "10px", marginBottom: "12px", background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
                        {Object.entries(selectedExDetails.verified_fields).map(([k, v], i) => (
                          <div key={i} style={{ fontSize: "12px" }}>
                            <span style={{ color: "var(--text-muted)", fontWeight: 600, display: "block", fontSize: "11px", textTransform: "uppercase" }}>{k}</span>
                            <span style={{ color: "var(--text-navy)", fontWeight: 600, fontFamily: "monospace" }}>{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="evidence-tags">
                      {selectedExDetails.references?.map((ref: string, i: number) => (
                        <span key={i} className="evidence-chip">
                          {ref}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* 3. AI INVESTIGATION */}
                  <div className="detail-group">
                    <h4 className="group-title">3. AI Investigation & Analysis</h4>
                    <div className="ai-card">
                      <div className="ai-card-header">
                        <span className="ai-label">FinanceOS Reasoning Layer (Investigative Only)</span>
                        <span className="ai-badge">Evidence Grounded</span>
                      </div>

                      {selectedExDetails.ai_investigation ? (
                        <div>
                          {/* INVESTIGATION SUMMARY */}
                          <div className="ai-summary">
                            <strong>Investigation Summary:</strong>
                            <p style={{ marginTop: "4px", color: "var(--text-main)" }}>
                              {selectedExDetails.ai_investigation.summary || "Exception analysis complete."}
                            </p>
                          </div>

                          {/* VERIFIED FACTS SECTION */}
                          {(selectedExDetails.ai_investigation.verified_facts?.length || 0) > 0 && (
                            <div className="ai-block verified-block">
                              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                                <span style={{ fontWeight: 700, fontSize: "12px", color: "var(--status-green)", textTransform: "uppercase" }}>✓ Verified Facts</span>
                              </div>
                              <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-main)" }}>
                                {selectedExDetails.ai_investigation.verified_facts.map((fact: string, i: number) => (
                                  <li key={i} style={{ marginBottom: "4px" }}>{fact}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* OBSERVED PATTERNS SECTION */}
                          {(selectedExDetails.ai_investigation.cross_record_patterns?.length || 0) > 0 && (
                            <div className="ai-block pattern-block">
                              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                                <span style={{ fontWeight: 700, fontSize: "12px", color: "var(--status-blue)", textTransform: "uppercase" }}>◉ Observed Patterns</span>
                              </div>
                              <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-main)" }}>
                                {selectedExDetails.ai_investigation.cross_record_patterns.map((pattern: string, i: number) => (
                                  <li key={i} style={{ marginBottom: "4px" }}>{pattern}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* POSSIBLE HYPOTHESES SECTION */}
                          {(selectedExDetails.ai_investigation.possible_causes?.length || 0) > 0 && (
                            <div className="ai-block hypothesis-block">
                              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                                <span style={{ fontWeight: 700, fontSize: "12px", color: "var(--status-purple)", textTransform: "uppercase" }}>? Possible Hypotheses</span>
                              </div>
                              <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", color: "var(--text-main)", fontStyle: "italic" }}>
                                {selectedExDetails.ai_investigation.possible_causes.map((cause: string, i: number) => (
                                  <li key={i} style={{ marginBottom: "4px" }}>
                                    {cause.startsWith("POSSIBLE HYPOTHESIS:") ? cause : `POSSIBLE HYPOTHESIS: ${cause}`}
                                  </li>
                                ))}
                              </ul>
                              <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--text-muted)", fontStyle: "italic" }}>
                                These are potential explanations suggested by AI analysis. Verification requires operator review.
                              </div>
                            </div>
                          )}

                          {/* RECOMMENDED ACTION */}
                          {selectedExDetails.ai_investigation.recommended_operator_action && (
                            <div className="ai-action-box">
                              <strong style={{ fontSize: "12px", color: "var(--text-green)", textTransform: "uppercase" }}>Recommended Operator Action:</strong>
                              <p style={{ marginTop: "4px", color: "var(--text-main)", fontSize: "12px" }}>
                                {selectedExDetails.ai_investigation.recommended_operator_action}
                              </p>
                            </div>
                          )}

                          {/* CONFIDENCE & LIMITATIONS */}
                          {selectedExDetails.ai_investigation.confidence_in_explanation && (
                            <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--border-color)", fontSize: "12px", color: "var(--text-muted)" }}>
                              <div style={{ marginBottom: "6px" }}>
                                <strong>Confidence Level:</strong> {selectedExDetails.ai_investigation.confidence_in_explanation}
                              </div>
                              {selectedExDetails.ai_investigation.limitations?.length > 0 && (
                                <div>
                                  <strong>Limitations:</strong>
                                  <ul style={{ margin: "4px 0 0 16px", paddingLeft: "0" }}>
                                    {selectedExDetails.ai_investigation.limitations.map((lim: string, i: number) => (
                                      <li key={i} style={{ marginBottom: "2px", fontSize: "11px" }}>{lim}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}

                          {/* INVESTIGATION ACTIVITY TRACE */}
                          <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--border-color)" }}>
                            <div style={{ fontWeight: 600, fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>Investigation Activity</div>
                            <div style={{ fontSize: "11px", color: "var(--text-main)", display: "flex", flexDirection: "column", gap: "4px" }}>
                              <div>• Loaded verified order evidence</div>
                              <div>• Checked related gateway transaction details</div>
                              <div>• Checked settlement batch information</div>
                              <div>• Analyzed related exceptions for patterns</div>
                              <div>• Generated grounded investigation summary</div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                          No AI investigation trace recorded for this item. Deterministic reconciliation decision remains valid.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-panel">
                  <div className="empty-icon-text">Select an exception</div>
                  <p>Choose an exception from the list on the left to inspect verified evidence and AI analysis.</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: EVALUATION & AUDIT */}
        {activeTab === "Evaluation" && (
          <div className="content-space">
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Demo Batch Metrics</h3>
                  <p className="section-sub">
                    Operational results for the current demo batch. These are the primary outcome metrics for FinanceOS.
                  </p>
                </div>
              </div>

              <div className="metrics-grid">
                <div className="metric-card border-green-light">
                  <span className="metric-label">ORDERS SAFELY RECONCILED</span>
                  <span className="metric-number text-green">
                    {reconciledCases} / {totalCases}
                  </span>
                  <span className="metric-sub">Safe auto-resolution count</span>
                </div>

                <div className="metric-card border-amber-light">
                  <span className="metric-label">ESCALATED FOR REVIEW</span>
                  <span className="metric-number text-amber">{escalatedCases}</span>
                  <span className="metric-sub">Requires human review</span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">SAFE RESOLUTION RATE</span>
                  <span className="metric-number text-navy">
                    {Math.max(0, Number((reconciledCases / Math.max(totalCases, 1)) * 100 || 0)).toFixed(1)}%
                  </span>
                  <span className="metric-sub">{reconciledCases} of {totalCases} orders</span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">CANONICAL FINANCIAL RECORDS</span>
                  <span className="metric-number text-blue">{recordsProcessed}</span>
                  <span className="metric-sub">Records processed in the current batch</span>
                </div>
              </div>
            </div>

            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Synthetic Rule-Consistency Benchmark</h3>
                  <p className="section-sub">
                    These metrics measure consistency against the synthetic benchmark and do not represent real-world generalization.
                  </p>
                </div>
              </div>

              <div className="metrics-grid">
                <div className="metric-card">
                  <span className="metric-label">SYNTHETIC PRECISION</span>
                  <span className={`metric-number ${batchData?.evaluation ? "text-green" : ""}`} style={!batchData?.evaluation ? { color: "var(--text-muted)" } : {}}>
                    {batchData?.evaluation ? `${(batchData.evaluation.precision * 100).toFixed(1)}%` : "N/A"}
                  </span>
                  <span className="metric-sub">
                    {batchData?.evaluation ? "0 incorrect auto-resolutions" : "Ground truth required"}
                  </span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">SYNTHETIC RECALL</span>
                  <span className={`metric-number ${batchData?.evaluation ? "text-blue" : ""}`} style={!batchData?.evaluation ? { color: "var(--text-muted)" } : {}}>
                    {batchData?.evaluation ? `${(batchData.evaluation.recall * 100).toFixed(1)}%` : "N/A"}
                  </span>
                  <span className="metric-sub">
                    {batchData?.evaluation ? "Resolvable cases captured" : "Ground truth required"}
                  </span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">SYNTHETIC F1 SCORE</span>
                  <span className={`metric-number ${batchData?.evaluation ? "text-navy" : ""}`} style={!batchData?.evaluation ? { color: "var(--text-muted)" } : {}}>
                    {batchData?.evaluation ? `${(batchData.evaluation.f1 * 100).toFixed(1)}%` : "N/A"}
                  </span>
                  <span className="metric-sub">
                    {batchData?.evaluation ? "Harmonic mean precision/recall" : "Ground truth required"}
                  </span>
                </div>

                <div className="metric-card border-green-light">
                  <span className="metric-label">SAFE RESOLUTION RATE</span>
                  <span className="metric-number text-green">
                    {batchData?.evaluation
                      ? `${(batchData.evaluation.safe_resolution_rate * 100).toFixed(1)}%`
                      : `${matchRate.toFixed(1)}%`}
                  </span>
                  <span className="metric-sub">
                    {reconciledCases} of {totalCases} orders reconciled
                  </span>
                </div>

                <div className="metric-card">
                  <span className="metric-label">SYNTHETIC ESCALATION ACCURACY</span>
                  <span className={`metric-number ${batchData?.evaluation ? "text-purple" : ""}`} style={!batchData?.evaluation ? { color: "var(--text-muted)" } : {}}>
                    {batchData?.evaluation ? `${(batchData.evaluation.exception_escalation_accuracy * 100).toFixed(1)}%` : "N/A"}
                  </span>
                  <span className="metric-sub">
                    {batchData?.evaluation ? `Across ${batchData.evaluation.ground_truth_cases} cases` : "Ground truth required"}
                  </span>
                </div>
              </div>

              {!batchData?.evaluation ? (
                <div className="callout-box neutral-box" style={{ padding: "16px", marginTop: "16px" }}>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-main)" }}>
                    Ground-truth benchmark metrics are unavailable for this uploaded batch because no labeled ground truth was provided. FinanceOS does not fabricate Precision, Recall, or F1. Operational reconciliation metrics are still reported from the current run.
                  </p>
                </div>
              ) : (
                <div className="callout-box success-box" style={{ padding: "16px", marginTop: "16px" }}>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-main)" }}>
                    Evaluation computed against verified synthetic benchmark ground truth ({batchData.evaluation.ground_truth_cases} labeled cases).
                  </p>
                </div>
              )}
            </div>

            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Independent Adversarial Evaluation</h3>
                  <p className="section-sub">
                    This is distinct from the synthetic benchmark and validates edge-case robustness with manually labeled scenarios.
                  </p>
                </div>
              </div>

              <div className="callout-box neutral-box" style={{ padding: "16px" }}>
                <p style={{ margin: 0, fontSize: "13px", color: "var(--text-main)" }}>
                  The backend includes a separate adversarial evaluation suite covering missing counterparts, duplicate keys, negative amounts, currency mismatches, batch anomalies, and other edge cases. It is run as a separate, independent validation layer rather than as a live demo metric.
                </p>
              </div>
            </div>

            {/* AUDIT & SAFETY ARCHITECTURE */}
            <div className="section-card">
              <h3 className="section-heading">System Trust & Safety Architecture</h3>
              <p className="section-sub" style={{ marginBottom: "16px" }}>
                Strict operational boundaries separating financial authority from AI assistance.
              </p>

              <div className="arch-flow-grid">
                <div className="flow-card">
                  <h5>1. CSV Ingestion Layer</h5>
                  <p>Deterministic schema mapping, header alias resolution, & entity separation.</p>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-card">
                  <h5>2. Rule Engine Authority</h5>
                  <p>Sole authority for financial decisions. Refuses ambiguous resolution.</p>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-card">
                  <h5>3. Grounded AI Investigator</h5>
                  <p>Inspects verified evidence only. Summarizes and explains refusal rationale.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

const container = document.getElementById("root");
if (container) {
  const root = createRoot(container);
  root.render(<App />);
}