from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

from app.agent import run_agent, ask_finance_agent, run_controller_agent, run_batch_controller
from app.tools import get_reconciliation_result
from app.investigation import investigate_and_explain_highest_priority
from app.evaluation import evaluate_batch, load_ground_truth
app = FastAPI(title="AI Finance Controller Agent")

import os

cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
if "*" in origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReconcileRequest(BaseModel):
    instruction: str = "Reconcile all available settlements"


class AgentRequest(BaseModel):
    question: str


class ControllerRequest(BaseModel):
    goal: str = (
        "Assess the current financial reconciliation state and tell me "
        "what needs attention first."
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/reconcile")
def reconcile(request: ReconcileRequest):
    summary = run_agent(request.instruction)
    result = get_reconciliation_result(force_refresh=True)

    return {
        "summary": summary,
        "result": result.model_dump(mode="json"),
    }


@app.post("/api/agent")
def ask_agent(request: AgentRequest):
    answer = ask_finance_agent(request.question)
    result = get_reconciliation_result()

    return {
        "answer": answer,
        "result": result.model_dump(mode="json"),
    }


@app.post("/api/controller")
def run_controller(request: ControllerRequest):
    """Run the bounded Finance Controller workflow with an auditable trace."""

    response = run_controller_agent(request.goal)
    return response.model_dump(mode="json")


@app.post("/api/controller/run")
def run_controller_batch():
    """Process and report the complete current reconciliation batch."""

    report = run_batch_controller()
    ground_truth_path = Path(__file__).resolve().parents[2] / "data" / "generated" / "ground_truth.json"
    if ground_truth_path.exists():
        report.evaluation = evaluate_batch(
            get_reconciliation_result(),
            load_ground_truth(ground_truth_path),
        )
    return report.model_dump(mode="json")
    
@app.get("/api/investigate/priority")
def investigate_priority():
    """
    Investigate the highest-priority reconciliation incident.

    Financial facts come from the deterministic reconciliation engine.
    The local AI model only explains verified evidence.
    """

    result = investigate_and_explain_highest_priority()

    return result