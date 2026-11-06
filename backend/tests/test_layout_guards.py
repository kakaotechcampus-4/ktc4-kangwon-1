"""파일을 옮겨도 경로·자료·전역 상태가 조용히 어긋나지 않게 막는 규칙입니다."""

import ast
import importlib
import re
import tomllib
import unittest
from pathlib import Path

from app import config
from app.db import connection

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


def app_sources():
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


class LayoutGuardTests(unittest.TestCase):
    def test_backend_dir_is_defined_once(self):
        self.assertEqual(config.BACKEND_DIR, BACKEND)
        self.assertTrue((config.BACKEND_DIR / "pyproject.toml").exists())
        self.assertIs(connection.BACKEND_DIR, config.BACKEND_DIR)

    def test_paths_do_not_depend_on_module_depth(self):
        pattern = re.compile(r"__file__\)?(?:\.resolve\(\))?\.parents\[\d+\]")
        offenders = [
            str(path.relative_to(BACKEND))
            for path in app_sources()
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

    def test_resources_are_not_found_by_package_name_literal(self):
        offenders = [
            str(path.relative_to(BACKEND))
            for path in app_sources()
            if 'files("app.' in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_package_data_points_at_real_files(self):
        setting = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = setting["tool"]["setuptools"]["package-data"]
        for package, patterns in package_data.items():
            with self.subTest(package=package):
                module = importlib.import_module(package)
                folder = Path(module.__file__).parent
                for pattern in patterns:
                    self.assertTrue(list(folder.glob(pattern)), pattern)

    def test_every_code_folder_is_a_package(self):
        folders = {path.parent for path in app_sources()}
        missing = [
            str(folder.relative_to(BACKEND))
            for folder in folders
            if not (folder / "__init__.py").exists()
        ]
        self.assertEqual(missing, [])

    def test_context_vars_are_defined_once(self):
        names = []
        for path in app_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", getattr(node.func, "attr", None)) == "ContextVar"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    names.append(node.args[0].value)
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)), names)


if __name__ == "__main__":
    unittest.main()
