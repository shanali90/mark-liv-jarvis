import hashlib
from pathlib import Path


class SafetyIntegrityError(RuntimeError):
    pass


SAFETY_FILE_HASHES = {
    "main.py": "3aa7b326bf6e1c2e86b86d2616b68d76f40130d5e3457592d29c7a3da8f099b0",
    "core/confirm.py": "278bb754b6e073d598829492ece81743eafbcb4a5f41721aa703b0c6fe746f1d",
    "core/safety/trust.py": "61ec62aa10ae4eae1072e504990b15e4aa3470759f4652b9e6f99fb529ef0873",
    "core/tools/mixin.py": "d0c9475545bed57f380fd6f78d9c2b9922e3207d8ee279a1a5705b6e0b9c9594",
    "scripts/hooks/pre-commit": "40953d61ed5c57d3a49eae0dc8b9258a1995e87f5a2e0bb3bd82764e06eb01db",
}


def verify_pinned_files(root: Path, pins: dict[str, str] | None = None) -> None:
    """Fail closed when a pinned safety file is missing or has changed."""
    expected_hashes = SAFETY_FILE_HASHES if pins is None else pins
    root = Path(root).resolve()
    failures = []
    for relative_path, expected in expected_hashes.items():
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            failures.append(f"{relative_path}: resolved outside project root")
            continue
        try:
            contents = target.read_bytes().replace(b"\r\n", b"\n")
            actual = hashlib.sha256(contents).hexdigest()
        except OSError as exc:
            failures.append(f"{relative_path}: cannot read ({exc})")
            continue
        if actual != expected:
            failures.append(f"{relative_path}: SHA-256 mismatch")
    if failures:
        raise SafetyIntegrityError(
            "Safety integrity verification failed:\n" + "\n".join(failures)
        )
