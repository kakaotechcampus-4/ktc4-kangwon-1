"""오프라인 실행의 네트워크 차단·읽기 전용 원천·전체 점수 저장을 확인합니다."""

import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic.scoring import BASELINE_BASE_QUARTER
from backtest.offline import block_network, load_sites, run
from tests.backtest_fixture import build_market


class OfflineTests(unittest.TestCase):
    def test_network_is_blocked_before_dns_or_connection(self):
        with block_network():
            with self.assertRaisesRegex(RuntimeError, "네트워크"):
                socket.getaddrinfo("example.invalid", 443)
            with socket.socket() as client:
                with self.assertRaisesRegex(RuntimeError, "네트워크"):
                    client.connect(("192.0.2.1", 443))

    def sites_file(self, root, site, identifier="sample"):
        path = root / "sites.json"
        path.write_text(
            json.dumps({"sites": [{"id": identifier, "site": site.model_dump(mode="json")}]}),
            encoding="utf-8",
        )
        return path

    def test_saves_all_industries_without_resolving_addresses_or_constructing_http(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_path = root / "market.sqlite3"
            site = build_market(data_path, BASELINE_BASE_QUARTER)
            sites = self.sites_file(root, site)
            before = hashlib.sha256(data_path.read_bytes()).hexdigest()
            with (
                patch("app.address.resolve_site", side_effect=AssertionError("주소 API 금지")),
                patch("httpx.AsyncClient", side_effect=AssertionError("HTTP 금지")),
                patch("httpx.Client", side_effect=AssertionError("HTTP 금지")),
            ):
                manifest = run(sites, data_path, root / "out")
            saved = json.loads((root / "out/sample.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["scores"]), 51)
            self.assertEqual(manifest["industry_score_count"], 51)
            self.assertEqual(manifest["llm_calls"], 0)
            self.assertEqual((root / "out/sites.json").read_bytes(), sites.read_bytes())
            self.assertEqual(saved["data"]["education_zones"]["status"], "not_queried")
            self.assertTrue(
                all(row["items"]["L"]["status"] == "unknown" for row in saved["scores"])
            )
            self.assertEqual(hashlib.sha256(data_path.read_bytes()).hexdigest(), before)

    def test_mismatched_quarter_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_path = root / "market.sqlite3"
            site = build_market(data_path, "20234")
            sites = self.sites_file(root, site)
            with self.assertRaisesRegex(ValueError, "최신 분기"):
                run(sites, data_path, root / "out")
            self.assertFalse((root / "out").exists())

    def test_existing_results_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_path = root / "market.sqlite3"
            site = build_market(data_path, BASELINE_BASE_QUARTER)
            sites = self.sites_file(root, site)
            output = root / "out"
            output.mkdir()
            sentinel = output / "existing.txt"
            sentinel.write_text("보존", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "이미 있습니다"):
                run(sites, data_path, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "보존")

    def test_path_traversal_in_case_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = build_market(root / "market.sqlite3", BASELINE_BASE_QUARTER)
            sites = self.sites_file(root, site, "../outside")
            with self.assertRaisesRegex(ValueError, "사례 ID"):
                load_sites(sites)


if __name__ == "__main__":
    unittest.main()
