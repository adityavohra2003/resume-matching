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
    dim = int(os.getenv("EMBEDDING_DIM", "384"))

    conn = get_conn()
    cur = conn.cursor()

    # pgvector extension (requires pgvector/pgvector image)
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create tables (safe for fresh DB)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS resumes (
            id UUID PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT,
            storage_path TEXT NOT NULL,
            status TEXT NOT NULL,
            raw_text TEXT,
            clean_text TEXT,
            parsed_json JSONB,
            embedding vector({dim}),
            embedding_model TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        );
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS job_descriptions (
            id UUID PRIMARY KEY,
            title TEXT,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            clean_text TEXT,
            embedding vector({dim}),
            embedding_model TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Backward-compatible ALTERs (safe for existing DBs)
    cur.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS raw_text TEXT;")
    cur.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS clean_text TEXT;")
    cur.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS parsed_json JSONB;")
    cur.execute(f"ALTER TABLE resumes ADD COLUMN IF NOT EXISTS embedding vector({dim});")
    cur.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS embedding_model TEXT;")
    cur.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")

    cur.execute("ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS clean_text TEXT;")
    cur.execute(f"ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS embedding vector({dim});")
    cur.execute("ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS embedding_model TEXT;")

    conn.commit()
    cur.close()
    conn.close()
