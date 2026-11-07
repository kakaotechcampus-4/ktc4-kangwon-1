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
FILE_CALLS = {
    "exists",
    "glob",
    "is_dir",
    "is_file",
    "iterdir",
    "mkdir",
    "open",
    "read_bytes",
    "read_csv",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_text",
    "rglob",
    "rmdir",
    "to_csv",
    "to_excel",
    "to_json",
    "to_parquet",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
DOMAIN_FORBIDDEN_SHARED = {
    "app.shared.concurrency",
    "app.shared.logging",
    "app.shared.scrub",
    "app.shared.canonical.file_sha256",
}
LEAF_MODULES = ("app.application.ports", "app.application.errors")
DOMAIN_RESOURCES = APP / "domain" / "resources.py"
ENTRY_POINTS = ("app.main", "app.bootstrap")
DRIVERS = {"httpx", "openai", "sqlite3"}
STORED_NAME = re.compile(r"^[a-z_]+_json$")
CODEC_NAMES = {
    "canonical_json",
    "complete_json",
    "input_json",
    "model_dump_json",
    "model_validate_json",
}
HTTP_STATUS = {400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504}
SCORING_MODULES = (
    "app.application.analysis",
    "app.application.local_snapshot",
    "app.application.preflight",
    "app.application.snapshot",
    "app.domain.scoring",
)


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


def identifiers(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute):
            yield node.lineno, node.attr
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.value.lineno, node.arg
        elif isinstance(node, ast.Name):
            yield node.lineno, node.id
        elif isinstance(node, ast.arg):
            yield node.lineno, node.arg
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def layer_files(*names):
    for name in names:
        for path in sorted((APP / name).rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


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

    def test_only_infrastructure_uses_drivers(self):
        found = {
            module_of(path): sorted(
                DRIVERS & {t.split(".")[0] for t in targets(path, module_of(path))}
            )
            for path in APP.rglob("*.py")
            if "__pycache__" not in path.parts
            and layer(module_of(path)) != "infrastructure"
            and module_of(path) not in {"app.main", "app.bootstrap"}
        }
        self.assertEqual({module: names for module, names in found.items() if names}, {})

    def test_stored_column_names_stay_in_infrastructure(self):
        found = {
            f"{path.relative_to(APP)}:{line}:{name}"
            for path in layer_files("ai", "application", "api", "domain")
            for line, name in identifiers(path)
            if STORED_NAME.match(name) and name not in CODEC_NAMES
        }
        self.assertEqual(sorted(found), [])

    def test_api_and_ai_do_not_know_where_data_lives(self):
        found = {
            f"{path.relative_to(APP)}:{line}:{name}"
            for path in layer_files("ai", "api")
            for line, name in identifiers(path)
            if name == "db_path"
        }
        found |= {
            f"{path.relative_to(APP)}:{node.lineno}:path"
            for path in layer_files("ai")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Attribute) and node.attr == "path"
        }
        self.assertEqual(sorted(found), [])

    def test_application_errors_do_not_carry_http_status(self):
        found = set()
        for path in layer_files("application"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", "")
                )
                if name.endswith(("Failed", "Rejected", "Error")) and any(
                    isinstance(arg, ast.Constant) and arg.value in HTTP_STATUS for arg in node.args
                ):
                    found.add(f"{path.relative_to(APP)}:{node.lineno}:{name}")
        self.assertEqual(sorted(found), [])

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
                    names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
                for name in names:
                    with self.subTest(path=path.name, module=name):
                        self.assertNotIn(name.split(".")[0], DOMAIN_FORBIDDEN_IMPORTS)
                        self.assertFalse(
                            any(
                                name == f or name.startswith(f"{f}.")
                                for f in DOMAIN_FORBIDDEN_SHARED
                            )
                        )

    def test_ports_and_errors_import_only_contracts(self):
        allowed = (*LEAF_MODULES, "app.domain", "app.shared")
        for path in APP.rglob("*.py"):
            source = module_of(path)
            if "__pycache__" in path.parts or not source.startswith(LEAF_MODULES):
                continue
            for target in targets(path, source):
                if target.startswith("app."):
                    with self.subTest(source=source, target=target):
                        self.assertTrue(
                            any(target == a or target.startswith(f"{a}.") for a in allowed)
                        )

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
