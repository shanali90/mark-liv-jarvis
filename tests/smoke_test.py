import os
import sys

# Add root to pythonpath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_jarvis_smoke():
    import main
    assert hasattr(main, "BASE_DIR")
    from core.offline_engine import is_online
    # Just run it to ensure no syntax/import errors
    online = is_online(timeout=1.0)
    print(f"Smoke test passed! is_online={online}")

if __name__ == "__main__":
    test_jarvis_smoke()
