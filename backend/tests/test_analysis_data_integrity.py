"""분석 데이터의 계산·수집 무결성 회귀 시험."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.agents.business_lifecycle.agent import BusinessLifecycleAgentError, validate_llm_result
from app.agents.business_lifecycle.area_resolver import (
    BusinessAreaResolverError,
    _read_polygon_record,
    load_shape_features,
    read_dbf,
    read_polygon_shapes,
)
from app.agents.commercial_area.client import SbizApiError, StoreClient
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.commercial_area.metrics import build_radius_slices
from app.agents.commercial_area.schemas import MiddleCode, Store
from app.agents.floating_population.agent import _trend
from app.agents.floating_population.models import AGE_BANDS, DAYS, TIME_BANDS, FlpopRecord


def _flpop(quarter: str, total: float) -> FlpopRecord:
    return FlpopRecord(
        trdar_cd="A",
        stdr_yyqu_cd=quarter,
        total=total,
        male=total,
        female=0,
        by_time={key: total / len(TIME_BANDS) for key in TIME_BANDS},
        by_day={key: total / len(DAYS) for key in DAYS},
        by_age={key: total / len(AGE_BANDS) for key in AGE_BANDS},
    )


class BusinessLifecycleValidationTests(unittest.TestCase):
    def test_llm_ids_are_one_to_one_and_calculated_fields_win(self):
        source = {
            "industries": [
                {
                    "industry_id": "I201",
                    "industry_name": "계산 이름",
                    "lifecycle_score": 71.5,
                    "confidence": "high",
                }
            ]
        }
        llm = {
            "industry_scores": [
                {
                    "industry_id": "I201",
                    "industry_name": "변조 이름",
                    "lifecycle_score": -999,
                    "confidence": "none",
                    "type": "성장형",
                    "evidence": ["근거"],
                    "warning": None,
                }
            ]
        }

        validate_llm_result(source, llm)

        self.assertEqual(llm["industry_scores"][0]["industry_name"], "계산 이름")
        self.assertEqual(llm["industry_scores"][0]["lifecycle_score"], 71.5)
        self.assertEqual(llm["industry_scores"][0]["confidence"], "high")

    def test_duplicate_llm_id_is_rejected(self):
        source = {"industries": [{"industry_id": "I201"}, {"industry_id": "I202"}]}
        llm = {"industry_scores": [{"industry_id": "I201"}, {"industry_id": "I201"}]}
        with self.assertRaises(BusinessLifecycleAgentError):
            validate_llm_result(source, llm)

    def test_invalid_llm_rows_and_ids_are_rejected(self):
        cases = [
            ({"industries": [{"industry_id": "I201"}]}, ["bad"]),
            ({"industries": [{"industry_id": "I201"}]}, [{"industry_id": []}]),
            ({"industries": [{"industry_id": "I201"}]}, [{"industry_id": True}]),
            ({"industries": [{"industry_id": True}]}, [{"industry_id": "I201"}]),
            ({"industries": [{"industry_id": "I201"}]}, [{"industry_id": 1}]),
            ({"industries": [{"industry_id": "UNKNOWN"}]}, [{"industry_id": "UNKNOWN"}]),
        ]
        for source, scores in cases:
            with (
                self.subTest(source=source, scores=scores),
                self.assertRaises(BusinessLifecycleAgentError),
            ):
                validate_llm_result(source, {"industry_scores": scores})

    def test_duplicate_input_id_is_rejected(self):
        source = {"industries": [{"industry_id": "I201"}, {"industry_id": "I201"}]}
        with self.assertRaises(BusinessLifecycleAgentError):
            validate_llm_result(source, {"industry_scores": [{"industry_id": "I201"}]})


class ShapePairingTests(unittest.TestCase):
    def test_deleted_dbf_and_null_shape_keep_original_positions(self):
        attrs = [{"TRDAR_CD": "A"}, None, {"TRDAR_CD": "C"}]
        polygon = ((0.0, 0.0, 1.0, 1.0), [[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]])
        shapes = [polygon, polygon, None]
        with tempfile.TemporaryDirectory() as directory:
            shp = Path(directory) / "area.shp"
            for suffix in (".shp", ".shx", ".dbf", ".prj"):
                shp.with_suffix(suffix).write_bytes(b"x")
            with (
                patch("app.agents.business_lifecycle.area_resolver._validate_projection"),
                patch("app.agents.business_lifecycle.area_resolver.read_dbf", return_value=attrs),
                patch(
                    "app.agents.business_lifecycle.area_resolver.read_polygon_shapes",
                    return_value=shapes,
                ),
            ):
                features = load_shape_features(shp)
        self.assertEqual([feature.attributes["TRDAR_CD"] for feature in features], ["A"])

    def test_truncated_dbf_record_is_rejected(self):
        header = bytearray(65)
        header[4:8] = struct.pack("<I", 1)
        header[8:10] = struct.pack("<H", 65)
        header[10:12] = struct.pack("<H", 4)
        header[32:43] = b"NAME\x00\x00\x00\x00\x00\x00\x00"
        header[43] = ord("C")
        header[48] = 3
        header[64] = 0x0D
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.dbf"
            path.write_bytes(bytes(header) + b" x")
            with self.assertRaises(BusinessAreaResolverError):
                read_dbf(path)

    def test_truncated_null_shape_record_is_rejected(self):
        data = bytearray(108)
        data[:4] = struct.pack(">i", 9994)
        data[104:108] = struct.pack(">i", 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.shp"
            path.write_bytes(data)
            with self.assertRaises(BusinessAreaResolverError):
                read_polygon_shapes(path)

    def test_invalid_polygon_counts_and_part_offsets_are_rejected(self):
        header = struct.pack("<i4d2i", 5, 0, 0, 1, 1, -1, 3)
        with self.assertRaises(BusinessAreaResolverError):
            _read_polygon_record(header)

        points = struct.pack("<8d", 0, 0, 1, 0, 0, 1, 0, 0)
        for parts in ((1, 0), (0, 4)):
            record = struct.pack("<i4d2i", 5, 0, 0, 1, 1, len(parts), 4)
            record += struct.pack(f"<{len(parts)}i", *parts) + points
            with self.subTest(parts=parts), self.assertRaises(BusinessAreaResolverError):
                _read_polygon_record(record)

    def test_polygon_with_too_few_points_for_ring_is_rejected(self):
        record = struct.pack("<i4d2ii4d", 5, 0, 0, 1, 1, 1, 2, 0, 0, 0, 1, 1)
        with self.assertRaises(BusinessAreaResolverError):
            _read_polygon_record(record)

        unclosed = struct.pack("<i4d2ii8d", 5, 0, 0, 1, 1, 1, 4, 0, 0, 0, 1, 0, 0, 1, 1, 1)
        with self.assertRaises(BusinessAreaResolverError):
            _read_polygon_record(unclosed)


class TrendTests(unittest.TestCase):
    def test_comparisons_use_exact_quarter_keys_regardless_of_order(self):
        series = [
            ("20241", [_flpop("20241", 9100)]),
            ("20251", [_flpop("20251", 9000)]),
            ("20244", [_flpop("20244", 4600)]),
            ("20252", [_flpop("20252", 9100)]),
        ]
        trend = _trend(series, {"A"})
        self.assertEqual(
            [point.period_code for point in trend.quarters],
            ["20241", "20244", "20251", "20252"],
        )
        self.assertIsNotNone(trend.qoq_change)
        self.assertIsNone(trend.yoy_change)

    def test_missing_requested_latest_quarter_is_not_replaced_by_older_data(self):
        trend = _trend([("20251", [_flpop("20251", 9000)]), ("20252", [])], {"A"})
        self.assertIsNone(trend.qoq_change)
        self.assertIsNone(trend.yoy_change)


class CommercialClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_4xx_is_not_retried(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, request=request)

        settings = CommercialSettings(sbiz_service_key="key", max_retries=3)
        client = StoreClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with self.assertRaises(SbizApiError):
            await client._request_page(37.5, 127.0, 500, 1)
        self.assertEqual(calls, 1)

    async def test_retry_wait_is_finite_and_capped(self):
        responses = iter([(429, "inf"), (429, "999"), (200, None)])

        def handler(request: httpx.Request) -> httpx.Response:
            status, retry_after = next(responses)
            headers = {"Retry-After": retry_after} if retry_after else {}
            return httpx.Response(
                status,
                request=request,
                headers=headers,
                json={"header": {"resultCode": "00"}, "body": {"items": [], "totalCount": 0}},
            )

        settings = CommercialSettings(sbiz_service_key="key", max_retries=2, retry_backoff_s=40)
        client = StoreClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with patch("app.agents.commercial_area.client.asyncio.sleep", new=AsyncMock()) as sleep:
            await client._request_page(37.5, 127.0, 500, 1)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [30.0, 30.0])

    async def test_non_finite_base_backoff_uses_default(self):
        responses = iter([429, 200])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                next(responses),
                request=request,
                json={"header": {}, "body": {"items": [], "totalCount": 0}},
            )

        settings = CommercialSettings(
            sbiz_service_key="key", max_retries=1, retry_backoff_s=float("nan")
        )
        client = StoreClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with patch("app.agents.commercial_area.client.asyncio.sleep", new=AsyncMock()) as sleep:
            await client._request_page(37.5, 127.0, 500, 1)
        sleep.assert_awaited_once_with(1.5)

    async def test_bad_cache_shape_is_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = CommercialSettings(cache_dir=Path(directory), sbiz_service_key="key")
            path = Path(directory) / "radius_500_37.5_127.0.json"
            path.write_text(json.dumps({"wrong": []}), encoding="utf-8")
            payload = {"header": {"resultCode": "00"}, "body": {"items": [], "totalCount": 0}}
            transport = httpx.MockTransport(
                lambda request: httpx.Response(200, request=request, json=payload)
            )
            client = StoreClient(settings, httpx.AsyncClient(transport=transport))
            stores, meta = await client.stores_in_radius(37.5, 127.0, 500)
        self.assertEqual(stores, [])
        self.assertFalse(meta["from_cache"])

    async def test_non_object_cache_item_is_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = CommercialSettings(cache_dir=Path(directory), sbiz_service_key="key")
            path = Path(directory) / "radius_500_37.5_127.0.json"
            path.write_text(json.dumps({"items": ["bad"], "meta": {}}), encoding="utf-8")
            payload = {"header": {}, "body": {"items": [], "totalCount": 0}}
            client = StoreClient(
                settings,
                httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, request=request, json=payload)
                    )
                ),
            )
            stores, meta = await client.stores_in_radius(37.5, 127.0, 500)
        self.assertEqual(stores, [])
        self.assertFalse(meta["from_cache"])

    async def test_missing_items_is_bad_response_but_empty_items_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = CommercialSettings(cache_dir=Path(directory), sbiz_service_key="key")
            missing = {"header": {"resultCode": "00"}, "body": {"totalCount": 0}}
            client = StoreClient(
                settings,
                httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, request=request, json=missing)
                    )
                ),
            )
            with self.assertRaisesRegex(SbizApiError, "BAD_RESPONSE"):
                await client.stores_in_radius(37.5, 127.0, 500, use_cache=False)

            valid = {"header": {"resultCode": "00"}, "body": {"items": [], "totalCount": 0}}
            client = StoreClient(
                settings,
                httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, request=request, json=valid)
                    )
                ),
            )
            stores, _ = await client.stores_in_radius(37.5, 127.0, 500, use_cache=False)
        self.assertEqual(stores, [])

    async def test_non_object_api_payload_is_bad_response(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = CommercialSettings(cache_dir=Path(directory), sbiz_service_key="key")
            client = StoreClient(
                settings,
                httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, request=request, json=[])
                    )
                ),
            )
            with self.assertRaisesRegex(SbizApiError, "BAD_RESPONSE"):
                await client.stores_in_radius(37.5, 127.0, 500, use_cache=False)

    async def test_non_object_api_item_and_header_are_bad_response(self):
        payloads = [
            {"header": {}, "body": {"items": ["bad"], "totalCount": 1}},
            {"header": [], "body": {"items": [], "totalCount": 0}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            settings = CommercialSettings(cache_dir=Path(directory), sbiz_service_key="key")
            for payload in payloads:
                with self.subTest(payload=payload):
                    client = StoreClient(
                        settings,
                        httpx.AsyncClient(
                            transport=httpx.MockTransport(
                                lambda request, value=payload: httpx.Response(
                                    200, request=request, json=value
                                )
                            )
                        ),
                    )
                    with self.assertRaisesRegex(SbizApiError, "BAD_RESPONSE"):
                        await client.stores_in_radius(37.5, 127.0, 500, use_cache=False)


class CommercialCalculationTests(unittest.TestCase):
    def test_specialization_without_baseline_radius_does_not_invent_zero_metres(self):
        master = [MiddleCode(code="I201", name="한식", major_code="I2", major_name="음식점업")]
        stores = [
            Store(
                store_id=str(index),
                name="가게",
                major_code="I2",
                major_name="음식점업",
                branch_name=None,
                middle_code="I201",
                middle_name="한식",
                small_code=None,
                small_name=None,
                latitude=37.5,
                longitude=127.0,
                road_address=None,
            )
            for index in range(5)
        ]
        slices = build_radius_slices(
            stores, 37.5, 127.0, master, CommercialSettings(), {"I201": 10}, None
        )
        text = slices[-1].explanations.specialization
        self.assertNotIn("0m", text)
        self.assertNotIn("None", text)


if __name__ == "__main__":
    unittest.main()
