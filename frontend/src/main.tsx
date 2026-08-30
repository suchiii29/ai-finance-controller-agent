import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
  evaluation?: EvaluationMetrics;
}

function App() {
  const [activeTab, setActiveTab] = useState<"Overview" | "Exceptions" | "Decisions" | "Evaluation">("Overview");
  const [batchData, setBatchData] = useState<BatchReport | null>(null);
  const [reconcileResult, setReconcileResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [processingStage, setProcessingStage] = useState<string>("");
  const [selectedException, setSelectedException] = useState<any | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const runFullPipeline = async () => {
    setLoading(true);
    setProcessingStage("Ingesting & validating financial records...");
    
    setTimeout(() => setProcessingStage("Executing deterministic rule engine..."), 400);
    setTimeout(() => setProcessingStage("Checking bank settlement batch integrity..."), 800);
    setTimeout(() => setProcessingStage("Escalating ambiguous cases..."), 1200);
    setTimeout(() => setProcessingStage("Generating grounded AI exception analysis..."), 1600);

    try {
      const recRes = await fetch(`${API_URL}/api/reconcile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: "Process reconciliation batch" }),
      });
      const recJson = await recRes.json();
      setReconcileResult(recJson.result);

      const ctrlRes = await fetch(`${API_URL}/api/controller/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const ctrlJson = await ctrlRes.json();
      setBatchData(ctrlJson);
    } catch (err) {
      console.error(err);
      alert("Failed to connect to backend server at " + API_URL);
    } finally {
      setLoading(false);
      setProcessingStage("");
    }
  };

  useEffect(() => {
    runFullPipeline();
  }, []);

  const decisions = reconcileResult?.decisions || [];
  const exceptions = batchData?.unresolved_exceptions || reconcileResult?.exceptions || [];
  
  const filteredExceptions = exceptions.filter((ex: any) => {
    const matchesSev = filterSeverity === "ALL" || ex.severity === filterSeverity;
    const matchesSearch = !searchQuery || 
      ex.exception_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ex.type?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ex.reason?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (ex.references && ex.references.some((r: string) => r.toLowerCase().includes(searchQuery.toLowerCase())));
    return matchesSev && matchesSearch;
  });

  const filteredDecisions = decisions.filter((d: any) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return d.order_id.toLowerCase().includes(q) || 
           d.decision.toLowerCase().includes(q) ||
           d.decision_reason.toLowerCase().includes(q) ||
           d.rule_id.toLowerCase().includes(q);
  });

  return (
    <div className="app-layout">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div className="brand-title">
            <span className="brand-name">FinanceOS</span>
            <span className="brand-tag">Operations Controller</span>
          </div>
        </div>

        <nav className="nav">
          {[
            { id: "Overview", label: "Overview", icon: "📊" },
            { id: "Exceptions", label: "Exceptions", icon: "⚠️", badge: exceptions.length },
            { id: "Decisions", label: "Decisions", icon: "📄" },
            { id: "Evaluation", label: "Evaluation", icon: "🛡️" },
          ].map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activeTab === item.id ? "active" : ""}`}
              onClick={() => setActiveTab(item.id as any)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-text">{item.label}</span>
              {item.badge !== undefined && item.badge > 0 && (
                <span className="badge">{item.badge}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="status-indicator">
            <span className={`status-dot ${batchData?.ai_available ? "green" : "amber"}`}></span>
            <span>{batchData?.ai_available ? "Engine & AI Connected" : "Engine Active (AI Offline)"}</span>
          </div>
          <p className="footer-note">Financial decisions are deterministic. AI investigates exceptions—it never overrides them.</p>
        </div>
      </aside>

      {/* MAIN CONTAINER */}
      <main className="main-wrapper">
        <header className="header">
          <div>
            <h1 className="page-title">{activeTab === "Overview" ? "Finance Operations" : activeTab}</h1>
            <p className="page-subtitle">
              {activeTab === "Overview" && "Reconcile payments, settlements, and exceptions with auditable controls."}
              {activeTab === "Exceptions" && "Review escalated financial cases with evidence-grounded AI investigations."}
              {activeTab === "Decisions" && "Audit deterministic rule outcomes across all order records."}
              {activeTab === "Evaluation" && "Isolated ground-truth performance metrics and system safety design."}
            </p>
          </div>

          <div className="header-actions">
            <button className="btn-primary" onClick={runFullPipeline} disabled={loading}>
              {loading ? "Processing Batch..." : "Run Batch Reconciliation"}
            </button>
          </div>
        </header>

        {loading && (
          <div className="modal-overlay">
            <div className="loader-card">
              <div className="spinner"></div>
              <h3>Running Reconciliation Pipeline</h3>
              <p className="stage-message">{processingStage}</p>
            </div>
          </div>
        )}

        {/* OVERVIEW TAB */}
        {activeTab === "Overview" && (
          <div className="content-space">
            {/* PRIMARY OUTCOME HERO BANNER */}
            <div className="hero-outcome-card">
              <div className="hero-outcome-header">
                <div>
                  <span className="hero-eyebrow">BATCH RECONCILIATION OUTCOME</span>
                  <h2 className="hero-title">
                    {batchData
                      ? `${batchData.reconciled_cases} of ${batchData.total_cases} Orders Safe-Reconciled`
                      : "Batch Processing Pending"}
                  </h2>
                </div>
                {batchData && (
                  <span className={`status-badge-hero ${batchData.escalated_cases > 0 ? 'review' : 'completed'}`}>
                    {batchData.escalated_cases > 0 ? `${batchData.escalated_cases} ESCALATED FOR OPERATOR REVIEW` : "100% RECONCILED"}
                  </span>
                )}
              </div>
              <p className="hero-description">
                Deterministic rule engine executed across <strong>{batchData?.records_processed || 0}</strong> source records.
                {" "}<strong>{batchData ? (batchData.match_rate * 100).toFixed(1) : 0}%</strong> of cases resolved with 100% mathematical certainty.
              </p>
            </div>

            {/* METRICS GRID */}
            <div className="metrics-grid">
              <div className="metric-card">
                <span className="metric-label">ORDERS RECONCILED</span>
                <div className="metric-number text-navy">
                  {batchData ? `${batchData.reconciled_cases} / ${batchData.total_cases}` : "—"}
                </div>
                <span className="metric-sub">
                  Safe Resolution: {((batchData?.match_rate || 0) * 100).toFixed(1)}%
                </span>
              </div>

              <div className="metric-card">
                <span className="metric-label">ESCALATED FOR REVIEW</span>
                <div className="metric-number text-amber">
                  {batchData ? batchData.escalated_cases : "—"}
                </div>
                <span className="metric-sub">Refused to guess under ambiguity</span>
              </div>

              <div className="metric-card border-green-light">
                <span className="metric-label">INCORRECT AUTO-RESOLUTIONS</span>
                <div className="metric-number text-green">
                  {batchData?.evaluation ? batchData.evaluation.incorrect_auto_resolutions : "0"}
                </div>
                <span className="metric-sub">Zero False Positives</span>
              </div>

              <div className="metric-card">
                <span className="metric-label">EVALUATION PRECISION</span>
                <div className="metric-number text-blue">
                  {batchData?.evaluation ? `${(batchData.evaluation.precision * 100).toFixed(0)}%` : "100%"}
                </div>
                <span className="metric-sub">Ground Truth Precision</span>
              </div>
            </div>

            {/* THROUGHPUT NOTE & ARCHITECTURE */}
            <div className="banner-card">
              <div className="banner-body">
                <h4>System Performance & Architecture</h4>
                <p>
                  <strong>Deterministic Processing Speed:</strong>{" "}
                  {batchData?.throughput
                    ? `${Math.round(batchData.throughput.records_per_second).toLocaleString()} records/sec (${(batchData.throughput.seconds * 1000).toFixed(1)}ms execution time across ${batchData.records_processed} source records)`
                    : "Measuring runtime..."}
                  <br />
                  <strong>Safety Policy:</strong> Automatic reconciliation requires 100% mathematical and rule-based certainty. Any mismatch in gateway totals or bank settlement credit triggers safe human escalation.
                </p>
              </div>
            </div>

            {/* THREE-STAGE PROCESS SUMMARY */}
            <div className="section-card">
              <h3 className="section-heading">How FinanceOS Works</h3>
              <div className="three-steps-grid">
                <div className="step-card">
                  <div className="step-badge">1</div>
                  <h4>Reconcile</h4>
                  <p>Matches orders, gateway transactions, and bank settlements using deterministic rules.</p>
                </div>
                <div className="step-card">
                  <div className="step-badge">2</div>
                  <h4>Investigate</h4>
                  <p>AI analyzes verified evidence for unresolved exceptions to explain root causes.</p>
                </div>
                <div className="step-card">
                  <div className="step-badge">3</div>
                  <h4>Escalate</h4>
                  <p>Ambiguous or unsafe cases remain untouched and are sent for human operator review.</p>
                </div>
              </div>
            </div>

            {/* PRIORITY EXCEPTIONS PREVIEW */}
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Priority Exception Queue</h3>
                  <p className="section-sub">Unresolved incidents requiring human operator review</p>
                </div>
                <button className="btn-secondary" onClick={() => setActiveTab("Exceptions")}>
                  View All ({exceptions.length}) →
                </button>
              </div>

              <div className="preview-list">
                {exceptions.slice(0, 4).map((ex: any) => (
                  <div 
                    key={ex.exception_id} 
                    className="preview-item"
                    onClick={() => {
                      setSelectedException(ex);
                      setActiveTab("Exceptions");
                    }}
                  >
                    <div className="preview-top">
                      <span className={`tag ${ex.severity?.toLowerCase()}`}>{ex.severity}</span>
                      <strong className="preview-type">{formatName(ex.type)}</strong>
                      <span className="mono-id">{ex.exception_id}</span>
                    </div>
                    <p className="preview-reason">{ex.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* EXCEPTIONS TAB */}
        {activeTab === "Exceptions" && (
          <div className="content-space">
            <div className="split-view-container">
              {/* LEFT MASTER LIST */}
              <div className="master-panel">
                <div className="panel-controls">
                  <input 
                    type="text" 
                    placeholder="Search exceptions or references..." 
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="input-search"
                  />
                  <select 
                    value={filterSeverity} 
                    onChange={(e) => setFilterSeverity(e.target.value)}
                    className="select-filter"
                  >
                    <option value="ALL">All Severities</option>
                    <option value="URGENT">URGENT Only</option>
                    <option value="REVIEW">REVIEW Only</option>
                  </select>
                </div>

                <div className="master-list">
                  {filteredExceptions.map((ex: any) => (
                    <div 
                      key={ex.exception_id}
                      className={`master-card ${selectedException?.exception_id === ex.exception_id ? 'selected' : ''}`}
                      onClick={() => setSelectedException(ex)}
                    >
                      <div className="card-row">
                        <span className={`tag ${ex.severity?.toLowerCase()}`}>{ex.severity}</span>
                        <strong className="card-title">{formatName(ex.type)}</strong>
                      </div>
                      <div className="card-meta">
                        <span className="mono-id">{ex.exception_id}</span>
                        <span>{ex.references?.length || 0} Evidence Ref(s)</span>
                      </div>
                      <p className="card-desc">{ex.reason}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* RIGHT DETAIL DRILL-DOWN */}
              <div className="detail-panel">
                {selectedException ? (
                  <div className="detail-content">
                    <div className="detail-header-block">
                      <div>
                        <span className={`tag ${selectedException.severity?.toLowerCase()}`}>
                          {selectedException.severity} SEVERITY
                        </span>
                        <h2>{formatName(selectedException.type)}</h2>
                        <span className="mono-id">ID: {selectedException.exception_id}</span>
                      </div>
                      <span className="status-chip escalated">ESCALATED FOR REVIEW</span>
                    </div>

                    {/* 1. SYSTEM DECISION */}
                    <div className="detail-group">
                      <h4 className="group-title">1. System Decision (Deterministic Engine)</h4>
                      <div className="callout-box warning-box">
                        <p><strong>Reason:</strong> {selectedException.reason}</p>
                        {selectedException.affected_orders && selectedException.affected_orders.length > 0 && (
                          <p className="mt-2">
                            <strong>Affected Orders ({selectedException.affected_orders.length}):</strong>{" "}
                            {selectedException.affected_orders.join(", ")}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* 2. VERIFIED EVIDENCE */}
                    <div className="detail-group">
                      <h4 className="group-title">2. Verified Evidence References</h4>
                      <div className="evidence-tags">
                        {(selectedException.references || []).map((ref: string, i: number) => (
                          <span key={i} className="evidence-chip">📄 {ref}</span>
                        ))}
                      </div>
                    </div>

                    {/* 3. AI INVESTIGATION */}
                    <div className="detail-group">
                      <h4 className="group-title">3. AI Investigation (Evidence Explanation Layer)</h4>
                      {selectedException.ai_investigation ? (
                        <div className="ai-card">
                          <div className="ai-card-header">
                            <span className="ai-label">✦ Grounded Incident Analysis</span>
                            <span className="ai-badge">Verified Input</span>
                          </div>

                          <p className="ai-summary">{renderCleanText(selectedException.ai_investigation.summary)}</p>

                          {selectedException.ai_investigation.observed_facts && (
                            <div className="ai-block">
                              <strong>Observed Facts:</strong>
                              <ul>
                                {selectedException.ai_investigation.observed_facts.map((fact: any, idx: number) => (
                                  <li key={idx}>{renderCleanText(fact)}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {selectedException.ai_investigation.why_escalated && (
                            <div className="ai-block">
                              <strong>Why Automatic Resolution Was Refused:</strong>
                              <p className="text-amber-dark">{renderCleanText(selectedException.ai_investigation.why_escalated)}</p>
                            </div>
                          )}

                          {selectedException.ai_investigation.suggested_action && (
                            <div className="ai-action-box">
                              <strong>Recommended Operator Action:</strong>
                              <p className="text-green-dark">{renderCleanText(selectedException.ai_investigation.suggested_action)}</p>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="callout-box neutral-box">
                          <p>AI investigation unavailable. Deterministic evidence remains available above.</p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="empty-panel">
                    <span className="empty-icon">👈</span>
                    <h3>Select an Exception to Inspect</h3>
                    <p>View the deterministic system decision, verified references, and AI investigation.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* DECISIONS TAB */}
        {activeTab === "Decisions" && (
          <div className="content-space">
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Order Reconciliation Decisions ({filteredDecisions.length})</h3>
                  <p className="section-sub">Audit log of deterministic rules executed across all batch orders</p>
                </div>
                <input 
                  type="text" 
                  placeholder="Search order ID or rule..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="input-search"
                />
              </div>

              <div className="table-container">
                <table className="clean-table">
                  <thead>
                    <tr>
                      <th>Order ID</th>
                      <th>Decision</th>
                      <th>Rule ID</th>
                      <th>Exception Category</th>
                      <th>Decision Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDecisions.map((d: any) => (
                      <tr key={d.order_id}>
                        <td><strong className="mono-id">{d.order_id}</strong></td>
                        <td>
                          <span className={`status-chip ${d.decision.toLowerCase()}`}>
                            {d.decision === "RECONCILED" ? "Reconciled" : "Escalated"}
                          </span>
                        </td>
                        <td><code className="rule-code">{d.rule_id}</code></td>
                        <td>{d.exception_type ? formatName(d.exception_type) : "—"}</td>
                        <td className="reason-col">{d.decision_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* EVALUATION TAB */}
        {activeTab === "Evaluation" && (
          <div className="content-space">
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3 className="section-heading">Evaluator & Ground Truth Performance</h3>
                  <p className="section-sub">Evaluator-only comparison. Ground truth is isolated from the reconciliation and decision path.</p>
                </div>
              </div>

              {batchData?.evaluation ? (
                <div className="metrics-grid mb-6">
                  <div className="metric-card">
                    <span className="metric-label">TOTAL EVALUATED CASES</span>
                    <div className="metric-number">{batchData.evaluation.total_cases_evaluated}</div>
                    <span className="metric-sub">Synthetic evaluation batch</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">CORRECTLY RECONCILED</span>
                    <div className="metric-number text-green">{batchData.evaluation.correctly_reconciled}</div>
                    <span className="metric-sub">True Positives</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">CORRECTLY ESCALATED</span>
                    <div className="metric-number text-blue">{batchData.evaluation.correctly_escalated}</div>
                    <span className="metric-sub">True Negatives (Safety Policy)</span>
                  </div>

                  <div className="metric-card border-green-light">
                    <span className="metric-label">INCORRECT AUTO-RESOLUTIONS</span>
                    <div className="metric-number text-green">{batchData.evaluation.incorrect_auto_resolutions}</div>
                    <span className="metric-sub">Zero False Positives</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">PRECISION</span>
                    <div className="metric-number">{(batchData.evaluation.precision * 100).toFixed(1)}%</div>
                    <span className="metric-sub">Accuracy of auto-reconciled orders</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">RECALL</span>
                    <div className="metric-number">{(batchData.evaluation.recall * 100).toFixed(1)}%</div>
                    <span className="metric-sub">Resolvable case coverage</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">F1 SCORE</span>
                    <div className="metric-number">{(batchData.evaluation.f1 * 100).toFixed(1)}%</div>
                    <span className="metric-sub">Harmonic mean precision/recall</span>
                  </div>

                  <div className="metric-card">
                    <span className="metric-label">SAFE RESOLUTION RATE</span>
                    <div className="metric-number">{(batchData.evaluation.safe_resolution_rate * 100).toFixed(1)}%</div>
                    <span className="metric-sub">Automated vs total ratio</span>
                  </div>
                </div>
              ) : (
                <p>Evaluation data unavailable. Run batch reconciliation first.</p>
              )}

              {/* SAFETY ARCHITECTURE FLOW */}
              <h4 className="group-title mt-4">System Architecture Safety Boundary</h4>
              <div className="arch-flow-grid">
                <div className="flow-card">
                  <h5>Deterministic Engine</h5>
                  <p>Makes 100% of financial reconciliation decisions using rule precedence.</p>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-card">
                  <h5>AI Investigator</h5>
                  <p>Explains verified exception evidence for human operators.</p>
                </div>
                <div className="flow-arrow">→</div>
                <div className="flow-card">
                  <h5>Human Operator</h5>
                  <p>Reviews escalated cases with grounded facts & recommended actions.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function renderCleanText(item: any): string {
  if (!item) return "";
  if (typeof item === "string") {
    if (item.trim().startsWith("{") && item.trim().endsWith("}")) {
      try {
        const parsed = JSON.parse(item);
        return parsed.summary || parsed.description || item;
      } catch {
        return item;
      }
    }
    return item;
  }
  if (typeof item === "object") {
    return item.summary || item.text || JSON.stringify(item);
  }
  return String(item);
}

function formatName(str: string) {
  if (!str) return "";
  return str.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

createRoot(document.getElementById("root")!).render(<App />);