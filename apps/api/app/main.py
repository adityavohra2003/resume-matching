import os
import uuid
from pathlib import Path
from typing import Optional

import redis
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from psycopg2.extras import Json

from app.db import get_conn, init_db
from app.embeddings import embed_text
from app.extractors import extract_text
from app.parser import parse_resume
from app.routes_match import router as match_router



app = FastAPI(title="Resume Matching API", version="0.2.0")
app.include_router(match_router)



class JobDescriptionCreate(BaseModel):
    title: Optional[str] = None
    content: str


# ---------- Phase 0.5: Readiness checks ----------
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


# ---------- Phase 2 + Phase 3 helpers ----------
def set_status(resume_id: str, status: str, raw_text: str | None = None) -> None:
    conn = get_conn()
    cur = conn.cursor()

    if raw_text is None:
        cur.execute(
            "UPDATE resumes SET status=%s, updated_at=NOW() WHERE id=%s",
            (status, resume_id),
        )
    else:
        cur.execute(
            "UPDATE resumes SET status=%s, raw_text=%s, updated_at=NOW() WHERE id=%s",
            (status, raw_text, resume_id),
        )

    conn.commit()
    cur.close()
    conn.close()


def clean_text_basic(text: str) -> str:
    return " ".join((text or "").split())


def set_phase3_outputs(
    resume_id: str,
    clean_text: str,
    parsed_json: dict,
    embedding: list[float],
    embedding_model: str,
) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE resumes
        SET status=%s,
            clean_text=%s,
            parsed_json=%s,
            embedding=%s,
            embedding_model=%s,
            updated_at=NOW()
        WHERE id=%s
        """,
        ("PROCESSED", clean_text, Json(parsed_json), embedding, embedding_model, resume_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def process_resume_text(resume_id: str, storage_path: str) -> None:
    """
    Runs in background (FastAPI BackgroundTasks).
    Phase 2: Extract text (no OCR)
    Phase 3: Clean + Parse (existing parser.py) + Embed + Store
    """
    try:
        print(f"[bg] started process_resume_text resume_id={resume_id}")

        set_status(resume_id, "PROCESSING")

        text = extract_text(Path(storage_path))

        # If tiny text, likely scanned PDF -> mark for OCR later (but we don't do OCR now)
        if len((text or "").strip()) < 200:
            set_status(resume_id, "NEEDS_OCR", text)
            return

        # store extracted text (Phase 2 output)
        set_status(resume_id, "EXTRACTED", text)

        # -------- Phase 3 --------
        clean = clean_text_basic(text)
        parsed = parse_resume(clean)  # DO NOT CHANGE NLP PART
        embedding = embed_text(clean)
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

        set_phase3_outputs(resume_id, clean, parsed, embedding, embedding_model)

    except Exception as e:
        print(f"[bg] ERROR resume_id={resume_id}: {repr(e)}")
        set_status(resume_id, "FAILED", f"ERROR: {e}")


# ---------- Phase 1.0: Resume ingestion ----------
@app.post("/resumes")
async def upload_resume(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if file.filename is None or file.filename.strip() == "":
        raise HTTPException(status_code=400, detail="Missing filename")

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

    # Kick off background extraction + Phase 3 processing
    background_tasks.add_task(process_resume_text, str(resume_id), str(storage_path))

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
        SELECT id, filename, content_type, storage_path, status,
               created_at, updated_at, clean_text, parsed_json, embedding_model
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
        "updated_at": row[6].isoformat() if row[6] else None,
        "clean_text": row[7],
        "parsed_json": row[8],
        "embedding_model": row[9],
    }


@app.get("/resumes/{resume_id}/text")
def get_resume_text(resume_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status, raw_text FROM resumes WHERE id=%s", (resume_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")

    return {"id": resume_id, "status": row[0], "raw_text": row[1]}


# ---------- Phase 1.1: Job Descriptions ----------
@app.post("/job-descriptions")
def create_job_description(payload: JobDescriptionCreate):
    jd_id = uuid.uuid4()

    clean = clean_text_basic(payload.content)
    embedding = embed_text(clean)
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO job_descriptions (id, title, content, status, clean_text, embedding, embedding_model)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (str(jd_id), payload.title, payload.content, "CREATED", clean, embedding, embedding_model),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"jd_id": str(jd_id), "title": payload.title, "status": "CREATED"}


@app.get("/job-descriptions/{jd_id}")
def get_job_description(jd_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, content, status, created_at, embedding_model
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
        "embedding_model": row[5],
    }
