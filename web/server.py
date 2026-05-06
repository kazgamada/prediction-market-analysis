from __future__ import annotations

import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.common.analysis import Analysis  # noqa: E402
from src.common.util.strings import snake_to_title  # noqa: E402

OUTPUT_DIR = ROOT / "output"
ANALYSIS_DIR = ROOT / "src" / "analysis"

app = FastAPI(title="Prediction Market Analysis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_analyses() -> dict[str, type[Analysis]]:
    out: dict[str, type[Analysis]] = {}
    for cls in Analysis.load(ANALYSIS_DIR):
        out[cls().name] = cls
    return out


ANALYSES = _load_analyses()


@dataclass
class Job:
    id: str
    analysis_name: str
    status: str = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    output_files: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


JOBS: dict[str, Job] = {}
JOBS_LOCK = Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=1)


def _run_job(job_id: str, name: str) -> None:
    job = JOBS[job_id]
    cls = ANALYSES.get(name)
    if cls is None:
        with JOBS_LOCK:
            job.status = "error"
            job.error = f"Analysis '{name}' not found"
            job.finished_at = datetime.utcnow().isoformat()
        return

    started = datetime.utcnow()
    with JOBS_LOCK:
        job.status = "running"
        job.started_at = started.isoformat()

    try:
        instance = cls()
        saved = instance.save(OUTPUT_DIR, formats=["png", "pdf", "csv", "json", "gif"])
        finished = datetime.utcnow()
        with JOBS_LOCK:
            job.status = "done"
            job.finished_at = finished.isoformat()
            job.duration_seconds = (finished - started).total_seconds()
            job.output_files = {
                fmt: f"/api/output/{Path(p).name}" for fmt, p in saved.items()
            }
    except Exception:
        finished = datetime.utcnow()
        with JOBS_LOCK:
            job.status = "error"
            job.error = traceback.format_exc()
            job.finished_at = finished.isoformat()
            job.duration_seconds = (finished - started).total_seconds()


@app.get("/api/analyses")
def list_analyses() -> list[dict]:
    items = []
    for name, cls in ANALYSES.items():
        instance = cls()
        items.append(
            {
                "name": instance.name,
                "title": snake_to_title(instance.name),
                "description": instance.description,
            }
        )
    items.sort(key=lambda x: x["title"])
    return items


@app.post("/api/analyses/{name}/run")
def run_analysis(name: str) -> dict:
    if name not in ANALYSES:
        raise HTTPException(status_code=404, detail=f"Analysis '{name}' not found")
    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id, analysis_name=name)
    with JOBS_LOCK:
        JOBS[job_id] = job
    EXECUTOR.submit(_run_job, job_id, name)
    return asdict(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return asdict(job)


@app.get("/api/output/{filename}")
def get_output(filename: str):
    path = (OUTPUT_DIR / filename).resolve()
    try:
        path.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
