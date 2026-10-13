import inspect
import logging
from collections.abc import Callable
from typing import Any

from core.audit import log_action
from core.permissions import SafetyLevel, approval_queue

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}
        
    def register(self, name: str, description: str, safety: SafetyLevel, func: Callable):
        """Register an MCP-compatible tool and wrap it to enforce safety if called directly."""
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Pass short_timeout if defined in kwargs (for testing), else pop it
            short_timeout = kwargs.pop("_short_timeout", None)
            
            log_action("system", "execute_tool", name, kwargs, result="PENDING")
            
            if safety == SafetyLevel.RED:
                details = f"Tool: {name}\nArgs: {kwargs}"
                approved = approval_queue.request_approval(name, details, short_timeout=short_timeout)
                if not approved:
                    log_action("system", "execute_tool", name, kwargs, result="DENIED")
                    raise PermissionError(f"Execution of {name} was denied or timed out.")
            
            try:
                result = func(*args, **kwargs)
                log_action("system", "execute_tool", name, kwargs, result="SUCCESS")
                return result
            except Exception as e:
                log_action("system", "execute_tool", name, kwargs, result=f"FAILED: {e}")
                raise

        self._tools[name] = {
            "name": name,
            "description": description,
            "safety": safety,
            "func": wrapper,
            "signature": inspect.signature(func)
        }
        logger.info(f"Registered tool: {name} [{safety.name}]")

    def execute(self, tool_name: str, kwargs: dict[str, Any], actor: str = "system") -> Any:
        """Execute a tool."""
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")
            
        tool = self._tools[tool_name]
        return tool["func"](**kwargs)

registry = ToolRegistry()
