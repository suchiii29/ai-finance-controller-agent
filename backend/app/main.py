from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
import os

from app.agent import run_agent, ask_finance_agent, run_controller_agent, run_batch_controller
from app.tools import (
    get_reconciliation_result,
    set_custom_batch,
    set_demo_batch,
    is_custom_upload,
    get_current_ingestion_summary,
    get_current_report,
    set_current_report,
)
from app.ingestion import process_csv_upload
from app.investigation import investigate_and_explain_highest_priority
from app.evaluation import evaluate_batch, load_ground_truth
from app.report_generator import generate_html_report

app = FastAPI(title="FinanceOS — AI Finance Controller")

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
def reconcile(request: ReconcileRequest = ReconcileRequest()):
    """Run reconciliation on the synthetic demo batch."""
    set_demo_batch()
    summary = run_agent(request.instruction)
    result = get_reconciliation_result()
    report = run_batch_controller()
    ground_truth_path = Path(__file__).resolve().parents[2] / "data" / "generated" / "ground_truth.json"
    if ground_truth_path.exists():
        report.evaluation = evaluate_batch(
            result,
            load_ground_truth(ground_truth_path),
        )
    set_current_report(report)

    return {
        "summary": summary,
        "result": result.model_dump(mode="json"),
    }


@app.post("/api/upload")
async def upload_batch(files: list[UploadFile] = File(...)):
    """
    Upload one or more CSV files containing financial records.
    Ingests records schema-specifically and runs the deterministic reconciliation engine.
    Ground-truth evaluation is explicitly disabled for custom batch uploads.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    files_content: list[tuple[str, bytes]] = []
    for file in files:
        content = await file.read()
        files_content.append((file.filename or "uploaded.csv", content))

    orders, txns, settlements, summary = process_csv_upload(files_content)

    if not summary.success:
        raise HTTPException(
            status_code=400,
            detail={
                "error": summary.error_message or "CSV ingestion failed",
                "summary": summary.model_dump(mode="json")
            }
        )

    set_custom_batch(orders, txns, settlements, summary)
    report = run_batch_controller()
    report.evaluation = None  # Explicitly unavailable for custom user uploads
    set_current_report(report)

    return {
        "ingestion_summary": summary.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "result": get_reconciliation_result().model_dump(mode="json"),
    }


@app.post("/api/agent")
@app.post("/api/ask")
def ask_agent(request: AgentRequest):
    """Query Ask FinanceOS dynamically against the current batch run data."""
    response = ask_finance_agent(request.question)
    result = get_reconciliation_result()

    return {
        "response": response,
        "answer": response.get("answer") if isinstance(response, dict) else str(response),
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

    # Ground truth evaluation is ONLY active for synthetic demo dataset
    if not is_custom_upload():
        ground_truth_path = Path(__file__).resolve().parents[2] / "data" / "generated" / "ground_truth.json"
        if ground_truth_path.exists():
            report.evaluation = evaluate_batch(
                get_reconciliation_result(),
                load_ground_truth(ground_truth_path),
            )
    else:
        report.evaluation = None

    set_current_report(report)
    return report.model_dump(mode="json")


@app.get("/api/report/download")
def download_report():
    """
    Generates and returns the HTML run report from the current run snapshot state.
    Does NOT rerun reconciliation.
    """
    report = get_current_report()
    if report is None:
        report = run_batch_controller()
        if not is_custom_upload():
            ground_truth_path = Path(__file__).resolve().parents[2] / "data" / "generated" / "ground_truth.json"
            if ground_truth_path.exists():
                report.evaluation = evaluate_batch(
                    get_reconciliation_result(),
                    load_ground_truth(ground_truth_path),
                )
        else:
            report.evaluation = None
        set_current_report(report)

    html_content = generate_html_report(report)
    return HTMLResponse(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename=financeos_report_{report.run_id}.html"}
    )


@app.get("/api/investigate/priority")
def investigate_priority():
    """Investigate the highest-priority reconciliation incident."""
    result = investigate_and_explain_highest_priority()
    return result