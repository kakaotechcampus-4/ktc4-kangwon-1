"""고정 후보의 분모·원문 해시·결과 보존 경계를 확인합니다."""

import tempfile
import unittest
from pathlib import Path

from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.freeze90 import digest, run, validate_cases, verify_files


class Freeze90Tests(unittest.TestCase):
    def test_primary_and_supported_denominators_cannot_be_filtered(self):
        supported = next(c for c in INDUSTRIES if c not in INDUSTRIES_WITHOUT_SEOUL)
        unsupported = next(iter(INDUSTRIES_WITHOUT_SEOUL))
        cases = [
            {"id": str(i), "target": supported if i < 184 else unsupported} for i in range(212)
        ]
        self.assertEqual(len(validate_cases(cases)), 212)
        with self.assertRaises(ValueError):
            validate_cases(cases[:-1])
        cases[-1]["target"] = supported
        with self.assertRaises(ValueError):
            validate_cases(cases)

    def test_missing_changed_and_outside_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.json"
            source.write_bytes(b"{}")
            expected = {"input.json": digest(source)}
            verify_files(root, expected)
            source.write_bytes(b"[]")
            with self.assertRaises(ValueError):
                verify_files(root, expected)
            with self.assertRaisesRegex(ValueError, "자동 다운로드"):
                verify_files(root, {"missing.json": "0" * 64})
            with self.assertRaisesRegex(ValueError, "벗어납니다"):
                verify_files(root, {"../outside.json": "0" * 64})

    def test_git_newlines_only_are_normalized_for_source_code(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "scorer.py"
            source.write_bytes(b"value = 1\n")
            frozen = digest(source, text=True)
            raw = digest(source)
            source.write_bytes(b"value = 1\r\n")
            self.assertEqual(digest(source, text=True), frozen)
            self.assertNotEqual(digest(source), raw)

    def test_existing_output_is_preserved_before_reading_or_scoring(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            out.mkdir()
            sentinel = out / "sentinel"
            sentinel.write_text("보존", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "덮어쓰지"):
                run(Path(folder), out, Path(folder) / "missing-manifest.json")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "보존")


if __name__ == "__main__":
    unittest.main()
