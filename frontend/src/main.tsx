import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Data = any;

const API_URL = "http://localhost:8000";

function App() {
  const [data, setData] = useState<Data>();
  const [loading, setLoading] = useState(false);
  const [controller, setController] = useState<Data>();
  const [controllerLoading, setControllerLoading] = useState(false);
  const [controllerError, setControllerError] = useState("");
  const [activePage, setActivePage] = useState("Dashboard");

  async function runReconciliation() {
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/reconcile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction:
            "Reconcile all available settlements and identify anything requiring attention.",
        }),
      });

      if (!response.ok) {
        throw new Error("Reconciliation request failed");
      }

      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error(error);
      alert("Could not connect to the backend. Make sure FastAPI is running.");
    } finally {
      setLoading(false);
    }
  }

  async function runController() {
    setControllerLoading(true);
    setControllerError("");

    try {
      const response = await fetch(`${API_URL}/api/controller/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
        }),
      });

      if (!response.ok) {
        throw new Error("Controller request failed");
      }

      setController({ batch: await response.json() });
    } catch (error) {
      console.error(error);
      setControllerError("The controller could not complete. Review the reconciliation manually.");
    } finally {
      setControllerLoading(false);
    }
  }

  const counts = data?.result?.runtime_counts || {};
  const exceptions = data?.result?.exceptions || [];
  const decisions = data?.result?.decisions || [];

  // Sort incidents: URGENT → REVIEW → everything else
  const sortedExceptions = [...exceptions].sort((a: any, b: any) => {
    const priority: Record<string, number> = {
      URGENT: 0,
      REVIEW: 1,
      WARNING: 2,
    };

    return (
      (priority[a.severity] ?? 3) -
      (priority[b.severity] ?? 3)
    );
  });

  const urgentCount = exceptions.filter(
    (item: any) => item.severity === "URGENT"
  ).length;

  const exceptionTypes = counts?.exception_count_by_type
    ? Object.entries(counts.exception_count_by_type)
        .sort((a: any, b: any) => Number(b[1]) - Number(a[1]))
        .slice(0, 5)
    : [];

  const reviewItems = sortedExceptions.slice(0, 5);

  const reconciledCount =
    counts?.reconciled_count ??
    decisions.filter((d: any) => d.decision === "RECONCILED").length;

  const exceptionCount =
    counts?.exception_count ??
    decisions.filter((d: any) => d.decision !== "RECONCILED").length;

  return (
    <div className="app">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">F</div>
          <div>
            <strong>FinanceOS</strong>
            <span>AI Finance Controller</span>
          </div>
        </div>

        <nav>
          {[
            ["Dashboard", "⌂"],
            ["Reconciliation", "↻"],
            ["Exceptions", "⚠"],
            ["Analytics", "◫"],
          ].map(([name, icon]) => (
            <button
              key={name}
              className={`nav-item ${
                activePage === name ? "active" : ""
              }`}
              onClick={() => setActivePage(name)}
            >
              <span>{icon}</span>
              {name}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="system-status">
            <span className="status-dot"></span>
            System operational
          </div>
          <small>Evidence-first finance ops</small>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">FINANCE OPERATIONS</p>
            <h1>{activePage}</h1>
          </div>

          <div className="topbar-actions">
            <span className="live-status">
              <span className="live-dot"></span>
              Live system
            </span>
            <div className="avatar">FC</div>
          </div>
        </header>

        {/* HERO */}
        <section className="welcome-section">
          <div>
            <h2>Financial operations, under control.</h2>
            <p>
              Reconcile orders, gateway transactions and bank settlements.
              Exceptions are surfaced with verified evidence — never guessed.
            </p>
          </div>

          <button
            className="primary-button"
            onClick={runReconciliation}
            disabled={loading}
          >
            {loading ? "Running reconciliation..." : "↻ Run reconciliation"}
          </button>
          <button
            className="secondary-button"
            onClick={runController}
            disabled={controllerLoading}
          >
            {controllerLoading ? "Assessing state..." : "✦ Run AI Controller"}
          </button>
        </section>

        {!data ? (
          <>
            <section className="overview-banner">
              <div className="overview-icon">✦</div>
              <div>
                <h3>Your finance operations command center</h3>
                <p>
                  Run your first reconciliation to analyze settlements and
                  surface exceptions requiring attention.
                </p>
              </div>
              <span className="ready-badge">Ready to run</span>
            </section>

            <section className="feature-grid">
              <FeatureCard
                icon="✓"
                title="Automated reconciliation"
                text="Match orders, transactions and settlements automatically."
              />
              <FeatureCard
                icon="!"
                title="Exception intelligence"
                text="Surface anomalies instead of silently guessing outcomes."
              />
              <FeatureCard
                icon="◈"
                title="Evidence-first decisions"
                text="Every decision is backed by rules and supporting evidence."
              />
            </section>
          </>
        ) : (
          <>
            {/* CLEAN SUMMARY */}
            <section className="run-summary">
              <span className="success-icon">✓</span>
              <div>
                <strong>Reconciliation completed successfully</strong>
                <p>
                  {data.result?.records_processed || 0} records analyzed.
                  {" "}
                  {exceptionCount} items require attention.
                </p>
              </div>
              <span className="run-id">
                {data.result?.run_id}
              </span>
            </section>

            <ControllerPanel
              data={controller}
              loading={controllerLoading}
              error={controllerError}
              onRun={runController}
            />

            {/* METRICS */}
            <section className="metrics">
              <MetricCard
                label="Orders reconciled"
                value={reconciledCount}
                detail="Successfully matched"
                type="success"
              />
              <MetricCard
                label="Require review"
                value={exceptionCount}
                detail="Need human attention"
                type="warning"
              />
              <MetricCard
                label="Urgent incidents"
                value={urgentCount}
                detail="High priority issues"
                type="danger"
              />
              <MetricCard
                label="Records processed"
                value={data.result?.records_processed || 0}
                detail="Across all sources"
                type="neutral"
              />
            </section>

            {/* TWO COLUMN SECTION */}
            <section className="dashboard-grid">
              <div className="panel">
                <div className="panel-header">
                  <div>
                    <h3>Attention required</h3>
                    <p>Urgent incidents appear first</p>
                  </div>
                  <span className="count-badge">{exceptions.length}</span>
                </div>

                <div className="exception-list">
                  {reviewItems.map((item: any) => {
                    const exceptionType =
                      item.exception_type || item.type || "UNKNOWN";

                    const references =
                      item.refs || item.references || [];

                    return (
                      <div className="exception-row" key={item.exception_id}>
                        <div
                          className={`severity-icon ${(
                            item.severity || ""
                          ).toLowerCase()}`}
                        >
                          !
                        </div>

                        <div className="exception-info">
                          <strong>{formatName(exceptionType)}</strong>
                          <p>{item.reason}</p>
                          <small>
                            {references.length > 0
                              ? references.join(", ")
                              : item.exception_id}
                          </small>
                        </div>

                        <span
                          className={`severity-badge ${(
                            item.severity || ""
                          ).toLowerCase()}`}
                        >
                          {item.severity || "UNKNOWN"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* RISK BREAKDOWN */}
              <div className="panel risk-panel">
                <div className="panel-header">
                  <div>
                    <h3>Risk breakdown</h3>
                    <p>Most frequent exception categories</p>
                  </div>
                </div>

                {exceptionTypes.length > 0 ? (
                  <div className="risk-list">
                    {exceptionTypes.map(([name, value]: any, index) => {
                      const maxValue = Math.max(
                        ...exceptionTypes.map((item: any) =>
                          Number(item[1])
                        )
                      );

                      const width =
                        maxValue > 0
                          ? (Number(value) / maxValue) * 100
                          : 0;

                      return (
                        <div className="risk-item" key={name}>
                          <div className="risk-label">
                            <span>{formatName(name)}</span>
                            <strong>{value}</strong>
                          </div>

                          <div className="progress-track">
                            <div
                              className={`progress-bar bar-${index}`}
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="no-data">
                    No risk data available
                  </div>
                )}
              </div>
            </section>

            {/* RECENT DECISIONS */}
            <section className="panel decisions-panel">
              <div className="panel-header">
                <div>
                  <h3>Recent decisions</h3>
                  <p>Evidence-based reconciliation outcomes</p>
                </div>
                <span className="decision-count">
                  {decisions.length} decisions
                </span>
              </div>

              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Decision</th>
                      <th>Reason</th>
                      <th>Rule</th>
                    </tr>
                  </thead>

                  <tbody>
                    {decisions.slice(0, 8).map((decision: any) => (
                      <tr key={decision.order_id}>
                        <td>
                          <strong>{decision.order_id}</strong>
                        </td>

                        <td>
                          <span
                            className={`decision-badge ${
                              decision.decision === "RECONCILED"
                                ? "reconciled"
                                : "exception"
                            }`}
                          >
                            {decision.decision === "RECONCILED"
                              ? "✓ Reconciled"
                              : "⚠ Exception"}
                          </span>
                        </td>

                        <td className="reason-cell">
                          {decision.decision_reason}
                        </td>

                        <td>
                          <code>{decision.rule_id}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function ControllerPanel({
  data,
  loading,
  error,
  onRun,
}: {
  data?: Data;
  loading: boolean;
  error: string;
  onRun: () => void;
}) {
  const batch = data?.batch;
  const trace = batch?.activity_trace || [];

  return (
    <section className="controller-panel">
      <div className="controller-heading">
        <div>
          <p className="eyebrow">BOUNDED EVIDENCE REVIEW</p>
          <h3>AI Controller assessment</h3>
          <p>Read-only prioritization over the current deterministic run.</p>
        </div>
        <button className="secondary-button compact" onClick={onRun} disabled={loading}>
          {loading ? "Working..." : "Run assessment"}
        </button>
      </div>

      {error && <div className="controller-error">{error}</div>}
      {loading && <div className="controller-loading">Observing reconciliation state and collecting approved evidence...</div>}
      {!loading && !error && !batch && (
        <div className="controller-empty">Run the controller to prioritize incidents and gather an auditable evidence trail.</div>
      )}
      {batch && (
        <>
          <div className="controller-status-row">
            <span className={`controller-status ${String(batch.status).toLowerCase()}`}>{batch.status}</span>
            <span className="safety-label">No financial actions executed automatically</span>
          </div>
          <div className="batch-metrics">
            <MetricCard label="Batch records" value={batch.records_processed} detail="Orders, transactions, settlements" type="neutral" />
            <MetricCard label="Safe match rate" value={`${(batch.match_rate * 100).toFixed(1)}%`} detail={`${batch.reconciled_cases} of ${batch.total_cases} orders`} type="success" />
            <MetricCard label="Throughput" value={`${Number(batch.timings?.records_per_second || 0).toFixed(0)}`} detail="Measured records/sec" type="neutral" />
            <MetricCard label="Unresolved" value={batch.unresolved_exceptions?.length || 0} detail="Escalated incidents" type="danger" />
          </div>
          {batch.evaluation && <div className="accuracy-strip"><strong>Measured accuracy</strong><span>Precision {(batch.evaluation.precision * 100).toFixed(1)}%</span><span>Recall {(batch.evaluation.recall * 100).toFixed(1)}%</span><span>F1 {(batch.evaluation.f1 * 100).toFixed(1)}%</span><span>{batch.evaluation.incorrect_auto_resolutions} unsafe auto-resolutions</span></div>}
          <p className="priority-assessment">The deterministic engine processed the complete batch. {batch.escalated_cases} order cases remain escalated for human review.</p>
          <div className="controller-columns">
            <div>
              <h4>Verified findings</h4>
              {batch.unresolved_exceptions?.length ? (
                <ul>{batch.unresolved_exceptions.slice(0, 5).map((finding: any) => <li key={finding.exception_id}><strong>{finding.severity} {formatName(finding.type)}</strong>: {finding.reason}</li>)}</ul>
              ) : <p className="muted">No unresolved incidents were verified.</p>}
              <h4>Recommended human actions</h4>
              <ul><li>Review unresolved incidents using the evidence references.</li><li>Do not apply consequential financial adjustments without operator approval.</li></ul>
            </div>
            <div>
              <h4>Activity trace</h4>
              <ol className="trace-list">{trace.map((event: any, index: number) => <li key={`${event.action}-${index}`}><strong>{event.state}</strong> {event.action}{event.outcome ? `: ${event.outcome}` : ""}</li>)}</ol>
              <small className="evidence-count">{batch.tool_calls} approved tool calls · {batch.timings?.deterministic_reconciliation_seconds?.toFixed(4)}s deterministic processing</small>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function FeatureCard({
  icon,
  title,
  text,
}: {
  icon: string;
  title: string;
  text: string;
}) {
  return (
    <div className="feature-card">
      <span className="feature-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  type,
}: {
  label: string;
  value: number | string;
  detail: string;
  type: string;
}) {
  return (
    <div className={`metric-card ${type}`}>
      <div className="metric-top">
        <span>{label}</span>
        <span className="metric-symbol">
          {type === "success"
            ? "↗"
            : type === "warning"
            ? "!"
            : type === "danger"
            ? "!"
            : "◌"}
        </span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function formatName(value: string) {
  return String(value)
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

createRoot(document.getElementById("root")!).render(<App />);