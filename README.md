# FinanceOS — AI Finance Controller

> **Razorpay AI Buildathon 2026 · Track 04: AI Finance Controller**

**FinanceOS is an AI-powered financial reconciliation agent that connects orders, payment gateway transactions, and bank settlements into a unified, auditable operations workflow. It automatically resolves safe financial matches using a deterministic rule engine while employing a bounded AI investigation agent to analyze verified evidence for exceptions. By separating financial decision authority from probabilistic reasoning, FinanceOS delivers 100% precision and verifiable audit trails for automated financial operations.**

---

## 🚀 Submission Links

### 🌐 Live Demo
**[Open the Deployed FinanceOS Application](https://ai-finance-controller-agent.vercel.app/)**

### 🎥 Demo Video
**[Watch the FinanceOS Demo Video](YOUR_VIDEO_LINK_HERE)**

---

## 🎯 Why FinanceOS Fits Track 04

FinanceOS directly fulfills the AI Finance Controller mandate by providing a complete, automated reconciliation and exception-handling loop:

1. **Schema-Aware Batch Ingestion:** Ingests and parses financial CSV records across Orders, Payment Gateway Transactions, and Bank Settlements.
2. **Multi-Source Financial Matching:** Links canonical payment intents to gateway net amounts and bank credit batches.
3. **Deterministic Financial Authority:** Applies explicit, 5-stage rule precedence to authorize reconciliations without probabilistic guessing.
4. **Measurable Safe Resolution:** Reconciles safe records automatically while measuring resolution throughput and accuracy.
5. **Exception Detection & Escalation:** Flags ambiguous or mismatched records into an auditable exception queue.
6. **Agentic AI Exception Investigation:** Deploys a bounded AI agent using read-only tools to inspect evidence, correlate records, and explain refusals.
7. **Actionable Operator Guidance:** Recommends concrete next operational steps to assist human operators in resolving escalated cases.
8. **Auditable Run Reports:** Generates downloadable, snapshot-in-time HTML audit reports with complete evidence trails and benchmark metrics.

---

## 📊 Verified Benchmark

Results measured out-of-band against the canonical synthetic ground-truth dataset:

| Metric | Measured Value | Meaning |
|---|---|---|
| **Precision** | **100.0%** | Zero false-positive auto-resolutions |
| **Recall** | **100.0%** | 100% of safely reconcilable cases captured |
| **F1 Score** | **100.0%** | Harmonic mean of precision and recall |
| **Safe Resolution Rate** | **63.3%** | 38 of 60 orders safely auto-reconciled |
| **Escalated Orders** | **22** | Ambiguous cases escalated to human review |
| **Total Test Suite** | **29 / 29 passing** | 100% test coverage across backend & agent flows |
| **Benchmark Dataset** | **139 records** | 60 Orders, 63 Gateway Txns, 16 Bank Settlements |

*Note: Ground-truth benchmark metrics are evaluated out-of-band. The Safe Resolution Rate (63.3%) reflects strict financial safety—refusing to guess on ambiguous records.*

---

## 💡 The Problem

Financial operations teams struggle to reconcile data across three independent systems:

```text
Order Management System (Order Intent)
                ↓
Payment Gateway Logs (Gross, Fee, Net)
                ↓
Bank Statements (Settlement Batches)
```

Manual reconciliation across thousands of records per day is slow, expensive, and prone to human error. Conversely, deploying a generic LLM directly to decide financial reconciliation introduces severe risk: a probabilistic model may confidently match records with subtle fee discrepancies or missing settlement credits.

In financial infrastructure, **a false-positive auto-resolution is far more dangerous than an escalation**.

---

## 🛠️ What FinanceOS Does

FinanceOS automates multi-source reconciliation using a correctness-first approach:

1. **Orders (Canonical Intent):** Expected payment amounts, currencies, and settlement SLA windows.
2. **Gateway Transactions (Processing):** Gross amounts, processing fees, net payouts, and settlement batch IDs.
3. **Bank Settlements (Payout):** Actual bank credit amounts, value dates, and batch identifiers.

FinanceOS links these three records. If all deterministic checks pass, the record is marked `RECONCILED`. If any check fails or evidence is ambiguous, it is marked `ESCALATED` for AI investigation.

---

## 🤖 AI Investigation Agent

When an order is escalated, FinanceOS deploys a bounded AI investigation agent (`app/investigation.py` & `app/agent.py`). The agent acts as an automated financial analyst:

* **Retrieves Verified Evidence:** Uses approved read-only tools (`get_exception_details`, `get_order_details`, `get_transaction_details`, `get_batch_details`).
* **Correlates Financial Records:** Connects order intents, gateway fee structures, and bank settlement batch totals.
* **Explains Deterministic Refusals:** Translates rule-engine trigger codes (e.g., `BATCH_SUM_MISMATCH_UNRESOLVED`) into plain-English explanations.
* **Recommends Operator Guidance:** Suggests concrete next steps (e.g., *"Verify gateway net total against bank credit for Batch SET-02"*).
* **Natural-Language Operational Interface:** Answers operator queries via "Ask FinanceOS" using active batch state.
* **Resilient Fallback Handling:** If the LLM provider is unavailable or times out, returns structured, evidence-grounded fallback explanations without interrupting reconciliation.

### 🔒 Financial Decision Boundary

FinanceOS maintains a strict architectural firewall between financial decision authority and AI reasoning:

* **Engine Authority:** The deterministic rule engine makes 100% of financial reconciliation decisions before AI investigation begins.
* **Read-Only Tools:** Agent tools are strictly getters; the AI cannot write to the database, modify transactions, or alter reconciliation states.
* **No Decision Override:** The AI agent cannot override an engine escalation or mark an unsafe record as reconciled.
* **Ground-Truth Isolation:** Ground truth is strictly isolated in `app/evaluation.py` and never imported or accessed during controller inference.

---

## ⚙️ How Reconciliation Works

For every order, FinanceOS executes a 5-stage deterministic pipeline:

1. **Counterpart Matching:** Link Order ID to Gateway Transaction ID (requires exactly one valid transaction).
2. **Arithmetic Verification:** Validate `Gross - Fee = Net` and `Gateway Gross = Order Amount`.
3. **Settlement Batch Aggregation:** Aggregate gateway net amounts in a batch and compare against Bank Settlement credit.
4. **Currency Check:** Ensure Order currency matches Gateway & Bank currencies.
5. **SLA Validation:** Confirm settlement value date falls within the expected SLA window.

If all 5 checks pass: `RECONCILED`. Otherwise: `ESCALATED`.

---

## 🛡️ Batch Integrity Safety

FinanceOS treats settlement batches as holistic financial integrity groups rather than evaluating transactions in total isolation:

```text
Gateway Net Amounts (TXN-A + TXN-B + TXN-C)
                     ↓
       Grouped by Settlement Batch ID
                     ↓
        Compared against Bank Credit
                     ↓
                 Mismatch?
                     ↓
      Can cause be safely isolated?
          /                      \
        YES                      NO
        /                          \
Isolate structural cause    Escalate affected orders
(Rule R5)                   (Rule R1)
```

If a bank credit discrepancy cannot be isolated to a specific transaction, FinanceOS escalates the entire affected batch. **It refuses to guess.**

---

## 🏗️ Architecture

```text
                 FINANCIAL CSV DATA
                        │
        ┌───────────────┼───────────────┐
        │               │               │
      Orders         Gateway          Bank
                   Transactions    Settlements
        │               │               │
        └───────────────┼───────────────┘
                        │
                        ▼
             Schema-Aware Ingestion
                        │
                        ▼
          Deterministic Rule Engine
                 /             \
                /               \
               ▼                 ▼
         RECONCILED          ESCALATED
                                  │
                                  ▼
                         Read-Only Evidence
                               Tools
                                  │
                                  ▼
                       AI Investigation Layer
                                  │
                                  ▼
                          Human Operator
```

---

## 📏 Reconciliation Rules

| Rule | Exception Type | Meaning / Trigger |
|---|---|---|
| **R1** | `BATCH_SUM_MISMATCH_UNRESOLVED` | Batch total mismatch; cause cannot be safely isolated |
| **R2** | `MISSING_COUNTERPART` | No gateway transaction exists for the order |
| **R3** | `DUPLICATE_CHARGE` | Multiple gateway transactions link to the same order |
| **R4** | `MALFORMED_VALUE` | Transaction contains non-numeric or missing amounts |
| **R5** | `BATCH_SUM_MISMATCH_ISOLATED` | Transaction identified as the isolated cause of batch mismatch |
| **R6** | `BROKEN_BATCH_LINK` | Gateway transaction lacks a settlement batch link |
| **R7** | `CURRENCY_MISMATCH` | Currency discrepancy across order/gateway/bank |
| **R8** | `AMOUNT_MISMATCH` | Gross/fee/net arithmetic mismatch |
| **R9** | `DATE_OUTSIDE_SLA` | Settlement date exceeds SLA window |
| **R10** | *(none)* | All 5 checks pass → `RECONCILED` |

*Additional source checks:* `DUPLICATE_KEY`, `UNFLAGGED_NEGATIVE_AMOUNT`, `ORPHAN_SETTLEMENT`, `UNRESOLVABLE_REFERENCE`.

---

## 📊 Evaluation & Audit Benchmarks

Ground-truth evaluation is performed **out-of-band** against the canonical synthetic benchmark (60 orders / 139 records):

- **Precision (100.0%):** Zero false-positive auto-resolutions. Every auto-reconciled order is verifiably correct.
- **Recall (100.0%):** Captured 100% of genuinely resolvable orders in the benchmark.
- **F1 Score (100.0%):** Perfect balance of precision and recall.
- **Safe Resolution Rate (63.3%):** 38 of 60 orders safely reconciled; 22 intentionally escalated due to complex anomalies.

---

## 🔎 Honest Evaluation for Custom CSV Uploads

FinanceOS supports arbitrary custom CSV uploads via schema-aware ingestion. 

For custom uploads without labeled ground truth:
- **Operational Metrics Surfaced:** Total records, reconciled count, escalated count, Safe Resolution Rate, and processing throughput.
- **Ground-Truth Metrics Set to N/A:** Precision, Recall, F1, and Escalation Accuracy are explicitly set to `N/A`.

FinanceOS **never fabricates benchmark accuracy** for custom datasets.

---

## 🔄 Failure Recovery

| Failure Mode | System Handling |
|---|---|
| **Missing API Key** | Engine runs deterministically; AI fallback responses rendered |
| **LLM Provider Timeout** | Exception caught gracefully; evidence summary rendered via deterministic fallback |
| **Malformed AI Response** | Fallback parser extracts evidence; zero crash |
| **Malformed CSV Value** | Flagged as `MALFORMED_VALUE`; excluded from matching |
| **Duplicate Transaction ID** | Flagged as `DUPLICATE_KEY` with URGENT severity |
| **Unrecognized CSV Schema** | HTTP 400 with honest error details; no silent corrupted processing |

---

## 📋 Auditability & Report Generation

FinanceOS generates downloadable, single-file HTML audit reports containing:
- Executive summary & operational counts.
- Ingestion summary & alias mapping log.
- Full exception register with evidence trails.
- Evaluation metrics table.
- System trust & safety architecture statement.

---

## 🎬 Demo Flow

1. Open FinanceOS (`http://localhost:5173`).
2. Click **Run Demo Batch** to execute the synthetic benchmark.
3. Review high-level metrics (Safe Resolution Rate, Precision, Recall, F1).
4. Inspect the Exception Register and click an escalated case to view its 3-tier evidence trail.
5. Use **Ask FinanceOS** to query batch status via natural language.
6. Click **Upload Custom CSV** to test custom data ingestion.
7. Click **Download Run Report** for an auditable HTML snapshot.

---

## 🛠️ Tech Stack

- **Frontend:** React 18, TypeScript, Vite, Vanilla CSS (Light fintech theme)
- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **Reconciliation Engine:** Pure Python (`app/engine/reconciliation.py`)
- **AI Agent Layer:** LangChain, OpenRouter (Gemini Flash via `openrouter/auto`)
- **Evaluation:** Isolated Python Evaluator (`app/evaluation.py`)

---

## 📁 Project Structure

```text
ai-finance-controller-agent/
├── backend/
│   ├── app/
│   │   ├── engine/
│   │   │   └── reconciliation.py
│   │   ├── main.py
│   │   ├── agent.py
│   │   ├── investigation.py
│   │   ├── tools.py
│   │   ├── ingestion.py
│   │   ├── evaluation.py
│   │   ├── llm.py
│   │   ├── models.py
│   │   ├── report_generator.py
│   │   └── data.py
│   ├── scripts/
│   │   ├── generate_data.py
│   │   └── benchmark.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── main.tsx
│       └── style.css
└── README.md
```

---

## 🚀 Local Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Clone & Install Backend

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd ai-finance-controller-agent/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py
```

### 2. Configure Environment (Optional)

Create `backend/.env`:
```text
OPENROUTER_API_KEY=your_key_here
```
*(If omitted, deterministic reconciliation and fallback evidence tools work automatically.)*

### 3. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Start Frontend

In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.

---

## 🧪 Testing

Run the complete 29-test suite:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. pytest -v
```

All 29 tests pass covering reconciliation rules, ingestion edge cases, agent tool execution, AI fallbacks, and evaluation isolation.

---

## ⚠️ Limitations

- **Synthetic Benchmark Data:** Default demo batch is generated with a fixed seed for audit reproducibility.
- **In-Memory Batch State:** Current active batch is stored in backend server memory.
- **Single-Tenant Prototype:** Built as a single-tenant operations console for Buildathon review.

---
## Failure Recovery

FinanceOS is designed to refuse unsafe reconciliation instead of forcing a match.

When the system encounters incomplete, ambiguous, or inconsistent financial data, it preserves the evidence and escalates the case for operator review.

Examples handled by the system include:

- Duplicate transaction keys → escalated as `DUPLICATE_KEY`
- Bank settlements without linked gateway transactions → `ORPHAN_SETTLEMENT`
- Gateway transactions referencing missing orders → `UNRESOLVABLE_REFERENCE`
- Multiple gateway transactions linked to one order → `DUPLICATE_CHARGE`
- Missing gateway counterparts → `MISSING_COUNTERPART`
- Settlement dates outside the allowed SLA → `DATE_OUTSIDE_SLA`
- Settlement batch totals that cannot be safely attributed → `BATCH_SUM_MISMATCH_UNRESOLVED`

The system does not guess or force a reconciliation when evidence is insufficient.

Instead:

1. The deterministic rule engine refuses unsafe resolution.
2. The affected case is recorded as an exception.
3. Verified evidence is preserved for investigation.
4. The AI layer explains the evidence and refusal rationale.
5. The case is escalated for operator review.

This ensures that failures in reconciliation do not become incorrect automated financial decisions.

## 🎯 Design Principle

> **"In financial operations, knowing when NOT to automate is part of automation."**

FinanceOS prioritizes absolute financial safety over aggressive auto-resolution. Refusing to guess on ambiguous records is a feature of responsible financial engineering.

---

## 📌 Submission Summary

| Dimension | Implementation |
|---|---|
| **Track** | Track 04 — AI Finance Controller |
| **Financial Authority** | 100% Deterministic Rule Engine |
| **AI Role** | Read-Only Exception Investigation Agent |
| **Precision / Recall / F1** | 100.0% / 100.0% / 100.0% (Synthetic Benchmark) |
| **Safe Resolution Rate** | 63.3% (38/60 orders safely reconciled) |
| **Test Coverage** | 29 / 29 Pytest Suite Passing |

---

### Built for Razorpay AI Buildathon 2026 — Track 04
**FinanceOS — Correctness-first financial automation with an evidence-grounded AI investigation agent.**
