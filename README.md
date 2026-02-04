# resume-matching

Phase 0:
Implemented health (/healthz) and readiness (/readyz) probes with live dependency checks for PostgreSQL and Redis.

Phase 1: Phase 1.0 deliverables (small, safe)
Create DB tables:
resumes (id, filename, status, created_at)
Add endpoint:
POST /resumes → accepts file upload, stores metadata in DB (for now, store file locally)
GET /resumes/{id} → returns stored metadata
