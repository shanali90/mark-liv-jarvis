import logging
import time
from typing import Any
from core.models import get_model
from core.registry import registry

logger = logging.getLogger(__name__)

# Very basic heuristic for tokens if tiktoken is not installed
def estimate_tokens(text: str) -> int:
    return len(text) // 4

class CostGuard:
    def __init__(self, daily_token_cap: int = 1_000_000):
        self.daily_token_cap = daily_token_cap
        self.tokens_used_today = 0
        self.reset_time = time.time() + 86400
        
    def add_tokens(self, tokens: int):
        if time.time() > self.reset_time:
            self.tokens_used_today = 0
            self.reset_time = time.time() + 86400
            
        self.tokens_used_today += tokens
        if self.tokens_used_today > self.daily_token_cap:
            logger.error("COST GUARD EXCEEDED: Daily token limit reached!")
            raise PermissionError("Daily token cap exceeded. Halting to prevent cost.")

cost_guard = CostGuard()

class FastBrain:
    def __init__(self):
        self.cache = {} # Simple memory cache for identical commands
        self.rules = {
            "volume up": {"tool": "computer_settings", "params": {"action": "volume_up"}},
            "volume down": {"tool": "computer_settings", "params": {"action": "volume_down"}},
            "mute": {"tool": "computer_settings", "params": {"action": "mute"}},
            "sleep": {"tool": "computer_control", "params": {"action": "sleep"}},
            "lock": {"tool": "computer_control", "params": {"action": "lock"}}
        }
        
    def _tier1_rules(self, query: str) -> dict | None:
        """Tier 1: Hardcoded exact-match or simple regex rules (0ms latency)."""
        clean_query = query.lower().strip()
        if clean_query in self.rules:
            return self.rules[clean_query]
        if clean_query in self.cache:
            return self.cache[clean_query]
        return None

    def _tier2_intent(self, query: str, tools: list[dict]) -> dict | None:
        """Tier 2: Small fast intent model (gemini-2.5-flash) for straightforward tool mapping."""
        # Convert tools to schema
        model = get_model("gemini", "gemini-2.5-flash")
        
        system = "You are a fast intent router. Given the tools available, pick the single tool and arguments that satisfy the user query. If complex reasoning or multiple steps are needed, do not return a tool call."
        try:
            resp = model.generate_content(query, system_instruction=system, tools=tools)
            cost_guard.add_tokens(estimate_tokens(query) + 200) # heuristic
            
            # Extract tool call from Gemini response
            if hasattr(resp, 'candidates') and resp.candidates:
                part = resp.candidates[0].content.parts[0]
                if part.function_call:
                    name = part.function_call.name
                    args = dict(part.function_call.args)
                    return {"tool": name, "params": args}
        except Exception as e:
            logger.warning(f"Tier 2 intent failed: {e}")
        return None

    def _tier3_planner(self, query: str, tools: list[dict]) -> dict | None:
        """Tier 3: Large reasoning model (gemini-2.5-pro) for complex plans."""
        model = get_model("gemini", "gemini-2.5-pro")
        system = "You are an advanced planner. You have access to tools. Plan and execute the first logical tool step for the given query."
        try:
            resp = model.generate_content(query, system_instruction=system, tools=tools)
            cost_guard.add_tokens(estimate_tokens(query) + 500) # heuristic
            
            if hasattr(resp, 'candidates') and resp.candidates:
                part = resp.candidates[0].content.parts[0]
                if part.function_call:
                    name = part.function_call.name
                    args = dict(part.function_call.args)
                    return {"tool": name, "params": args}
        except Exception as e:
            logger.warning(f"Tier 3 planner failed: {e}")
        return None
        
    def _verify(self, result: Any, intent: dict) -> bool:
        """Verifier loop (no silent failures)."""
        if result is None or (isinstance(result, str) and "failed" in result.lower()):
            return False
        return True

    def process(self, query: str, available_tools: list[dict]) -> str:
        """Main entrypoint for Fast Brain routing."""
        # Tier 1
        intent = self._tier1_rules(query)
        
        # Tier 2
        if not intent:
            intent = self._tier2_intent(query, available_tools)
            
        # Tier 3
        if not intent:
            intent = self._tier3_planner(query, available_tools)
            
        if not intent:
            return "Could not determine an action for this query."
            
        # Cache successful dynamic intents
        self.cache[query.lower().strip()] = intent
        
        # Execute
        try:
            tool_name = intent["tool"]
            params = intent["params"]
            
            # Run through registry
            result = registry.execute(tool_name, params)
            
            # Verify
            if not self._verify(result, intent):
                logger.error(f"Execution verification failed for {tool_name}")
                return f"Execution of {tool_name} failed verification. Result: {result}"
                
            return f"Successfully executed {tool_name}. Result: {result}"
            
        except PermissionError as e:
            return f"Blocked by safety guard: {e}"
        except Exception as e:
            return f"Error executing action: {e}"

brain = FastBrain()
