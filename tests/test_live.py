import pytest
from core.gemini import client as gemini_client
try:
    from core.llm_client import query as llm_query
except ImportError:
    llm_query = None

@pytest.mark.live
def test_live_gemini():
    """Makes a tiny real call to Gemini API."""
    cl = gemini_client()
    # Simple call to generate content
    response = cl.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say exactly 'ok'"
    )
    assert "ok" in response.text.lower()

@pytest.mark.live
def test_live_offline_provider():
    """Makes a tiny real call to the fallback LLM provider."""
    # This uses whatever is configured (Ollama or OpenAI-compatible)
    generator = llm_query("Say exactly 'ok'")
    full_response = ""
    for chunk in generator:
        full_response += chunk
    assert "ok" in full_response.lower()
