"""판단 코드(app/agentic)에 SQL 문장이 남지 않고 저장소 계층으로만 DB를 쓰는지 확인합니다."""

import ast
import re
import unittest
from pathlib import Path

AGENTIC = Path(__file__).resolve().parents[1] / "app" / "agentic"
SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|BEGIN|WITH|CREATE)\b")
MODEL_SQL_TOOL = "sql_tool.py"
PENDING = {
    "advisor.py",
    "evaluators.py",
    "questions.py",
    "runtime.py",
}


def sql_strings(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.match(node.value):
            found.append((node.lineno, node.value.strip()[:60]))
    return found


class AgenticSqlBoundaryTests(unittest.TestCase):
    def test_agentic_has_no_sql_outside_model_tool(self):
        for path in sorted(AGENTIC.glob("*.py")):
            if path.name == MODEL_SQL_TOOL or path.name in PENDING:
                continue
            with self.subTest(file=path.name):
                self.assertEqual(sql_strings(path), [])

    def test_pending_files_still_hold_sql(self):
        for name in sorted(PENDING):
            with self.subTest(file=name):
                self.assertNotEqual(sql_strings(AGENTIC / name), [])
