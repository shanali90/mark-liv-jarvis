import hashlib

import pytest

from core.safety.integrity import SafetyIntegrityError, verify_pinned_files


def test_modified_pinned_safety_file_fails_startup_verification(tmp_path):
    safety_file = tmp_path / "core" / "safety" / "trust.py"
    safety_file.parent.mkdir(parents=True)
    safety_file.write_text("modified safety policy", encoding="utf-8")
    pinned_hash = hashlib.sha256(b"original safety policy").hexdigest()

    with pytest.raises(SafetyIntegrityError, match="core/safety/trust.py: SHA-256 mismatch"):
        verify_pinned_files(
            tmp_path,
            {"core/safety/trust.py": pinned_hash},
        )
