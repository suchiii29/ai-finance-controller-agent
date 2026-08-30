# FinanceOS — AI Finance Controller & Reconciliation Agent

> **Track 04: AI Finance Controller • Razorpay AI Buildathon 2026**

FinanceOS is an evidence-first, high-throughput financial reconciliation system that closes payment reconciliation loops across synthetic batches while strictly maintaining financial safety.

---

## Central Product Philosophy

> **Deterministic systems decide financial truth. AI investigates, explains, prioritizes, and communicates uncertainty.**

FinanceOS operates on a safety-first boundary:
1. **Deterministic Engine:** Reconciles transactions automatically when evidence is 100% conclusive.
2. **Conservative Escalation:** Refuses to guess or force auto-resolutions when settlement data is ambiguous or batch totals mismatch.
3. **Bounded AI Agent:** Investigates escalated exceptions, surfaces verified facts from evidence references, explains refusal reasons, and recommends safe next steps for human operators. **The LLM cannot alter reconciliation outcomes or perform financial mutations.**

---

## System Architecture

```text
       ┌────────────────────────────────────────────────────────┐
       │   RAW BATCH INGESTION (Orders, Txns, Bank Statements)  │
       └───────────────────────────┬────────────────────────────┘
                                   │
       ┌───────────────────────────▼────────────────────────────┐
       │     DETERMINISTIC FINANCIAL RECONCILIATION ENGINE       │
       │   (5-Stage Pipeline, 10 Rules, Batch Integrity Check)  │
       └─────────────┬────────────────────────────┬─────────────┘
                     │                            │
            [100% Conclusive]                    [Ambiguous / Exception]
                     │                            │
                     ▼                            ▼
           ┌──────────────────┐        ┌────────────────────────────┐
           │    RECONCILED    │        │     EXCEPTIONS QUEUE       │
           │  (38/60 Orders)  │        │     (22/60 Escalated)      │
           └──────────────────┘        └─────────────┬──────────────┘
                                                     │
                                                     ▼
                                       ┌────────────────────────────┐
                                       │   VERIFIED EVIDENCE TOOLS  │
                                       │   (Read-Only Data Access)  │
                                       └─────────────┬──────────────┘
                                                     │
                                                     ▼
                                       ┌────────────────────────────┐
                                       │   BOUNDED AI INVESTIGATOR  │
                                       │ (OpenRouter / Gemini Flash)│
                                       └─────────────┬──────────────┘
                                                     │
                                                     ▼
                                       ┌────────────────────────────┐
                                       │ AUDITABLE HUMAN ESCALATION │
                                       │ (Grounded Facts + Next Step)│
                                       └────────────────────────────┘
```

---

## Key Features & Demo Strengths

- **High-Throughput Batch Processing:** Reconciles 139 records (60 orders, 63 gateway transactions, 16 bank settlements) in **~8ms (~16,000 records/sec)**.
- **Measured Accuracy (Ground Truth Isolated):**
  - **Precision:** `100%` (Zero false positives / zero incorrect auto-resolutions)
  - **Recall:** `100%` (Zero missed resolvable cases)
  - **Safe Resolution Rate:** `63.3%` (38 reconciled, 22 escalated)
- **Settlement Batch Safety Rule:** If a bank settlement credit mismatches the gateway net total and the cause is unattributable, *all orders in that settlement batch are safely escalated*.
- **Graceful Fallback:** If the AI provider is offline or unconfigured (`OPENROUTER_API_KEY`), the reconciliation engine completes fully and surfaces deterministic evidence without failure.
- **Auditability:** Every decision retains an immutable evidence list referencing order IDs, gateway transaction IDs, settlement batch IDs, and UTRs.

---

## Project Structure

```text
ai-finance-controller-agent/
├── backend/
│   ├── app/
│   │   ├── engine/reconciliation.py   # Core 5-stage deterministic engine
│   │   ├── agent.py                   # Controller & batch orchestration loop
│   │   ├── investigation.py           # Structured AI evidence investigation layer
│   │   ├── llm.py                     # Centralized OpenRouter/Gemini provider
│   │   ├── tools.py                   # Approved read-only evidence tools
│   │   ├── models.py                  # Pydantic schema definitions
│   │   ├── evaluation.py              # Isolated evaluator (ground truth comparison)
│   │   └── main.py                    # FastAPI application server
│   ├── scripts/
│   │   ├── generate_data.py           # Synthetic dataset generator
│   │   └── benchmark.py               # Performance & evaluation benchmark runner
│   ├── tests/                         # Pytest test suite (9/9 passing)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx                   # FinanceOS Operations Dashboard (React)
│   │   └── style.css                  # Modern dark fintech design system
│   ├── index.html                     # Valid HTML5 entry with Google Fonts
│   ├── package.json
│   └── vite.config.ts
└── data/generated/                    # Synthetic financial CSVs + ground_truth.json
```

---

## Tech Stack & Architecture

- **Frontend:** React 18, Vite, TypeScript, Vanilla CSS (Dark Fintech Design System)
- **Backend API:** Python 3.10+, FastAPI, Uvicorn, Pydantic
- **Deterministic Reconciliation Engine:** Pure Python (`app/engine/reconciliation.py`), 5-stage pipeline, 10 rules
- **AI Investigation Layer:** LangChain (`langchain-openai`) integrated with OpenRouter (`openrouter/auto` / Gemini Flash)
- **Evaluation Engine:** Isolated evaluator (`app/evaluation.py`) comparing results against `data/generated/ground_truth.json`

---

## Deployment Strategy & Hosting Guide

### Recommended Strategy: Render / Railway (Backend) + Vercel / Netlify (Frontend)

1. **Frontend Deployment (Vercel / Netlify)**
   - Connect repository or deploy `frontend/` directory.
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Environment Variables:
     - `VITE_API_URL`: `https://your-backend-service.onrender.com` (Your deployed backend API URL)

2. **Backend Deployment (Render / Railway / Cloud Run)**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment Variables:
     - `OPENROUTER_API_KEY`: Your secret OpenRouter key (*Never exposed to frontend*)
     - `CORS_ORIGINS`: `https://your-frontend-app.vercel.app` (Or `*`)

---

## Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Generate synthetic batch data (60 orders, 63 txns, 16 settlements)
python scripts/generate_data.py

# Optional: Add your OpenRouter API key to backend/.env
# OPENROUTER_API_KEY=sk-or-v1-...

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** in your browser.

### 3. Run Offline Benchmark
```bash
cd backend
source .venv/bin/activate
python -m scripts.benchmark
```

---

## Safety & Evaluation Guarantees

1. **Ground Truth Isolation:** Ground truth (`data/generated/ground_truth.json`) is never imported or accessed by `engine/reconciliation.py`, `agent.py`, or `investigation.py`. It is loaded only by `evaluation.py` for post-hoc metrics.
2. **Read-Only Agent Tools:** Agent tools are strictly read-only getters (`get_order_details`, `get_exception_details`, etc.). No state mutation functions exist in the agent interface.
3. **No Key Exposure:** All API keys are loaded via backend environment variables. The frontend bundle contains zero secret credentials.


