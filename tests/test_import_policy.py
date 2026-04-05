from __future__ import annotations

import unittest
from pathlib import Path


class ImportPolicyTests(unittest.TestCase):
    def test_direct_pyqt6_imports_are_limited_to_explicit_exceptions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        allowed_files = {
            repo_root / "tests" / "fake_aqt.py",
        }
        allowed_prefixes = (
            "from PyQt6.QtMultimedia import",
            "from PyQt6.QtMultimediaWidgets import",
        )

        offenders: list[str] = []
        for path in list((repo_root / "src").rglob("*.py")) + list((repo_root / "tests").rglob("*.py")):
            if path in allowed_files:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not stripped.startswith("from PyQt6"):
                    continue
                if stripped.startswith(allowed_prefixes):
                    continue
                offenders.append(f"{path.relative_to(repo_root)}:{lineno}: {stripped}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
