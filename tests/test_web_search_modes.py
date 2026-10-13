from actions.web_search import web_search
import actions.web_search as ws

def test_web_search_all_modes(monkeypatch):
    # Mocking internal logic with realistic small data instead of long repeating strings.
    # The previous test used "Mock Gemini " * 10 because `_news` had a hardcoded `len(text) > 60` check
    # that caused it to discard short mocked responses and fall back incorrectly.
    # Here, we mock the final inner methods directly to bypass the length check entirely,
    # ensuring clean and realistic test data.

    monkeypatch.setattr(ws, '_search', lambda q: "Python is a programming language.")
    monkeypatch.setattr(ws, '_news', lambda q: "Latest news: Python 3.14 released today.")
    monkeypatch.setattr(ws, '_research', lambda q: "Deep dive: Python was created by Guido van Rossum.")
    monkeypatch.setattr(ws, '_price', lambda q: "Python crash course book costs $20.")
    monkeypatch.setattr(ws, '_compare', lambda i, a: "Python vs Java: Python is dynamically typed.")

    # Test all success modes
    for mode in ["search", "news", "research", "price", "compare"]:
        args = {'query': 'Python'}
        if mode == "compare":
            args = {'query': '', 'items': ['Python', 'Java'], 'aspect': 'types', 'mode': 'compare'}
        else:
            args['mode'] = mode

        res = web_search(args)
        assert res.startswith("<untrusted>\n"), f"Missing <untrusted> wrap for mode {mode}"
        assert res.endswith("</untrusted>"), f"Missing </untrusted> wrap for mode {mode}"
        assert "Python" in res

    # Test that "Search failed" is NOT wrapped in untrusted tags
    monkeypatch.setattr(ws, '_search', lambda q: "Search failed: Rate limit exceeded.")
    res = web_search({'query': 'Python', 'mode': 'search'})
    assert res == "Search failed: Rate limit exceeded."
    assert "<untrusted>" not in res

    # Test exception fallback inside web_search
    def fail_search(q):
        raise ValueError("Network detached.")
    monkeypatch.setattr(ws, '_search', fail_search)
    res = web_search({'query': 'Python', 'mode': 'search'})
    assert "Search failed: Network detached." in res
    assert "<untrusted>" not in res
