"""판단 코드(app/agentic)에 SQL 문장이 남지 않고 저장소 계층으로만 DB를 쓰는지 확인합니다."""

import ast
import re
import tempfile
import unittest
from pathlib import Path

AGENTIC = Path(__file__).resolve().parents[1] / "app" / "agentic"
SQL = re.compile(
    r"^\s*\(*\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|"
    r"RELEASE|WITH|CREATE|DROP|ALTER|PRAGMA)\b",
    re.IGNORECASE,
)
MODEL_SQL_TOOL = "sql_tool.py"


def sql_strings(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.match(node.value):
            found.append((node.lineno, node.value.strip()[:60]))
    return found


class AgenticSqlBoundaryTests(unittest.TestCase):
    def test_agentic_has_no_sql_outside_model_tool(self):
        self.assertTrue((AGENTIC / MODEL_SQL_TOOL).is_file())
        for path in sorted(AGENTIC.glob("*.py")):
            if path.name == MODEL_SQL_TOOL:
                continue
            with self.subTest(file=path.name):
                self.assertEqual(sql_strings(path), [])

    def test_catches_lowercase_parenthesized_and_other_statements(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.py"
            path.write_text(
                'A = "select 1"\n'
                'B = "(SELECT 1)"\n'
                'C = "PRAGMA foreign_keys"\n'
                'D = "REPLACE INTO t VALUES(1)"\n'
                'E = "values"\n',
                encoding="utf-8",
            )
            self.assertEqual([line for line, _ in sql_strings(path)], [1, 2, 3, 4])
