import csv
import tempfile
import unittest
from pathlib import Path

from app.industries.catalog import INDUSTRIES
from backtest.catalog import develop_code, invalid_rows, read_sample, row_key

FIELDS = ["업종코드", "업종", "그룹", "순번", "상호", "주소"]
CODE, NAME = next((c, n) for c, n in INDUSTRIES.items() if "·" in n)


def sample(rows, folder):
    path = Path(folder) / "sample.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(code="SV001", name=NAME, number="1", address="서울 마포구 와우산로 94"):
    return {
        "업종코드": code,
        "업종": name,
        "그룹": "1",
        "순번": number,
        "상호": "가",
        "주소": address,
    }


class CatalogTests(unittest.TestCase):
    def test_every_develop_name_maps_to_its_code(self):
        for code, name in INDUSTRIES.items():
            self.assertEqual(develop_code(name), code)

    def test_spacing_and_middle_dot_variants_map(self):
        variant = " " + NAME.replace("·", "ㆍ").replace(" ", "  ") + " "
        self.assertEqual(develop_code(variant), CODE)

    def test_unknown_name_raises(self):
        with self.assertRaises(KeyError):
            develop_code("없는 업종")

    def test_read_sample_picks_rows_by_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = sample([row(number="1"), row(number="2")], folder)
            rows = read_sample(path, {"SV001-2"})
        self.assertEqual([row_key(r) for r in rows], ["SV001-2"])

    def test_invalid_rows_reports_duplicates_unknown_names_and_empty_addresses(self):
        problems = invalid_rows(
            [
                row(number="1"),
                row(number="1"),
                row(number="2", name="없는 업종"),
                row(number="3", address=" "),
            ]
        )
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("두 번" in p for p in problems))
        self.assertTrue(any("없는 업종" in p for p in problems))
        self.assertTrue(any("주소" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
