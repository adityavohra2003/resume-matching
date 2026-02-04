import os
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
import psycopg2
import redis

from app.db import get_conn, init_db
from pydantic import BaseModel
from typing import Optional


app = FastAPI(title="Resume Matching API", version="0.1.0")
class JobDescriptionCreate(BaseModel):
    title: Optional[str] = None
    content: str


# --- Readiness checks (Phase 0.5) ---
def check_postgres() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    cur.fetchone()
    cur.close()
    conn.close()

def check_redis() -> None:
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    r.ping()


@app.on_event("startup")
def on_startup():
    # Create tables if not present
    init_db()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    errors = {}
    try:
        check_postgres()
    except Exception as e:
        errors["postgres"] = str(e)

    try:
        check_redis()
    except Exception as e:
        errors["redis"] = str(e)

    if errors:
        return {"status": "not_ready", "errors": errors}

    return {"status": "ready"}


# --- Phase 1.0: Ingestion ---
@app.post("/resumes")
async def upload_resume(file: UploadFile = File(...)):
    # Basic validation
    if file.filename is None or file.filename.strip() == "":
        raise HTTPException(status_code=400, detail="Missing filename")

    allowed = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
        "application/msword",  # doc
    }
    # Some browsers may send octet-stream; we won’t hard fail, but we record it.
    content_type = file.content_type

    resume_id = uuid.uuid4()
    upload_dir = Path(os.getenv("UPLOAD_DIR", "/data")) / "resumes"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    storage_path = upload_dir / f"{resume_id}_{safe_name}"

    # Save file to disk
    data = await file.read()
    storage_path.write_bytes(data)

    # Store metadata in Postgres
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO resumes (id, filename, content_type, storage_path, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (str(resume_id), safe_name, content_type, str(storage_path), "UPLOADED"),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "resume_id": str(resume_id),
        "filename": safe_name,
        "content_type": content_type,
        "status": "UPLOADED",
    }


@app.get("/resumes/{resume_id}")
def get_resume(resume_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, filename, content_type, storage_path, status, created_at
        FROM resumes
        WHERE id = %s
        """,
        (resume_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")

    return {
        "id": str(row[0]),
        "filename": row[1],
        "content_type": row[2],
        "storage_path": row[3],
        "status": row[4],
        "created_at": row[5].isoformat(),
    }

# --- Phase 1.1: Job Descriptions ---
@app.post("/job-descriptions")
def create_job_description(payload: JobDescriptionCreate):
    jd_id = uuid.uuid4()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO job_descriptions (id, title, content, status)
        VALUES (%s, %s, %s, %s)
        """,
        (str(jd_id), payload.title, payload.content, "CREATED"),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "jd_id": str(jd_id),
        "title": payload.title,
        "status": "CREATED",
    }


@app.get("/job-descriptions/{jd_id}")
def get_job_description(jd_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, content, status, created_at
        FROM job_descriptions
        WHERE id = %s
        """,
        (jd_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Job description not found")

    return {
        "id": str(row[0]),
        "title": row[1],
        "content": row[2],
        "status": row[3],
        "created_at": row[4].isoformat(),
    }
