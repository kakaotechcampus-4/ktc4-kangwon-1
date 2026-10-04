"""캐시 작업이 이벤트 루프를 막거나 분석 값을 바꾸지 않는지 검사합니다."""

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.agents.commercial_area import client, franchise
from app.agents.commercial_area.config import Settings

ITEM = {
    "bizesId": "test-1",
    "bizesNm": "시험 점포",
    "brchNm": "본점",
    "indsLclsCd": "I2",
    "indsLclsNm": "음식점업",
    "indsMclsCd": "I201",
    "indsMclsNm": "한식 음식점업",
    "indsSclsCd": "I20101",
    "indsSclsNm": "백반",
    "lat": "37.5",
    "lon": "127",
    "rdnmAdr": "시험 주소",
    "signguCd": "11710",
    "signguNm": "송파구",
    "stdrDt": "2026-09-01",
    "unused_large_field": "x" * 10000,
}


class CacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(cache_dir=Path(self.tmp.name), sbiz_service_key="test")

    def test_invalid_utf8_cache_is_ignored(self):
        with (
            patch.object(
                Path, "read_text", side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
            ),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "stat") as stat,
        ):
            stat.return_value.st_mtime = float("inf")
            self.assertIsNone(client._read_cache(self.settings.cache_dir / "bad.json", 24))
            self.assertIsNone(franchise.load_cached_brands(self.settings))

    async def test_cache_io_and_conversion_leave_event_loop_free(self):
        loop_thread = threading.get_ident()
        loop = asyncio.get_running_loop()
        for method in ("stores_in_radius", "stores_in_district"):
            with self.subTest(method=method):
                payload = {"body": {"items": [ITEM], "totalCount": 1}}
                http = httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda _, payload=payload: httpx.Response(200, json=payload)
                    )
                )
                self.addAsyncCleanup(http.aclose)
                store_client = client.StoreClient(self.settings, http)

                def guarded(fn):
                    def call(*call_args):
                        self.assertNotEqual(threading.get_ident(), loop_thread)
                        # 동기 작업이 다른 코루틴의 진행을 기다려도 교착하지 않아야 합니다.
                        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop).result(2)
                        return fn(*call_args)

                    return call

                with (
                    patch.object(client, "_read_cache", side_effect=guarded(client._read_cache)),
                    patch.object(client, "_write_cache", side_effect=guarded(client._write_cache)),
                    patch.object(client, "to_store", side_effect=guarded(client.to_store)),
                ):
                    args = (37.5, 127, 300) if method == "stores_in_radius" else ("11710",)
                    first, meta = await getattr(store_client, method)(*args)
                    second, cached = await getattr(store_client, method)(*args)
                self.assertEqual(first, second)
                self.assertEqual(first[0], client.to_store(ITEM))
                self.assertEqual(meta["reference_date"], "2026-09-01")
                self.assertTrue(cached["from_cache"])

    async def test_cache_saves_only_store_fields_and_metadata(self):
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"body": {"items": [ITEM], "totalCount": 1}})
            )
        )
        self.addAsyncCleanup(http.aclose)
        store_client = client.StoreClient(self.settings, http)
        expected, _ = await store_client.stores_in_district("11710")
        payload = json.loads(
            await asyncio.to_thread(
                (self.settings.cache_dir / "district_11710.json").read_text, encoding="utf-8"
            )
        )
        self.assertNotIn("unused_large_field", payload["items"][0])
        self.assertEqual(client.to_store(payload["items"][0]), expected[0])
        self.assertEqual(payload["meta"]["reference_date"], "2026-09-01")

    async def test_brand_cache_io_is_offloaded(self):
        loop_thread = threading.get_ident()
        original_load, original_save = franchise.load_cached_brands, franchise.save_brands

        def load(settings):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return original_load(settings)

        def save(settings, brands):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return original_save(settings, brands)

        settings = Settings(cache_dir=self.settings.cache_dir, ftc_service_key="test")
        with (
            patch.object(franchise, "load_cached_brands", side_effect=load),
            patch.object(franchise, "save_brands", side_effect=save),
            patch.object(franchise, "fetch_brands", new=AsyncMock(return_value=["시험브랜드"])),
        ):
            self.assertEqual(await franchise.load_brands(settings), ["시험브랜드"])
            self.assertEqual(await franchise.load_brands(settings), ["시험브랜드"])

    async def test_previous_full_cache_is_read_without_network(self):
        path = self.settings.cache_dir / "district_11710.json"
        await asyncio.to_thread(
            path.write_text,
            json.dumps({"items": [ITEM], "meta": {"reference_date": "2026-09-01"}}),
            encoding="utf-8",
        )

        def no_network(request):
            raise AssertionError("유효한 기존 캐시는 외부 조회 없이 읽어야 합니다.")

        async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as http:
            stores, meta = await client.StoreClient(self.settings, http).stores_in_district("11710")
        self.assertEqual(stores, [client.to_store(ITEM)])
        self.assertTrue(meta["from_cache"])
        self.assertEqual(meta["reference_date"], "2026-09-01")
