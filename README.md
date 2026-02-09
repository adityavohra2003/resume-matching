# Resume ↔ Job Description Matching System (ATS-style, Explainable)

Production-style resume screening platform that ingests resumes asynchronously, extracts and parses text, generates embeddings, stores everything in Postgres + pgvector, and returns **ranked + explainable** matches for a given job description.

## Features
- **FastAPI** backend (Swagger docs at `/docs`)
- **Docker Compose** local stack
- **Postgres + pgvector** for embedding storage + vector similarity search
- **Redis** available for async patterns (currently used for readiness check)
- **Async resume processing** using FastAPI `BackgroundTasks` (API never blocks)
- **Text extraction** from PDF/DOCX (OCR intentionally not implemented yet)
- **Explainable matching**:
  - semantic similarity (embeddings)
  - skills overlap (keyword-based)
  - experience alignment (simple heuristic)
- **Minimal Streamlit UI** to demo upload → JD → match

---

## Architecture (Local)

