import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
AUDIT_LOG_FILE = LOG_DIR / "audit.jsonl"

logger = logging.getLogger(__name__)
_AUDIT_LOCK = threading.Lock()

def _get_last_hash() -> str:
    """Read the last hash from the audit log to maintain the hash chain."""
    if not AUDIT_LOG_FILE.exists():
        return "0000000000000000000000000000000000000000000000000000000000000000"

    last_line = ""
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line

        if last_line:
            data = json.loads(last_line)
            return data.get("hash", "")
    except Exception as e:
        logger.error(f"Failed to read last audit log hash: {e}")
    return "0000000000000000000000000000000000000000000000000000000000000000"

def log_action(actor: str, action: str, tool_name: str, inputs: dict[str, Any], result: str = "PENDING"):
    """Append a new action to the audit log hash chain."""
    with _AUDIT_LOCK:
        LOG_DIR.mkdir(exist_ok=True)
        last_hash = _get_last_hash()

        redacted_inputs = {}
        for k, v in inputs.items():
            if any(sec in k.lower() for sec in ["key", "secret", "token", "password", "bearer"]):
                redacted_inputs[k] = "[REDACTED]"
            elif isinstance(v, (dict, list, str, int, float, bool, type(None))):
                redacted_inputs[k] = v
            else:
                redacted_inputs[k] = f"<{type(v).__name__}>"

        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "actor": actor,
            "action": action,
            "tool_name": tool_name,
            "inputs": redacted_inputs,
            "result": result,
            "prev_hash": last_hash
        }

        record_str = json.dumps(record, sort_keys=True)
        current_hash = hashlib.sha256(record_str.encode("utf-8")).hexdigest()
        record["hash"] = current_hash

        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

def verify_chain() -> bool:
    """Verify the integrity of the audit log hash chain."""
    with _AUDIT_LOCK:
        if not AUDIT_LOG_FILE.exists():
            return True

        prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    recorded_hash = data.pop("hash")
                    data_prev_hash = data.get("prev_hash")

                    if data_prev_hash != prev_hash:
                        logger.error(f"Audit log tampered at line {line_num}: prev_hash mismatch.")
                        return False

                    record_str = json.dumps(data, sort_keys=True)
                    calc_hash = hashlib.sha256(record_str.encode("utf-8")).hexdigest()

                    if calc_hash != recorded_hash:
                        logger.error(f"Audit log tampered at line {line_num}: hash mismatch.")
                        return False

                    prev_hash = calc_hash
                except Exception as e:
                    logger.error(f"Audit log corrupted at line {line_num}: {e}")
                    return False

        return True
