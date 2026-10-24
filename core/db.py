import sqlite3
import numpy as np
from pathlib import Path
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "memory" / "jarvis.db"

def get_connection():
    # Make sure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Memory entries (kv with embeddings)
    c.execute("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            embedding BLOB,
            updated_at TEXT NOT NULL,
            UNIQUE(category, key)
        )
    """)
    # FTS table for full-text search
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            category, key, value, content='memory_entries', content_rowid='id'
        )
    """)
    # Triggers to keep FTS in sync
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
            INSERT INTO memory_fts(rowid, category, key, value) VALUES (new.id, new.category, new.key, new.value);
        END;
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_entries BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, category, key, value) VALUES('delete', old.id, old.category, old.key, old.value);
        END;
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_entries BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, category, key, value) VALUES('delete', old.id, old.category, old.key, old.value);
            INSERT INTO memory_fts(rowid, category, key, value) VALUES (new.id, new.category, new.key, new.value);
        END;
    """)
    
    # Sessions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            summary TEXT NOT NULL,
            language TEXT
        )
    """)
    
    # Monitors table
    c.execute("""
        CREATE TABLE IF NOT EXISTS monitors (
            topic TEXT PRIMARY KEY,
            added TEXT,
            last_check TEXT,
            last_hash TEXT
        )
    """)
    conn.commit()
    conn.close()

def generate_embedding(text: str) -> list[float] | None:
    from core.models import get_embedding_model
    try:
        # Note: If user is out of credits or has no keys, we silently return None
        # to avoid crashing the db save. 
        model = get_embedding_model()
        return model.embed(text)
    except Exception as e:
        logger.warning(f"Failed to generate embedding: {e}")
        return None

def upsert_memory(category: str, key: str, value: str):
    conn = get_connection()
    c = conn.cursor()
    
    emb_list = generate_embedding(f"{category} {key} {value}")
    emb_bytes = np.array(emb_list, dtype=np.float32).tobytes() if emb_list else None
    updated_at = datetime.utcnow().isoformat()
    
    c.execute("""
        INSERT INTO memory_entries (category, key, value, embedding, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(category, key) DO UPDATE SET
            value=excluded.value,
            embedding=excluded.embedding,
            updated_at=excluded.updated_at
    """, (category, key, value, emb_bytes, updated_at))
    conn.commit()
    conn.close()
    
def delete_memory(category: str, key: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM memory_entries WHERE category=? AND key=?", (category, key))
    conn.commit()
    conn.close()

def get_all_memory() -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT category, key, value, updated_at FROM memory_entries")
    rows = c.fetchall()
    conn.close()
    
    mem = {}
    for r in rows:
        cat = r["category"]
        if cat not in mem:
            mem[cat] = {}
        mem[cat][r["key"]] = {"value": r["value"], "updated": r["updated_at"]}
    return mem

def _cosine(a, b) -> float | None:
    """Compute cosine similarity between two vectors.

    Returns None when vector sizes differ or when either norm is zero.
    """
    if a is None or b is None:
        return None
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)
    if a_arr.shape != b_arr.shape:
        return None
    norm_a = float(np.linalg.norm(a_arr))
    norm_b = float(np.linalg.norm(b_arr))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return None
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def search_memory(query: str, limit: int = 8) -> list[dict]:
    # Hybrid search: FTS5 + Cosine similarity (if available)
    conn = get_connection()
    c = conn.cursor()
    
    results = {}
    
    # 1. FTS5 exact text matches
    try:
        # FTS5 match query
        # Remove special chars that break fts match syntax
        safe_query = ''.join(e for e in query if e.isalnum() or e.isspace())
        if safe_query.strip():
            fts_q = " OR ".join([f"{w}*" for w in safe_query.split()])
            c.execute("""
                SELECT rowid, category, key, value 
                FROM memory_fts 
                WHERE memory_fts MATCH ? 
                LIMIT 20
            """, (fts_q,))
            for r in c.fetchall():
                results[r["rowid"]] = {"score": 1.0, "row": r} # Base score
    except Exception as e:
        logger.warning(f"FTS5 search failed: {e}")
        
    # 2. Vector search
    query_emb = generate_embedding(query)
    if query_emb:
        q_vec = np.array(query_emb, dtype=np.float32)
        # Fetch all embeddings (fine for personal scale < 10k items)
        c.execute("SELECT id, category, key, value, embedding FROM memory_entries WHERE embedding IS NOT NULL")
        for r in c.fetchall():
            emb_bytes = r["embedding"]
            db_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            sim = _cosine(q_vec, db_vec)
            if sim is not None and sim > 0.5: # threshold
                if r["id"] in results:
                    results[r["id"]]["score"] += float(sim)
                else:
                    results[r["id"]] = {"score": float(sim), "row": r}
                        
    conn.close()
    
    # Sort by score and take limit
    sorted_res = sorted(results.values(), key=lambda x: x["score"], reverse=True)
    return [{"category": x["row"]["category"], "key": x["row"]["key"], "value": x["row"]["value"]} for x in sorted_res[:limit]]

def add_session(date: str, summary: str, language: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (date, summary, language) VALUES (?, ?, ?)", (date, summary, language))
    conn.commit()
    conn.close()

def get_recent_sessions(limit: int = 5) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT date, summary, language FROM sessions ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"date": r["date"], "summary": r["summary"], "language": r["language"]} for r in rows]
