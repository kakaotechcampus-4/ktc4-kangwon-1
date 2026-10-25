"""순위 규칙이 DB를 쓰는 공간 비교 모듈과 비공개 함수에 기대지 않는지 확인합니다."""

import ast
import unittest
from pathlib import Path

AGENTIC = Path(__file__).resolve().parents[1] / "app" / "agentic"
PURE = ("scoring.py", "space_rules.py", "space_values.py")


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]


class SpaceRulesBoundaryTests(unittest.TestCase):
    def test_rules_do_not_import_db_layer(self):
        for name in PURE:
            path = AGENTIC / name
            self.assertTrue(path.is_file(), name)
            for node in imports(path):
                with self.subTest(file=name, line=node.lineno):
                    if isinstance(node, ast.ImportFrom):
                        module = ("." * node.level) + (node.module or "")
                        self.assertNotIn(module, {".space", "app.agentic.space"})
                        self.assertFalse(module.startswith(("app.db", ".facts")))
                    else:
                        self.assertFalse(any(a.name.startswith("app.db") for a in node.names))

    def test_rules_use_public_space_helpers(self):
        for node in imports(AGENTIC / "space_rules.py"):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                for alias in node.names:
                    with self.subTest(name=alias.name):
                        self.assertFalse(alias.name.startswith("_"))
