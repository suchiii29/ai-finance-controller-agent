# AI Finance Controller Agent

A deterministic, evidence-based finance reconciliation agent built for the Razorpay AI Buildathon concept.

## Stack
- Python 3.11+
- FastAPI backend
- LangChain for natural-language request parsing/reporting only
- Deterministic reconciliation engine for every financial decision
- React + Vite + TypeScript frontend

## Architecture

```text
DETERMINISTIC RECONCILIATION ENGINE
				↓
VERIFIED READ-ONLY EVIDENCE TOOLS
				↓
BOUNDED AI CONTROLLER
				↓
PRIORITIZATION + HUMAN ESCALATION
				↓
AUDITABLE ACTIVITY TRACE
```

The engine in `backend/app/engine/reconciliation.py` remains the source of truth for every reconciliation decision. The controller can decide what evidence to inspect next within a bounded set of approved read-only tools. It cannot execute refunds, settlements, payments, ledger changes, or other financial actions. IDs for detail tools must come from previously observed deterministic tool results.

The API returns structured controller status, verified evidence, recommended human actions, uncertainties, and a high-level trace. The trace contains operational events only and does not expose model chain-of-thought.

The complete batch endpoint also reports derived evaluation metrics when the evaluator-only `data/generated/ground_truth.json` is present. Ground-truth labels are never returned to the agent or API client.

## Safety boundary
The LLM never decides whether money is reconciled. `engine/reconciliation.py` makes every decision using deterministic rules. Ground truth is generated separately and is only used by offline evaluation.

## Run
### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_data.py
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Benchmark
```bash
cd backend
python -m scripts.benchmark
```

The benchmark processes the complete batch, reports source-record throughput and order-case metrics, and compares decisions with evaluator-only synthetic labels. It does not require Ollama.
