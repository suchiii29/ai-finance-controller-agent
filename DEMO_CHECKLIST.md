# DEMO CHECKLIST & RECORDING GUIDE — FINANCEOS

> **Razorpay AI Buildathon 2026 • Track 04: AI Finance Controller**

Use this checklist to record tomorrow's submission video.

---

## 1. PRE-RECORDING SETUP (2 minutes before recording)

### Terminal 1: Backend API Server
```bash
cd /home/harshlife/ai-finance-controller/ai-finance-controller-agent/backend
source .venv/bin/activate
# Make sure OPENROUTER_API_KEY is present in backend/.env if demonstrating AI explanations
uvicorn app.main:app --reload --port 8000
```
*Verify API health:* Open `http://localhost:8000/health` → `{"status": "ok"}`

### Terminal 2: Frontend App Server
```bash
cd /home/harshlife/ai-finance-controller/ai-finance-controller-agent/frontend
npm run dev
```
*Verify App UI:* Open `http://localhost:5173`

---

## 2. CLICK-BY-CLICK DEMO FLOW (2-3 minute video)

### Step 1: Landing & Philosophy (0:00 - 0:30)
- **Action:** Open `http://localhost:5173`. Point out the header banner and the "Absolute Safety Boundary" card in the left sidebar.
- **Talking Point:** *"FinanceOS is an AI Finance Controller. Our core philosophy is simple: deterministic rules decide financial truth; AI investigates and explains exceptions. Money is never auto-reconciled on AI confidence alone."*

### Step 2: Run Batch Reconciliation (0:30 - 0:55)
- **Action:** Click the primary **`↻ Run Batch Reconciliation`** button at top right.
- **Talking Point:** *"We click 'Run Batch Reconciliation'. The backend processes a synthetic batch of 60 orders, 63 gateway transactions, and 16 bank settlements in about 8 milliseconds—around 16,000 records per second."*

### Step 3: Show Overview Metrics (0:55 - 1:20)
- **Action:** Highlight the summary cards:
  - `38 / 60 Orders Reconciled` (63.3% Safe Resolution Rate)
  - `22 Escalated for Safety`
  - `0 Incorrect Auto-Resolutions` (Zero false positives)
  - `100% Evaluation Precision`
- **Talking Point:** *"Out of 60 orders, 38 were 100% deterministically matched. 22 were safely escalated because evidence was ambiguous or incomplete—for example, settlement batch mismatches. We achieved 0 false auto-resolutions."*

### Step 4: Exception Queue & Evidence Drill-Down (1:20 - 2:00)
- **Action:** Click **"Exception Queue"** on the left menu (or click any item in the Priority Exception list). Select an exception like `EXC-c5eedc85` (Batch Sum Mismatch).
- **Talking Point:** *"Let's inspect an exception. Here you see three distinct tiers:*
  1. *System Decision: Escalated due to batch integrity rules.*
  2. *Verified Evidence: Exact order IDs, settlement batch IDs, and UTR references.*
  3. *AI Investigation: Grounded Gemini explanation surfacing observed facts, why auto-resolution was refused, and suggested next steps for human operators."*

### Step 5: Decisions Table & Honest Metrics (2:00 - 2:30)
- **Action:** Click **"All Decisions"** to show the 60-order table, then click **"Evaluation & Safety"** to show the isolated ground-truth comparison.
- **Talking Point:** *"In 'All Decisions', every order retains an auditable rule code like R10 or R1. Under 'Evaluation & Safety', we compare against isolated ground truth—achieving 100% Precision, 100% Recall, and 0 incorrect auto-resolutions. Ground truth is isolated from the inference path."*

---

## 3. VERIFICATION CHECKLIST BEFORE PRESSING RECORD

- [ ] FastAPI backend running on port 8000
- [ ] Vite frontend running on port 5173
- [ ] Page loaded cleanly at `http://localhost:5173`
- [ ] Clicked `Run Batch Reconciliation` and verified metrics render
- [ ] Clicked an exception and verified evidence + AI investigation box renders
- [ ] No red errors in browser console
