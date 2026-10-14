import asyncio
import os
import sys

# Ensure imports work regardless of run directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_weather_report():
    from actions.weather_report import weather_action

    # Valid city
    res_valid = weather_action({"city": "Karachi"})
    assert "Current weather in Karachi" in res_valid or "couldn't fetch" in res_valid

    # Invalid city
    res_invalid = weather_action({"city": "NonExistentCity1234XYZ"})
    assert "Could not find coordinates" in res_invalid or "couldn't fetch" in res_invalid

def test_trust_levels(monkeypatch, tmp_path):
    from core.safety.trust import get_trust_level, promote_trust, LEVEL_ASK, LEVEL_DRAFT, LEVEL_SILENT
    from core.safety import trust

    monkeypatch.setattr(trust, "_TRUST_PATH", tmp_path / "trust_policy.json")

    # Check default policy
    assert get_trust_level("mail_send") == LEVEL_ASK
    assert get_trust_level("calendar_read") == LEVEL_SILENT

    # Check strict overrides
    assert get_trust_level("permanent_delete") == LEVEL_ASK
    promote_trust("permanent_delete", LEVEL_SILENT)
    assert get_trust_level("permanent_delete") == LEVEL_ASK # Should not promote

    # Promote a valid property
    promote_trust("mail_draft", LEVEL_DRAFT)
    assert get_trust_level("mail_draft") == LEVEL_DRAFT


def test_everyday_controls_do_not_ask():
    from core.safety.trust import get_trust_level, LEVEL_ASK, LEVEL_DO_TELL

    assert get_trust_level("browser_control", "go_to") == LEVEL_DO_TELL
    assert get_trust_level("browser_control", "smart_type") == LEVEL_DO_TELL
    assert get_trust_level("computer_control", "scroll") == LEVEL_DO_TELL
    assert get_trust_level("file_controller", "read") == LEVEL_DO_TELL
    assert get_trust_level("computer_settings", "volume_set") == LEVEL_ASK
    assert get_trust_level("computer_settings", "restart") == LEVEL_ASK
    assert get_trust_level("file_controller", "move") == LEVEL_ASK
    assert get_trust_level("send_message") == LEVEL_ASK
    assert get_trust_level("browser_control", "smart_click", args={"description": "Send"}) == LEVEL_ASK
    assert get_trust_level("computer_control", "screen_click", args={"description": "Send"}) == LEVEL_ASK

def test_detect_failure_logging():
    from selfheal.detect import safe_execute

    def failing_func():
        raise ValueError("Intentional simulated crash")

    def success_func():
        return "Success"

    # Execute failed function
    success, result, duration = safe_execute("test_fail", failing_func)
    assert not success
    assert "Action failed internally (ValueError): Intentional simulated crash" in result

    # Execute success function
    success, result, duration = safe_execute("test_success", success_func)
    assert success
    assert result == "Success"

def test_browser_loop_budget(monkeypatch):
    from actions.browser_control import browser_control
    import actions.browser_control as bc

    # go_to opens the REAL native browser. The test must never do that: it used
    # to open a tab on example.com in the owner's own Chrome on every run.
    opened = []
    monkeypatch.setattr(bc, "_open_native", lambda url, browser=None: opened.append(url) or "stub: not opened")
    monkeypatch.setattr(bc, "_log", lambda *a, **k: None)

    # Reset budget
    bc._BROWSER_BUDGET["count"] = 0

    aborted = False
    for _ in range(12):
        res = browser_control({"action": "go_to", "url": "https://example.com"})
        if "Browser loop budget exceeded" in res:
            aborted = True
            break

    assert aborted, "Browser budget guard failed to trigger after 10 loops"
    assert len(opened) == 10, "budget must stop the 11th call before it opens anything"

def test_browser_untrusted_wrapper():
    import actions.browser_control as bc

    class FakePage:
        async def inner_text(self, tag): return "Some webpage text"
    class FakeBrowser:
        async def _get_page(self): return FakePage()

    fb = FakeBrowser()

    async def run_test():
        return await bc._BrowserSession.get_text(fb)

    res = asyncio.run(run_test())

    assert "<untrusted>" in res
    assert "</untrusted>" in res
    assert "Some webpage text" in res

def test_other_untrusted_wrappers():
    import tempfile
    from actions.file_controller import file_controller

    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        f.write('Secret untrusted content')
        tmp_name = f.name

    try:
        res = file_controller({'action': 'read', 'path': tmp_name})
        assert '<untrusted>' in res
        assert 'Secret untrusted content' in res
    finally:
        os.remove(tmp_name)


def test_web_search_untrusted(monkeypatch):
    from actions.web_search import web_search
    import actions.web_search as ws
    monkeypatch.setattr(ws, '_ddg_news', lambda *a, **k: [{'title': 'Mock News', 'body': 'Mock body', 'url': 'http://mock'}])
    res = web_search({'query': 'Python', 'mode': 'news'})
    assert '<untrusted>' in res
    assert 'Mock News' in res
