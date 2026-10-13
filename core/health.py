from core.audit import verify_chain
from core.config_schema import validate_config
from core.vault import get_secret


def health_check() -> dict:
    """Returns a health report of the Jarvis system."""
    health = {
        "status": "healthy",
        "config_valid": False,
        "audit_chain_valid": False,
        "vault_accessible": False
    }
    
    try:
        validate_config()
        health["config_valid"] = True
    except Exception as e:
        health["status"] = "degraded"
        health["config_error"] = str(e)
        
    try:
        health["audit_chain_valid"] = verify_chain()
        if not health["audit_chain_valid"]:
            health["status"] = "degraded"
    except Exception:
        health["status"] = "degraded"
        
    try:
        # Just check if we can query the vault without crashing
        get_secret("dummy_test")
        health["vault_accessible"] = True
    except Exception:
        health["status"] = "degraded"
        
    return health
