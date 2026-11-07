import ast
import hashlib
import unittest
from pathlib import Path

from app.application.snapshot import snapshot_config
from app.domain import code90
from app.domain.baselines import commercial_area as density_baseline
from app.domain.baselines import floating_population as population_baseline
from app.infrastructure.market_data.local import score_reference
from app.shared.canonical import canonical_hash

CODE90_LOGIC = "92394464"
REFERENCE_LOGIC = "ca2260a8"
POPULATION_LOGIC = "72429f98"
DENSITY_LOGIC = "d6eee7bb"


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
            node.body = [
                child for child in node.body if not isinstance(child, (ast.Import, ast.ImportFrom))
            ] or [ast.Pass()]
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
                        "method": density_baseline.METHOD,
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
        self.assertEqual(
            logic_fingerprint(population_baseline),
            POPULATION_LOGIC,
            "유동인구 기준선이 바뀌었습니다. METHOD를 올리고 이 지문을 갱신하세요.",
        )
        self.assertEqual(
            logic_fingerprint(density_baseline),
            DENSITY_LOGIC,
            "밀도 기준선이 바뀌었습니다. METHOD를 올리고 이 지문을 갱신하세요.",
        )

    def test_population_row_carries_method(self):
        _, hashes, _ = snapshot_config(None, local=True)
        values = {
            name: getattr(population_baseline, name)
            for name in (
                "AGE_SHARE_AVG",
                "TIME_PER_HOUR_SHARE_AVG",
                "WEEKEND_TO_WEEKDAY_AVG",
                "TIME_BAND_DAILY_PERCENTILES",
                "PATTERN_DAILY_PERCENTILES",
                "DAILY_TOTAL_PERCENTILES",
            )
        }
        self.assertEqual(
            hashes["population_baseline"],
            canonical_hash(
                [
                    {
                        "configuration": "population_baseline",
                        "method": population_baseline.METHOD,
                        "values": values,
                    }
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
