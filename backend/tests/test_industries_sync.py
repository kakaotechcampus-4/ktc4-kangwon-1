"""원본 CSV와 생성된 catalog.py가 어긋나지 않았는지 검사합니다.

CSV만 고치고 재생성을 잊으면 런타임이 옛 표를 계속 씁니다. 그걸 여기서 잡습니다.
"""

import subprocess
import sys
import unittest
from pathlib import Path

from app.industries import DATA_DIR

BACKEND_DIR = Path(__file__).resolve().parents[1]
BUILDER = BACKEND_DIR / "scripts" / "build_industry_catalog.py"


@unittest.skipUnless(DATA_DIR.exists(), "설치본에는 원본 CSV가 없습니다")
class CatalogSyncTests(unittest.TestCase):
    def test_csv_files_are_utf8_with_bom(self):
        for path in sorted(DATA_DIR.glob("*.csv")):
            with self.subTest(path.name):
                self.assertTrue(
                    path.read_bytes().startswith(b"\xef\xbb\xbf"),
                    f"{path.name}이 BOM 없는 파일입니다. 엑셀로 저장하지 마세요.",
                )

    @unittest.skipUnless(BUILDER.exists(), "빌드 스크립트가 없습니다")
    def test_catalog_matches_the_csv_sources(self):
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--check"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
