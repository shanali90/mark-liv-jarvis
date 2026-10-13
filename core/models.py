import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

class ModelAdapter(ABC):
    @abstractmethod
    def generate_content(self, prompt: str, system_instruction: str = "", tools: list[dict] | None = None) -> Any:
        pass

class GeminiAdapter(ModelAdapter):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        
    def generate_content(self, prompt: str, system_instruction: str = "", tools: list[dict] | None = None) -> Any:
        from core.gemini import client as gemini_client
        from google.genai import types
        cl = gemini_client()
        
        config_kwargs = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            # We map generic tool dicts to Gemini's Tool type
            config_kwargs["tools"] = tools
            
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        return cl.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )

class OpenAIAdapter(ModelAdapter):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name
        
    def generate_content(self, prompt: str, system_instruction: str = "", tools: list[dict] | None = None) -> Any:
        from core.llm_client import _load_config
        import requests
        
        cfg = _load_config()
        url = cfg.get("llm_url", "http://localhost:11434").rstrip("/")
        api_key = cfg.get("openai_api_key", "")
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model_name,
            "messages": messages,
        }
        
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            
        endpoint = f"{url}/v1/chat/completions"
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

def get_model(provider: str, model_name: str) -> ModelAdapter:
    if provider == "gemini":
        return GeminiAdapter(model_name)
    elif provider == "openai":
        return OpenAIAdapter(model_name)
    else:
        raise ValueError(f"Unknown provider {provider}")

class EmbeddingAdapter(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

class GeminiEmbeddingAdapter(EmbeddingAdapter):
    def __init__(self, model_name: str = "text-embedding-004"):
        self.model_name = model_name
        
    def embed(self, text: str) -> list[float]:
        from core.gemini import client as gemini_client
        cl = gemini_client()
        result = cl.models.embed_content(
            model=self.model_name,
            contents=text
        )
        # return the list of floats
        return result.embeddings[0].values

class OpenAIEmbeddingAdapter(EmbeddingAdapter):
    def __init__(self, model_name: str = "text-embedding-3-small"):
        self.model_name = model_name
        
    def embed(self, text: str) -> list[float]:
        from core.llm_client import _load_config
        import requests
        
        cfg = _load_config()
        url = cfg.get("llm_url", "http://localhost:11434").rstrip("/")
        api_key = cfg.get("openai_api_key", "")
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "model": self.model_name,
            "input": text,
        }
        
        endpoint = f"{url}/v1/embeddings"
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

def get_embedding_model(provider: str = "gemini", model_name: str = "text-embedding-004") -> EmbeddingAdapter:
    if provider == "gemini":
        return GeminiEmbeddingAdapter(model_name)
    elif provider == "openai":
        return OpenAIEmbeddingAdapter(model_name)
    else:
        raise ValueError(f"Unknown provider {provider}")
