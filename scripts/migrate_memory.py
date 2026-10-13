import json
import sys
from pathlib import Path
import logging

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import init_db, upsert_memory, add_session, get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    base_dir = Path(__file__).resolve().parent.parent
    json_path = base_dir / "memory" / "long_term.json"
    
    if not json_path.exists():
        logger.info(f"No long_term.json found at {json_path}. Skipping migration.")
        return
        
    logger.info("Initializing SQLite database...")
    init_db()
    
    logger.info(f"Reading {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Migrate key-value categories
    categories = ["identity", "preferences", "projects", "relationships", "wishes", "notes"]
    for cat in categories:
        if cat in data:
            entries = data[cat]
            for key, val_obj in entries.items():
                value = val_obj.get("value", str(val_obj))
                logger.info(f"Migrating [{cat}] {key}")
                upsert_memory(cat, key, str(value))
                
    # Migrate sessions
    if "sessions" in data:
        for s in data["sessions"]:
            add_session(
                date=s.get("date", ""),
                summary=s.get("summary", ""),
                language=s.get("language", "")
            )
            
    # Migrate monitors
    if "monitors" in data:
        conn = get_connection()
        c = conn.cursor()
        for topic, m in data["monitors"].items():
            c.execute("""
                INSERT OR IGNORE INTO monitors (topic, added, last_check, last_hash)
                VALUES (?, ?, ?, ?)
            """, (topic, m.get("added"), m.get("last_check"), m.get("last_hash")))
        conn.commit()
        conn.close()
            
    # Rename to .bak
    bak_path = json_path.with_suffix(".json.bak")
    json_path.rename(bak_path)
    logger.info(f"Migration complete. Renamed {json_path.name} to {bak_path.name}.")

if __name__ == "__main__":
    migrate()
