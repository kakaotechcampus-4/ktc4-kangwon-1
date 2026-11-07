import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
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
DOMAIN_FORBIDDEN_IMPORTS = {
    "asyncio",
    "contextvars",
    "httpx",
    "openai",
    "os",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "tempfile",
    "threading",
    "urllib",
}
FILE_CALLS = {"open", "read_bytes", "read_text", "write_bytes", "write_text"}
DOMAIN_RESOURCES = APP / "domain" / "resources.py"
ENTRY_POINTS = ("app.main", "app.bootstrap")


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


def entry_imports(path, module):
    return [
        target
        for target in targets(path, module)
        if any(target == entry or target.startswith(f"{entry}.") for entry in ENTRY_POINTS)
    ]


def sql_strings(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.match(node.value):
            found.append((node.lineno, node.value.strip()[:60]))
    return found


class ArchitectureTests(unittest.TestCase):
    def test_layer_rules(self):
        self.assertEqual(sorted(violations()), [], "허용하지 않은 계층 방향입니다.")

    def test_every_app_module_belongs_to_a_layer(self):
        loose = [
            module_of(path)
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts
            and layer(module_of(path)) is None
            and module_of(path) not in {"app", "app.main", "app.bootstrap"}
        ]
        self.assertEqual(loose, [])

    def test_layers_do_not_import_entry_points(self):
        found = {
            module_of(path): entry_imports(path, module_of(path))
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts and layer(module_of(path)) is not None
        }
        self.assertEqual({module: names for module, names in found.items() if names}, {})

    def test_entry_point_probe_catches_import_forms(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.py"
            path.write_text(
                "from app import bootstrap\nimport app.main\nfrom app.bootstrap import wire\n",
                encoding="utf-8",
            )
            self.assertEqual(
                entry_imports(path, "app.application.probe"),
                ["app.bootstrap", "app.main", "app.bootstrap"],
            )

    def test_sql_stays_in_infrastructure(self):
        outside = {
            str(path.relative_to(BACKEND)).replace("\\", "/")
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts
            and layer(module_of(path)) != "infrastructure"
            and sql_strings(path)
        }
        self.assertEqual(sorted(outside), [])

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

    def test_domain_has_no_io_imports(self):
        for path in sorted((APP / "domain").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module]
                for name in names:
                    with self.subTest(path=path.name, module=name):
                        self.assertNotIn(name.split(".")[0], DOMAIN_FORBIDDEN_IMPORTS)

    def test_domain_reads_files_only_through_resources(self):
        for path in sorted((APP / "domain").rglob("*.py")):
            if path == DOMAIN_RESOURCES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    with self.subTest(path=path.name, line=node.lineno):
                        self.assertNotIn(name, FILE_CALLS)

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
