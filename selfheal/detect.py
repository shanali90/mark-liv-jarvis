import time
import traceback
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("memory") / "incidents.db"

def _init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT,
                signature TEXT,
                exception_type TEXT,
                traceback TEXT,
                inputs TEXT,
                duration REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_stats (
                tool_name TEXT PRIMARY KEY,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_duration REAL DEFAULT 0
            )
        """)

_init_db()

def _redact_inputs(kwargs: dict) -> str:
    """Redacts sensitive information before saving."""
    if not kwargs:
        return "{}"
    safe_kwargs = {}
    redact_keys = {"password", "token", "key", "secret", "bearer"}
    for k, v in kwargs.items():
        if any(rk in k.lower() for rk in redact_keys):
            safe_kwargs[k] = "***REDACTED***"
        elif k in ("player", "response", "session_memory"):
            safe_kwargs[k] = f"<{type(v).__name__}>"
        else:
            safe_kwargs[k] = repr(v)
    return json.dumps(safe_kwargs)

def _record_incident(tool_name: str, exc: Exception, kwargs: dict, duration: float):
    tb = traceback.format_exc()
    # Simple signature hash
    signature = str(hash(f"{type(exc).__name__}:{tb.splitlines()[-2] if len(tb.splitlines()) > 1 else ''}"))
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO incidents (tool_name, signature, exception_type, traceback, inputs, duration) VALUES (?, ?, ?, ?, ?, ?)",
            (tool_name, signature, type(exc).__name__, tb, _redact_inputs(kwargs), duration)
        )
        conn.execute(
            "INSERT INTO tool_stats (tool_name, fail_count) VALUES (?, 1) ON CONFLICT(tool_name) DO UPDATE SET fail_count = fail_count + 1",
            (tool_name,)
        )

def _record_success(tool_name: str, duration: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO tool_stats (tool_name, success_count, last_duration) VALUES (?, 1, ?) ON CONFLICT(tool_name) DO UPDATE SET success_count = success_count + 1, last_duration = ?",
            (tool_name, duration, duration)
        )

def safe_execute(tool_name: str, func, *args, **kwargs):
    """
    Standard executor that wraps every tool call to capture failures.
    Returns (success: bool, result: any, duration: float).
    """
    start = time.time()
    try:
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        # Simple heuristic result validation
        if result is None:
            raise ValueError(f"Tool {tool_name} returned None, which indicates failure or incomplete action.")
        if isinstance(result, str) and ("error" in result.lower() or "failed" in result.lower()):
            if "not found" not in result.lower() and "untrusted" not in result.lower():
                # Allow 'not found' or 'untrusted' responses as valid results, others as soft fails
                raise RuntimeError(f"Tool {tool_name} soft-failed: {result}")
            
        _record_success(tool_name, duration)
        return True, result, duration
        
    except Exception as e:
        duration = time.time() - start
        _record_incident(tool_name, e, kwargs, duration)
        # Log to stdout for dev server
        print(f"[SelfHeal] Caught failure in {tool_name}: {e}")
        # Send error context back to model so it can attempt a different path
        return False, f"Action failed internally ({type(e).__name__}): {str(e)}", duration
