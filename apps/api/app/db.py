import os
import psycopg2

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "postgres"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.getenv("DATABASE_NAME", "resume_db"),
        user=os.getenv("DATABASE_USER", "app"),
        password=os.getenv("DATABASE_PASSWORD", "app"),
        connect_timeout=2,
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id UUID PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT,
            storage_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
