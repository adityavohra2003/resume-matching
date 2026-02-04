import os
from fastapi import FastAPI
import psycopg2
import redis

app = FastAPI(title="Resume Matching API", version="0.0.2")


def check_postgres() -> None:
    conn = psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "postgres"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.getenv("DATABASE_NAME", "resume_db"),
        user=os.getenv("DATABASE_USER", "app"),
        password=os.getenv("DATABASE_PASSWORD", "app"),
        connect_timeout=2,
    )
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
        # 503 is standard for "not ready"
        return {"status": "not_ready", "errors": errors}

    return {"status": "ready"}
