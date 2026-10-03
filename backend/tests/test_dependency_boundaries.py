"""하위 계층의 import 방향과 독립적인 목업 구성을 검사합니다."""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


class DependencyBoundaryTests(unittest.TestCase):
    def test_mocking_imports_in_fresh_process(self):
        result = subprocess.run(
            [sys.executable, "-c", "import app.services.mocking"],
            cwd=APP.parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lower_layers_do_not_import_services_or_api(self):
        for root in (APP / "db", APP / "agents", APP / "execution"):
            for path in root.rglob("*.py"):
                with self.subTest(path=path.relative_to(APP)):
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        modules = (
                            [node.module or ""]
                            if isinstance(node, ast.ImportFrom)
                            else [alias.name for alias in node.names]
                            if isinstance(node, ast.Import)
                            else []
                        )
                        self.assertFalse(
                            any(
                                module == forbidden or module.startswith(forbidden + ".")
                                for module in modules
                                for forbidden in ("app.services", "app.api")
                            ),
                            f"{path.relative_to(APP)}:{getattr(node, 'lineno', 0)}",
                        )

    def test_common_execution_rules_have_no_storage_or_http_dependency(self):
        for path in (APP / "execution").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                self.assertFalse(
                    any(module.split(".")[0] in {"sqlite3", "fastapi"} for module in modules)
                )
