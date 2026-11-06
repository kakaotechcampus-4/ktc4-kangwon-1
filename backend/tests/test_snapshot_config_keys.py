"""설정 해시가 파일 위치·import 줄이 아니라 계산 내용과 버전에만 묶이는지 확인합니다."""

import ast
import hashlib
import unittest
from pathlib import Path

from app.agentic import code90
from app.agentic.snapshot import snapshot_config
from app.agents.commercial_area import baseline as density_baseline
from app.canonical import canonical_hash
from app.local_data import score_reference

CODE90_LOGIC = "92394464"
REFERENCE_LOGIC = "68d23072"


def logic_fingerprint(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
        and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                node.body = node.body[1:] or [ast.Pass()]
    dump = ast.dump(ast.Module(body=body, type_ignores=[]))
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()[:8]


class SnapshotConfigKeyTests(unittest.TestCase):
    def test_keys_are_logical_names(self):
        _, hashes, _ = snapshot_config(None, local=True)
        self.assertEqual(
            set(hashes),
            {
                "industry_profile",
                "code90",
                "code90_reference",
                "population_baseline",
                "density_baseline",
                "lifecycle_baseline",
            },
        )

    def test_code_values_follow_content_not_file(self):
        _, hashes, _ = snapshot_config(None, local=True)
        self.assertEqual(
            hashes["density_baseline"],
            canonical_hash(
                [
                    {
                        "configuration": "density_baseline",
                        "values": density_baseline.SEOUL_INDUSTRY_DENSITY_PERCENTILES,
                    }
                ]
            ),
        )
        self.assertEqual(
            hashes["code90_reference"],
            canonical_hash(
                [
                    {
                        "configuration": "code90_reference",
                        "method": code90.METHOD,
                        "version": score_reference.REFERENCE_VERSION,
                    }
                ]
            ),
        )

    def test_logic_change_requires_version_bump(self):
        self.assertEqual(
            logic_fingerprint(code90),
            CODE90_LOGIC,
            "code90 계산이 바뀌었습니다. code90.METHOD를 올리고 이 지문을 갱신하세요.",
        )
        self.assertEqual(
            logic_fingerprint(score_reference),
            REFERENCE_LOGIC,
            "참고 분포 계산이 바뀌었습니다. REFERENCE_VERSION을 올리고 이 지문을 갱신하세요.",
        )


if __name__ == "__main__":
    unittest.main()
