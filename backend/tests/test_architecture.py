import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
ALLOWLIST = Path(__file__).parent / "fixtures" / "architecture_allowlist.txt"
ALLOWED = {
    "domain": ("domain", "shared"),
    "shared": ("shared",),
    "application": ("application", "domain", "shared"),
    "ai": ("ai", "application", "domain", "shared"),
    "infrastructure": (
        "infrastructure",
        "domain",
        "shared",
        "application.ports",
        "application.errors",
    ),
    "api": ("api", "application", "domain", "shared"),
}
SQL = re.compile(
    r"^\s*\(*\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|"
    r"RELEASE|WITH|CREATE|DROP|ALTER|PRAGMA)\b\s+\S",
    re.IGNORECASE,
)
SQL_OUTSIDE_INFRASTRUCTURE = {
    "app/ai/sql_tool.py",
    "app/application/analysis.py",
    "app/application/local_snapshot.py",
}


def module_of(path):
    parts = path.relative_to(BACKEND).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def is_module(dotted):
    path = BACKEND / Path(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def targets(path, module):
    package = module.split(".")[:-1]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            source = ".".join([*base, *([node.module] if node.module else [])])
            for alias in node.names:
                full = f"{source}.{alias.name}"
                yield full if is_module(full) or not node.module else source


def layer(dotted):
    parts = dotted.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "app" and parts[1] in ALLOWED else None


def allowed(source, target):
    rules = ALLOWED[layer(source)]
    return any(target == f"app.{rule}" or target.startswith(f"app.{rule}.") for rule in rules)


def violations():
    found = set()
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = module_of(path)
        if layer(source) is None:
            continue
        for target in targets(path, source):
            if layer(target) is not None and not allowed(source, target):
                found.add(f"{source} -> {target}")
    return found


def sql_strings(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.match(node.value):
            found.append((node.lineno, node.value.strip()[:60]))
    return found


class ArchitectureTests(unittest.TestCase):
    def test_layer_rules_only_shrink(self):
        current = violations()
        listed = {line for line in ALLOWLIST.read_text(encoding="utf-8").splitlines() if line}
        self.assertEqual(sorted(current - listed), [], "허용하지 않은 계층 방향입니다.")
        self.assertEqual(sorted(listed - current), [], "고친 위반은 허용목록에서 지우세요.")

    def test_every_app_module_belongs_to_a_layer(self):
        loose = [
            module_of(path)
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts
            and layer(module_of(path)) is None
            and module_of(path) not in {"app", "app.main"}
        ]
        self.assertEqual(loose, [])

    def test_sql_stays_in_infrastructure(self):
        outside = {
            str(path.relative_to(BACKEND)).replace("\\", "/")
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts
            and layer(module_of(path)) != "infrastructure"
            and sql_strings(path)
        }
        self.assertEqual(sorted(outside - SQL_OUTSIDE_INFRASTRUCTURE), [])
        self.assertEqual(sorted(SQL_OUTSIDE_INFRASTRUCTURE - outside), [])

    def test_sql_probe_catches_statement_forms(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.py"
            path.write_text(
                'A = "select 1"\n'
                'B = "(SELECT 1)"\n'
                'C = "PRAGMA foreign_keys"\n'
                'D = "REPLACE INTO t VALUES(1)"\n'
                'E = "values"\n'
                'F = "DELETE"\n',
                encoding="utf-8",
            )
            self.assertEqual([line for line, _ in sql_strings(path)], [1, 2, 3, 4])

    def test_relative_imports_are_resolved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.py"
            path.write_text(
                "from ..infrastructure.persistence.connection import connect\nfrom . import text\n",
                encoding="utf-8",
            )
            found = set(targets(path, "app.domain.probe"))
        self.assertIn("app.infrastructure.persistence.connection", found)
        self.assertIn("app.domain.text", found)
        self.assertFalse(allowed("app.domain.probe", "app.infrastructure.persistence.connection"))

    def test_space_rules_use_public_helpers(self):
        tree = ast.parse((APP / "domain" / "space_rules.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                for alias in node.names:
                    with self.subTest(name=alias.name):
                        self.assertFalse(alias.name.startswith("_"))

    def test_mock_imports_in_fresh_process(self):
        result = subprocess.run(
            [sys.executable, "-c", "import app.infrastructure.mock"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
