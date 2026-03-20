"""FastAPI web frontend for the Requirements Decomposition System."""
import asyncio
import json
import logging
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import src.config as config
from src.cost_tracker import CostTracker
from src.decomposer import decompose_dig
from src.exporter import export_trees_to_xlsx
from src.loader import load_workbook_data, WorkbookData
from src.models import RequirementTree, ValidationResult
from src.refiner import refine_tree
from src.validator import run_semantic_judge, validate_tree_structure
from src.verifier import apply_vv_to_tree

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
app = FastAPI(title="reqdecomp")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

# In-memory state
ref_data: WorkbookData | None = None
jobs: dict[str, "Job"] = {}

# Model options (reuse from configure script)
MODELS = [
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic", "price": "$3 / $15 per Mtok", "cost_per_dig": "~$0.20-0.40"},
    {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "anthropic", "price": "$0.80 / $4 per Mtok", "cost_per_dig": "~$0.05-0.10"},
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4 (OpenRouter)", "provider": "openrouter", "price": "$3 / $15 per Mtok", "cost_per_dig": "~$0.20-0.40"},
    {"id": "anthropic/claude-haiku-4", "name": "Claude Haiku 4 (OpenRouter)", "provider": "openrouter", "price": "$0.80 / $4 per Mtok", "cost_per_dig": "~$0.05-0.10"},
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash (OpenRouter)", "provider": "openrouter", "price": "$0.15 / $0.60 per Mtok", "cost_per_dig": "~$0.01-0.03"},
    {"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3 (OpenRouter)", "provider": "openrouter", "price": "$0.27 / $1.10 per Mtok", "cost_per_dig": "~$0.02-0.05"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini (OpenRouter)", "provider": "openrouter", "price": "$0.15 / $0.60 per Mtok", "cost_per_dig": "~$0.01-0.03"},
]


@dataclass
class Job:
    id: str
    status: str = "running"
    dig_ids: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    cancelled: bool = False
    task: asyncio.Task | None = None

    def emit(self, event: dict):
        self.events.append(event)


def _load_xlsx():
    """Load or reload the xlsx data."""
    global ref_data
    xlsx_path = config.CWD / "GTR-SDS.xlsx"
    if not xlsx_path.exists():
        # Check package root too
        xlsx_path = config.PACKAGE_ROOT / "GTR-SDS.xlsx"
    if xlsx_path.exists():
        ref_data = load_workbook_data(xlsx_path)
        return len(ref_data.digs)
    return 0


def _reload_config():
    """Reload config from .env after settings change."""
    from dotenv import load_dotenv
    # Re-read .env
    env_path = config.PACKAGE_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    cwd_env = config.CWD / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=True)
    # Update module-level config values
    config.PROVIDER = os.getenv("PROVIDER", "anthropic")
    config.MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
    config.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    config.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


# Load on startup
@app.on_event("startup")
async def startup():
    _load_xlsx()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    dig_count = len(ref_data.digs) if ref_data else 0
    return templates.TemplateResponse("index.html", {
        "request": request,
        "dig_count": dig_count,
        "model": config.MODEL,
        "provider": config.PROVIDER,
    })


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Block upload during running jobs
    running = [j for j in jobs.values() if j.status == "running"]
    if running:
        raise HTTPException(409, "Cannot upload while a job is running")

    xlsx_path = config.CWD / "GTR-SDS.xlsx"
    with open(xlsx_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    count = _load_xlsx()
    return {"status": "ok", "dig_count": count}


@app.post("/run")
async def run(request: Request):
    if not ref_data:
        raise HTTPException(400, "No xlsx loaded. Upload a file first.")

    body = await request.json()
    dig_input = body.get("dig_ids", "").strip()
    settings = {
        "max_depth": min(int(body.get("max_depth", 4)), 4),
        "max_breadth": min(int(body.get("max_breadth", 3)), 5),
        "skip_vv": body.get("skip_vv", False),
        "skip_judge": body.get("skip_judge", False),
    }

    # Parse DIG IDs
    if dig_input:
        dig_ids = [d.strip() for d in dig_input.split(",") if d.strip()]
        missing = [d for d in dig_ids if d not in ref_data.digs]
        if missing:
            raise HTTPException(400, f"DIG(s) not found: {', '.join(missing)}")
    else:
        dig_ids = list(ref_data.digs.keys())

    job = Job(id=str(uuid.uuid4())[:8], dig_ids=dig_ids, settings=settings)
    jobs[job.id] = job
    job.task = asyncio.create_task(_run_job_async(job))
    return {"job_id": job.id}


async def _run_job_async(job: Job):
    """Wrapper to run the blocking pipeline in a thread."""
    try:
        await asyncio.to_thread(_run_job, job)
    except Exception as e:
        job.status = "error"
        job.emit({"type": "error", "message": str(e)})


def _run_job(job: Job):
    """Run the decomposition pipeline (blocking, runs in thread)."""
    settings = job.settings
    total = len(job.dig_ids)
    job.emit({"type": "started", "total_digs": total, "job_id": job.id})

    total_cost = 0.0
    total_api_calls = 0
    total_nodes = 0

    for idx, dig_id in enumerate(job.dig_ids, 1):
        if job.cancelled:
            job.status = "cancelled"
            job.emit({"type": "cancelled"})
            return

        dig = ref_data.digs[dig_id]
        job.emit({"type": "dig_started", "dig_id": dig_id, "index": idx, "total": total,
                  "dig_text": dig["dig_text"][:80]})

        cost_tracker = CostTracker(model=config.MODEL)

        try:
            # Decompose
            job.emit({"type": "phase", "dig_id": dig_id, "phase": "decompose", "detail": "Building requirement tree"})
            tree = decompose_dig(
                dig_id=dig_id, dig_text=dig["dig_text"], ref_data=ref_data,
                max_depth=settings["max_depth"], max_breadth=settings["max_breadth"],
                skip_vv=settings["skip_vv"], cost_tracker=cost_tracker,
            )

            if not tree.root:
                job.emit({"type": "error", "dig_id": dig_id, "message": "No requirements generated"})
                continue

            nodes = tree.count_nodes()
            job.emit({"type": "phase", "dig_id": dig_id, "phase": "decompose_done",
                      "detail": f"{nodes} requirements"})

            # V&V
            if not settings["skip_vv"]:
                job.emit({"type": "phase", "dig_id": dig_id, "phase": "vv",
                          "detail": f"Generating V&V for {nodes} requirements"})
                apply_vv_to_tree(tree, ref_data, cost_tracker)

            # Structural validation
            structural_errors = validate_tree_structure(
                tree, ref_data, settings["max_depth"], settings["max_breadth"])

            # Semantic judge + refinement
            semantic_review = None
            if not settings["skip_judge"]:
                job.emit({"type": "phase", "dig_id": dig_id, "phase": "judge", "detail": "Reviewing tree"})
                semantic_review = run_semantic_judge(tree, cost_tracker)

                if semantic_review.status != "pass":
                    job.emit({"type": "phase", "dig_id": dig_id, "phase": "refine",
                              "detail": f"{len(semantic_review.issues)} issues"})
                    tree = refine_tree(tree, semantic_review, ref_data, cost_tracker)
                    structural_errors = validate_tree_structure(
                        tree, ref_data, settings["max_depth"], settings["max_breadth"])
                    semantic_review = run_semantic_judge(tree, cost_tracker)

            tree.validation = ValidationResult(
                structural_errors=structural_errors,
                semantic_review=semantic_review,
            )
            tree.cost = cost_tracker.get_summary()

            # Save JSON
            config.OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
            json_path = config.OUTPUT_JSON_DIR / f"{dig_id}.json"
            json_path.write_text(tree.model_dump_json(indent=2), encoding="utf-8")

            summary = cost_tracker.get_summary()
            dig_cost = summary.total_cost_usd
            total_cost += dig_cost
            total_api_calls += summary.api_calls
            total_nodes += tree.count_nodes()

            job.emit({"type": "dig_complete", "dig_id": dig_id, "nodes": tree.count_nodes(),
                      "levels": tree.max_depth(), "cost": round(dig_cost, 4)})
            job.emit({"type": "cost", "total_cost": round(total_cost, 4), "api_calls": total_api_calls})

        except Exception as e:
            logger.error(f"Error processing DIG {dig_id}: {e}")
            job.emit({"type": "error", "dig_id": dig_id, "message": str(e)})

    # Export xlsx
    try:
        config.OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
        json_files = sorted(config.OUTPUT_JSON_DIR.glob("*.json"))
        trees = [RequirementTree.model_validate_json(f.read_text(encoding="utf-8")) for f in json_files]
        export_trees_to_xlsx(trees, config.OUTPUT_XLSX_DIR / "results.xlsx")
    except Exception as e:
        logger.error(f"Export failed: {e}")

    job.status = "complete"
    job.emit({"type": "complete", "total_digs": total, "total_nodes": total_nodes,
              "total_cost": round(total_cost, 4)})


@app.get("/stream/{job_id}")
async def stream(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        sent = 0
        while True:
            while sent < len(job.events):
                event = job.events[sent]
                yield f"data: {json.dumps(event)}\n\n"
                sent += 1
            if job.status in ("complete", "error", "cancelled"):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/cancel/{job_id}")
async def cancel(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.cancelled = True
    return {"status": "cancelling"}


@app.get("/results")
async def results():
    json_dir = config.OUTPUT_JSON_DIR
    if not json_dir.exists():
        return {"results": []}
    results = []
    for f in sorted(json_dir.glob("*.json")):
        try:
            tree = RequirementTree.model_validate_json(f.read_text(encoding="utf-8"))
            cost_data = tree.cost
            total_cost = sum(e.cost_usd for e in cost_data.breakdown) if cost_data else 0
            results.append({
                "dig_id": tree.dig_id,
                "dig_text": tree.dig_text[:80],
                "nodes": tree.count_nodes(),
                "levels": tree.max_depth(),
                "cost": round(total_cost, 4),
            })
        except Exception:
            pass
    return {"results": results}


@app.get("/results/{dig_id}")
async def result_detail(dig_id: str):
    json_path = config.OUTPUT_JSON_DIR / f"{dig_id}.json"
    if not json_path.exists():
        raise HTTPException(404, "Result not found")
    tree = RequirementTree.model_validate_json(json_path.read_text(encoding="utf-8"))
    return tree.model_dump()


@app.get("/export")
async def export():
    config.OUTPUT_XLSX_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.OUTPUT_XLSX_DIR / "results.xlsx"
    json_dir = config.OUTPUT_JSON_DIR
    if not json_dir.exists():
        raise HTTPException(404, "No results to export")
    json_files = sorted(json_dir.glob("*.json"))
    if not json_files:
        raise HTTPException(404, "No results to export")
    trees = [RequirementTree.model_validate_json(f.read_text(encoding="utf-8")) for f in json_files]
    export_trees_to_xlsx(trees, output_path)
    return FileResponse(output_path, filename="results.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/settings")
async def get_settings():
    return {
        "provider": config.PROVIDER,
        "model": config.MODEL,
        "has_anthropic_key": bool(config.ANTHROPIC_API_KEY),
        "has_openrouter_key": bool(config.OPENROUTER_API_KEY),
        "models": MODELS,
    }


@app.post("/settings")
async def update_settings(request: Request):
    body = await request.json()
    env_path = config.PACKAGE_ROOT / ".env"
    lines = [
        "# Requirements Decomposition System Configuration",
        f"PROVIDER={body.get('provider', config.PROVIDER)}",
        f"MODEL={body.get('model', config.MODEL)}",
        "",
    ]
    ak = body.get("anthropic_key", "").strip() or config.ANTHROPIC_API_KEY
    if ak:
        lines.append(f"ANTHROPIC_API_KEY={ak}")
    ork = body.get("openrouter_key", "").strip() or config.OPENROUTER_API_KEY
    if ork:
        lines.append(f"OPENROUTER_API_KEY={ork}")
    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")
    _reload_config()
    return {"status": "ok", "provider": config.PROVIDER, "model": config.MODEL}


@app.post("/dry-run")
async def dry_run(request: Request):
    if not ref_data:
        raise HTTPException(400, "No xlsx loaded")
    body = await request.json()
    dig_input = body.get("dig_ids", "").strip()
    max_depth = min(int(body.get("max_depth", 4)), 4)
    max_breadth = min(int(body.get("max_breadth", 3)), 5)
    skip_vv = body.get("skip_vv", False)
    skip_judge = body.get("skip_judge", False)

    n = len(ref_data.digs) if not dig_input else len([d for d in dig_input.split(",") if d.strip()])
    max_nodes = sum(max_breadth ** i for i in range(max_depth))
    calls_per_dig = max_nodes * 2 + 1
    if skip_vv:
        calls_per_dig = max_nodes + 1
    if skip_judge:
        calls_per_dig -= 1

    return {
        "digs": n,
        "max_calls_per_dig": calls_per_dig,
        "max_total_calls": n * calls_per_dig,
    }


@app.post("/update")
async def update_software():
    """Pull latest from GitHub and reinstall."""
    import subprocess
    try:
        # Check if git is available
        git_check = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if git_check.returncode != 0:
            return {"status": "error", "message": "Git is not installed. Download updates manually from GitHub."}

        # Pull latest
        pull = subprocess.run(
            ["git", "pull"], capture_output=True, text=True,
            cwd=str(config.PACKAGE_ROOT), timeout=30,
        )
        if pull.returncode != 0:
            return {"status": "error", "message": "Git pull failed: " + pull.stderr.strip()}

        if "Already up to date" in pull.stdout:
            return {"status": "ok", "message": "Already up to date.", "updated": False}

        # Reinstall package
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
            capture_output=True, text=True,
            cwd=str(config.PACKAGE_ROOT), timeout=60,
        )

        changes = pull.stdout.strip()
        return {
            "status": "ok",
            "message": "Updated! Restart the server to apply changes.",
            "updated": True,
            "details": changes,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/check-updates")
async def check_updates():
    """Check if there are remote updates available."""
    import subprocess
    try:
        # Fetch remote without merging
        subprocess.run(
            ["git", "fetch", "--quiet"], capture_output=True, text=True,
            cwd=str(config.PACKAGE_ROOT), timeout=15,
        )
        # Compare local vs remote
        result = subprocess.run(
            ["git", "rev-list", "HEAD..@{u}", "--count"],
            capture_output=True, text=True,
            cwd=str(config.PACKAGE_ROOT), timeout=10,
        )
        behind = int(result.stdout.strip()) if result.returncode == 0 else 0
        return {"behind": behind, "available": behind > 0}
    except Exception:
        return {"behind": 0, "available": False}


def start_server(port: int = 8000):
    """Start the web server."""
    import uvicorn
    print(f"\n  reqdecomp web interface starting...")
    print(f"  Open http://localhost:{port} in your browser\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
