import re
from typing import Any, Dict, List, Tuple
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import get_conn

router = APIRouter(tags=["matching"])


class MatchRequest(BaseModel):
    jd_id: UUID
    top_k: int = Field(default=10, ge=1, le=100)


# ---- Minimal, explainable JD skill extractor (NOT changing your resume parser) ----
_SKILL_TERMS = [
    # ---------- Programming ----------
    "python", "java", "c++", "javascript", "typescript", "go",
    "bash", "shell", "linux",

    # ---------- Data Science Core ----------
    "data science", "data analysis", "data analytics",
    "pandas", "numpy", "scipy",
    "matplotlib", "seaborn", "plotly",
    "jupyter", "notebook",

    # ---------- Machine Learning ----------
    "machine learning", "ml",
    "scikit-learn", "sklearn",
    "supervised learning", "unsupervised learning",
    "classification", "regression", "clustering",
    "feature engineering", "model evaluation",

    # ---------- Deep Learning ----------
    "deep learning", "neural networks",
    "tensorflow", "tensor flow",
    "keras",
    "pytorch", "torch",
    "cnn", "rnn", "lstm", "transformer",

    # ---------- NLP ----------
    "nlp", "natural language processing",
    "tokenization", "lemmatization",
    "word embeddings", "embeddings",
    "sentence transformers", "sentence-transformers",
    "spacy", "nltk",
    "bert", "gpt", "llm",

    # ---------- Computer Vision ----------
    "computer vision",
    "opencv",
    "image processing",
    "object detection", "image classification",
    "yolo", "resnet",

    # ---------- Databases ----------
    "sql", "postgres", "postgresql",
    "mysql", "sqlite",
    "nosql", "mongodb",
    "pgvector",

    # ---------- Big Data ----------
    "big data",
    "spark", "pyspark",
    "hadoop",
    "kafka",

    # ---------- Backend / APIs ----------
    "fastapi", "flask", "django",
    "rest api", "restful api",
    "grpc",

    # ---------- MLOps / Deployment ----------
    "mlops",
    "docker", "docker compose",
    "kubernetes", "k8s",
    "ci/cd",
    "github actions", "gitlab ci",
    "mlflow",
    "model deployment",
    "monitoring",

    # ---------- Cloud ----------
    "aws", "amazon web services",
    "s3", "ec2", "lambda",
    "gcp", "google cloud",
    "azure",

    # ---------- Software Engineering ----------
    "software engineering",
    "system design",
    "data structures",
    "algorithms",
    "object oriented programming",
    "oop",
    "version control",
    "git",

    # ---------- Research / Math ----------
    "statistics", "probability",
    "linear algebra",
    "optimization",
    "hypothesis testing",
]


def _normalize_skill(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def extract_jd_skills(jd_text: str) -> List[str]:
    text = (jd_text or "").lower()
    found = []
    for term in _SKILL_TERMS:
        if term in text:
            found.append(_normalize_skill(term))
    # de-duplicate, stable order
    seen = set()
    out = []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def extract_resume_skills(parsed_json: Any, resume_clean_text: str) -> List[str]:
    """
    1) Prefer parser output: parsed_json['skills']
    2) If empty/missing, fallback to keyword detection from resume_clean_text.
    """
    skills_from_parser: List[str] = []

    if isinstance(parsed_json, dict):
        skills_val = parsed_json.get("skills") or parsed_json.get("Skills")
        if isinstance(skills_val, list):
            skills_from_parser = [str(x).strip() for x in skills_val if str(x).strip()]
        elif isinstance(skills_val, str):
            parts = re.split(r"[,\n;]+", skills_val)
            skills_from_parser = [p.strip() for p in parts if p.strip()]

    # Normalize + dedup
    def norm_list(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for s in items:
            ns = _normalize_skill(s)
            if ns and ns not in seen:
                seen.add(ns)
                out.append(ns)
        return out

    skills_from_parser = norm_list(skills_from_parser)

    # Fallback: keyword detect from resume clean text if parser didn't populate skills
    if skills_from_parser:
        return skills_from_parser

    text = (resume_clean_text or "").lower()
    found = []
    for term in _SKILL_TERMS:
        if term in text:
            found.append(_normalize_skill(term))
    return norm_list(found)


def compute_skill_overlap(resume_skills: List[str], jd_skills: List[str]) -> Tuple[float, List[str], List[str]]:
    """
    Returns overlap_score in [0,1], matched skills, missing skills.
    overlap_score = matched / len(jd_skills) (if jd_skills exists else 0)
    """
    rs = set(resume_skills)
    matched = [s for s in jd_skills if s in rs]
    missing = [s for s in jd_skills if s not in rs]
    score = (len(matched) / len(jd_skills)) if jd_skills else 0.0
    return score, matched, missing


def experience_alignment(clean_text: str, jd_skills: List[str]) -> Tuple[float, List[str]]:
    """
    Very light heuristic: count how many JD skill terms appear in resume clean_text.
    Score = hits / max(1, len(jd_skills))
    """
    text = (clean_text or "").lower()
    hits = [s for s in jd_skills if s and s in text]
    score = (len(hits) / max(1, len(jd_skills))) if jd_skills else 0.0
    return score, hits


@router.post("/match")
def match(req: MatchRequest):
    conn = get_conn()
    cur = conn.cursor()

    # 1) Load JD embedding + text
    cur.execute(
        """
        SELECT clean_text, embedding, embedding_model
        FROM job_descriptions
        WHERE id = %s
        """,
        (str(req.jd_id),),
    )
    jd_row = cur.fetchone()
    if not jd_row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Job description not found")

    jd_clean_text, jd_embedding, jd_embedding_model = jd_row
    if jd_embedding is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Job description embedding is missing")

    # 2) Vector search in Postgres (pgvector)
    # cosine distance: (resume.embedding <=> jd_embedding)
    # similarity = 1 - distance
    cur.execute(
        """
        SELECT
            id,
            parsed_json,
            clean_text,
            embedding_model,
            (1 - (embedding <=> %s)) AS semantic_similarity
        FROM resumes
        WHERE status = 'PROCESSED'
          AND embedding IS NOT NULL
        ORDER BY (embedding <=> %s) ASC
        LIMIT %s
        """,
        (jd_embedding, jd_embedding, req.top_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    jd_skills = extract_jd_skills(jd_clean_text)

    results = []
    for (resume_id, parsed_json, resume_clean_text, resume_embedding_model, semantic_sim) in rows:
        resume_skills = extract_resume_skills(parsed_json, resume_clean_text)


        skill_score, matched, missing = compute_skill_overlap(resume_skills, jd_skills)
        exp_score, keyword_hits = experience_alignment(resume_clean_text, jd_skills)

        # Weighted, explainable score (bounded-ish)
        final = 0.60 * float(semantic_sim or 0.0) + 0.25 * float(skill_score) + 0.15 * float(exp_score)

        results.append(
            {
                "resume_id": str(resume_id),
                "final_score": round(final, 4),
                "semantic_similarity": round(float(semantic_sim or 0.0), 4),
                "skills_overlap": round(float(skill_score), 4),
                "experience_alignment": round(float(exp_score), 4),
                "skills_matched": matched,
                "skills_missing": missing,
                "keyword_hits_in_resume_text": keyword_hits,
                "models": {
                    "jd_embedding_model": jd_embedding_model,
                    "resume_embedding_model": resume_embedding_model,
                },
            }
        )

    # Sort by final_score descending (vector query returns semantic rank only)
    results.sort(key=lambda x: x["final_score"], reverse=True)

    return {
        "jd_id": str(req.jd_id),
        "top_k": req.top_k,
        "jd_skills_detected": jd_skills,
        "results": results,
    }
