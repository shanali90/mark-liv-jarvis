import core.gemini as gemini
import actions.web_search as ws


def test_model_404_removed_from_session_ladder(monkeypatch):
    gemini._dead_models.clear()
    gemini._cooldown.clear()

    monkeypatch.setattr(gemini, "api_key", lambda: "fake_key")

    calls = []

    class FakeClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                model = kwargs.get("model")
                calls.append(model)
                if model == "gemini-bad-model":
                    raise RuntimeError("404 NOT_FOUND. Model is no longer available to new users.")
                return type("Resp", (), {"text": "ok"})()

    monkeypatch.setattr(gemini, "client", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(gemini, "get_available_models", lambda refresh=False: ["gemini-bad-model", "gemini-good-model"])
    monkeypatch.setattr(gemini, "_LADDERS", {
        gemini.FAST: ("gemini-bad-model", "gemini-good-model"),
        gemini.SMART: ("gemini-good-model",),
    })

    # First call: hits gemini-bad-model, fails with 404, removes it, falls back to gemini-good-model
    resp = gemini.call("hello", tier=gemini.FAST)
    assert resp.text == "ok"
    assert "gemini-bad-model" in gemini._dead_models
    assert calls == ["gemini-bad-model", "gemini-good-model"]

    # Second call: gemini-bad-model is in _dead_models, skipped completely!
    calls.clear()
    resp2 = gemini.call("hello again", tier=gemini.FAST)
    assert resp2.text == "ok"
    assert calls == ["gemini-good-model"]


def test_web_search_fallback_short_honest_line(monkeypatch):
    monkeypatch.setattr(ws, "_gemini_search", lambda q: (_ for _ in ()).throw(RuntimeError("All Gemini models 404")))
    monkeypatch.setattr(ws, "_ddg_search", lambda q, **kw: (_ for _ in ()).throw(RuntimeError("DDG connection timeout")))

    res = ws._search("world news")
    assert "404" not in res
    assert "I couldn't reach the search service" in res
