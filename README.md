# FinanceOS — AI Finance Controller

> **Razorpay AI Buildathon 2026 · Track 04: AI Finance Controller**

**FinanceOS is an AI-powered financial reconciliation agent that connects orders, payment gateway transactions, and bank settlements into a unified, auditable operations workflow. It automatically resolves safe financial matches using a deterministic rule engine while employing a bounded AI investigation agent to analyze verified evidence for exceptions. The system keeps financial decision authority in the deterministic engine and uses AI strictly for evidence-backed investigation and operator guidance.**

> **Core philosophy:** "Knowing when not to automate is part of automation."

---

## 🚀 Submission Links

### 🌐 Live Demo
https://ai-finance-controller-agent.vercel.app/

### 🎥 Demo Video
**Placeholder for the final demo video:** [Add FinanceOS demo video URL here once recorded]

---

## 🎯 Why FinanceOS Fits Track 04

FinanceOS directly fulfills the AI Finance Controller mandate by providing a complete, automated reconciliation and exception-handling loop:

1. **Schema-Aware Batch Ingestion:** Ingests and parses financial CSV records across Orders, Payment Gateway Transactions, and Bank Settlements.
2. **Multi-Source Financial Matching:** Links canonical payment intents to gateway net amounts and bank credit batches.
3. **Deterministic Financial Authority:** Applies explicit, 5-stage rule precedence to authorize reconciliations without probabilistic guessing.
4. **Measurable Safe Resolution:** Reconciles safe records automatically while measuring resolution throughput and accuracy.
5. **Exception Detection & Escalation:** Flags ambiguous or mismatched records into an auditable exception queue.
6. **Bounded AI Investigation:** Deploys a read-only AI agent to inspect verified evidence, correlate records, and explain refusals without overriding decisions.
7. **Actionable Operator Guidance:** Recommends concrete next operational steps to assist human operators in resolving escalated cases.
8. **Auditable Run Reports:** Generates downloadable, snapshot-in-time HTML audit reports with complete evidence trails and benchmark metrics.

---

## 📊 Demo Batch Outcome

FinanceOS's primary operational outcome for the live demo batch is measured as follows:

| Metric | Measured Value | Meaning |
|---|---|---|
| **Orders Safely Reconciled** | **38 / 60** | Safe auto-resolution count |
| **Escalated for Review** | **22** | Cases held for operator review |
| **Safe Resolution Rate** | **63.3%** | Ratio of safe reconciliations to all orders |
| **Canonical Financial Records** | **139** | Total records processed in the demo batch |

### 🧪 Evaluation Overview

FinanceOS distinguishes three separate evaluation contexts:

1. **Demo batch metrics** — the live operational outcome of the current batch.
2. **Synthetic Rule-Consistency Benchmark** — a synthetic benchmark that measures consistency against a known rule-based ground truth.
3. **Independent Adversarial Evaluation** — an independent, manually labeled validation suite covering difficult edge cases.

#### Synthetic Rule-Consistency Benchmark

| Metric | Measured Value | Meaning |
|---|---|---|
| **Synthetic Precision** | **100.0%** | Rule-consistency benchmark metric |
| **Synthetic Recall** | **100.0%** | Rule-consistency benchmark metric |
| **Synthetic F1 Score** | **100.0%** | Rule-consistency benchmark metric |

*These metrics measure consistency against the synthetic benchmark and do not represent real-world generalization.*

#### Independent Adversarial Evaluation

The project includes a separate backend adversarial suite with manually labeled scenarios covering missing counterparts, duplicate keys, amount mismatches, negative amounts, currency mismatches, batch anomalies, and other edge cases. This evaluation is intentionally kept separate from the demo outcome and the synthetic benchmark.

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

* **Deterministic reconciliation engine makes financial decisions.** The engine is the sole authority for deciding whether an order is reconciled or escalated.
* **AI never overrides financial decisions.** The AI agent may investigate, explain, and recommend, but it cannot auto-reconcile or change a decision.
* **AI is read-only.** Agent tools are strictly getters; the AI cannot write to the database, modify transactions, or alter reconciliation states.
* **AI performs evidence-backed investigation and cross-record pattern synthesis.** It inspects verified evidence, correlates activity across related orders and batches, and summarizes likely operational causes while clearly separating facts, patterns, and hypotheses.
* **AI recommendations remain grounded in verified evidence.** Hypotheses are explicit and never treated as financial facts.
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

FinanceOS treats settlement batches as holistic financial integrity groups rather than evaluating transactions in total isolation. It refuses to guess when evidence is incomplete:

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

- **Synthetic Rule-Consistency Benchmark:** Precision, Recall, and F1 measure deterministic consistency against the synthetic benchmark. They do not prove real-world generalization.
- **Demo Batch Outcome:** 38 of 60 orders safely reconciled; 22 intentionally escalated due to complex anomalies.
- **Independent Adversarial Evaluation:** Separate manually labeled edge-case suite validates outlier handling without claiming generalization beyond the tested scenarios.

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
2. Click **Run Demo Batch** to execute the demo reconciliation workflow.
3. Review the primary demo batch metrics: 38 / 60 safely reconciled, 22 escalated, 63.3% safe resolution rate, and 139 processed records.
4. Inspect the Exception Register and click an escalated case to view the evidence trail and AI investigation.
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

Final suite status: **41 tests pass** covering reconciliation rules, ingestion edge cases, agent tool execution, AI fallbacks, evaluation isolation, and the independent adversarial validation suite.

---

## ⚠️ Limitations

- **Synthetic Benchmark Data:** Synthetic benchmark metrics validate deterministic consistency, not real-world generalization.
- **In-Memory Batch State:** Current active batch is stored in backend server memory.
- **Single-Tenant Prototype:** Built as a single-tenant operations console for Buildathon review.
- **AI Hypotheses Are Not Financial Facts:** AI-suggested causes remain hypotheses unless independently verified.
- **Escalation is a Safety Feature:** FinanceOS escalates uncertainty instead of guessing and auto-resolving unsafe financial data.

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
| **Demo Batch Metrics** | 38 / 60 safely reconciled; 22 escalated; 63.3% safe resolution rate; 139 records processed |
| **Synthetic Benchmark** | Precision / Recall / F1 shown separately as a rule-consistency benchmark only |
| **Independent Adversarial Evaluation** | Separate manual edge-case validation suite |
| **Test Coverage** | 41 / 41 Pytest Suite Passing |

---

### Built for Razorpay AI Buildathon 2026 — Track 04
**FinanceOS — Correctness-first financial automation with an evidence-grounded AI investigation agent.**
