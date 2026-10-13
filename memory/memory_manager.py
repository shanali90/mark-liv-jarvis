import logging
from datetime import datetime
from core.db import (
    get_all_memory,
    upsert_memory,
    delete_memory,
    search_memory as db_search_memory,
    add_session,
    get_recent_sessions
)

logger = logging.getLogger(__name__)

MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
PROMPT_MAX_PER_CATEGORY = 6

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
        "sessions":      [],
        "monitors":      {}
    }

def set_trim_notifier(fn) -> None:
    # Legacy function; SQLite memory has no size-based auto-trim mechanism.
    pass

def load_memory() -> dict:
    """Load the full nested dict structure for legacy compat."""
    try:
        mem = get_all_memory()
        
        # Ensure all core categories exist
        base = _empty_memory()
        for cat in base.keys():
            if cat not in ["sessions", "monitors"]:
                if cat in mem:
                    base[cat] = mem[cat]
                    
        # Load sessions and monitors (basic translation)
        sessions = get_recent_sessions(limit=15)
        base["sessions"] = sessions[::-1] # return chronological if needed
        return base
    except Exception as e:
        logger.error(f"Error loading memory from SQLite: {e}")
        return _empty_memory()

def save_memory(memory: dict) -> None:
    """Legacy: Upsert the entire dictionary into DB."""
    categories = ["identity", "preferences", "projects", "relationships", "wishes", "notes"]
    for cat in categories:
        if cat in memory:
            for key, val_obj in memory[cat].items():
                value = val_obj.get("value", str(val_obj))
                upsert_memory(cat, key, value)
                
    if "sessions" in memory:
        # Sessions are usually additive, avoid mass overwrite unless needed.
        # Legacy save_memory usually gets called after appending one session.
        pass

def update_memory(memory_update: dict) -> dict:
    """Legacy: Recursively update specific keys."""
    categories = ["identity", "preferences", "projects", "relationships", "wishes", "notes"]
    for cat in categories:
        if cat in memory_update:
            for key, val_obj in memory_update[cat].items():
                value = val_obj.get("value", str(val_obj)) if isinstance(val_obj, dict) else str(val_obj)
                upsert_memory(cat, key, value)
    
    return load_memory()

def _entry_value(entry) -> str:
    if isinstance(entry, dict) and "value" in entry:
        return str(entry["value"])
    return str(entry)

def _pretty(key: str) -> str:
    return key.replace("_", " ").title()

def format_memory_for_prompt(memory: dict | None) -> str:
    """Format core memory block for the system prompt."""
    if not memory:
        memory = load_memory()
    out = []
    
    # Very basic legacy output
    for cat in ["identity", "preferences"]:
        if memory.get(cat):
            out.append(f"[{cat.upper()}]")
            for k, v in list(memory[cat].items())[:PROMPT_MAX_PER_CATEGORY]:
                out.append(f"- {_pretty(k)}: {_entry_value(v)}")
    
    # Add brief recent sessions
    sessions = memory.get("sessions", [])
    if sessions:
        out.append("\n[RECENT SESSIONS]")
        for s in sessions[-3:]:
            date = s.get("date", "")
            summ = s.get("summary", "")
            if len(summ) > 100: summ = summ[:97] + "..."
            out.append(f"- {date}: {summ}")
            
    return "\n".join(out)

def search_memory(query: str, limit: int = 8) -> str:
    """Hybrid Search using FTS5 + Embeddings from core.db"""
    results = db_search_memory(query, limit)
    if not results:
        return "No relevant memories found."
        
    out = []
    for r in results:
        cat = r["category"]
        key = r["key"]
        val = r["value"]
        out.append(f"[{cat}] {_pretty(key)}: {val}")
    return "\n".join(out)

def all_entries_for_ui() -> list[dict]:
    memory = load_memory()
    out = []
    for cat in ["identity", "preferences", "projects", "relationships", "wishes", "notes"]:
        for key, obj in memory.get(cat, {}).items():
            val = _entry_value(obj)
            out.append({"category": cat, "key": key, "value": val})
    return out

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    upsert_memory(category, key, value)
    return f"Remembered: {category}/{key} = {value}"

def forget(key: str, category: str = "notes") -> str:
    delete_memory(category, key)
    return f"Forgot {category}/{key}"

def save_session_summary(summary: str, language: str = "") -> None:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    add_session(now, summary, language)

def pop_last_session() -> dict | None:
    # Legacy: hard to do safely in SQL without tracking. Just return None
    # since it was rarely used except for immediate rollbacks in errors.
    return None