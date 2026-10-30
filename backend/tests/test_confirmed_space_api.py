import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.v1.analyses import analysis_runner
from app.main import create_app
from app.services.settings import ExecutionSettings
from tests.auth_fixture import login


class ConfirmedSpaceApiTests(unittest.TestCase):
    def post(self, **fields):
        seen = {}

        async def runner(*args, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                status="waiting_for_input", question_session_id="q", questions=[]
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "api.sqlite3"
            app = create_app(settings=ExecutionSettings(db_path=path), load_env=False)
            login(app, path)
            app.dependency_overrides[analysis_runner] = lambda: runner
            with TestClient(app) as client:
                response = client.post("/api/v1/analyses", json={"address": "시험", **fields})
        return response, seen

    def test_floor_and_area_reach_runner(self):
        response, seen = self.post(floor="4층", exclusive_area_m2=93.6)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(seen["confirmed_space"], {"floor": "4층", "exclusive_area": "93.6㎡"})

    def test_area_text_drops_trailing_zeros(self):
        _, seen = self.post(floor="지하 1층", exclusive_area_m2=100)
        self.assertEqual(seen["confirmed_space"], {"floor": "지하 1층", "exclusive_area": "100㎡"})

    def test_only_one_value(self):
        _, seen = self.post(exclusive_area_m2=0.01)
        self.assertEqual(seen["confirmed_space"], {"exclusive_area": "0.01㎡"})

    def test_without_values_runner_gets_none(self):
        response, seen = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(seen["confirmed_space"])

    def test_facilities_field_accepts_states(self):
        response, seen = self.post(
            floor="1층", facilities={"ventilation": "unavailable", "kitchen": "present"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            seen["confirmed_space"],
            {
                "floor": "1층",
                "existing_facilities": {"kitchen": "present", "ventilation": "unavailable"},
            },
        )

    def test_installable_and_all_three_keys(self):
        _, seen = self.post(
            facilities={"kitchen": "installable", "ventilation": "present", "water_supply": None}
        )
        self.assertEqual(
            seen["confirmed_space"],
            {"existing_facilities": {"kitchen": "installable", "ventilation": "present"}},
        )

    def test_empty_facilities_saves_nothing(self):
        for facilities in ({}, {"kitchen": None, "ventilation": None, "water_supply": None}):
            with self.subTest(facilities=facilities):
                response, seen = self.post(facilities=facilities)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNone(seen["confirmed_space"])

    def test_facilities_rejects_unknown_value_and_extra_key(self):
        for facilities in (
            {"ventilation": "maybe"},
            {"ventilation": "unknown"},
            {"duct": "present"},
            "present",
        ):
            with self.subTest(facilities=facilities):
                response, seen = self.post(facilities=facilities)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(seen, {})

    def test_bad_values_are_422(self):
        for fields in (
            {"floor": "4층 401호"},
            {"floor": "지하1층"},
            {"floor": "0층"},
            {"floor": "1F"},
            {"exclusive_area_m2": 0},
            {"exclusive_area_m2": 0.001},
            {"exclusive_area_m2": 100001},
            {"exclusive_area_m2": "넓음"},
            {"exclusive_area_m2": "93.6"},
            {"exclusive_area_m2": True},
        ):
            with self.subTest(fields=fields):
                response, seen = self.post(**fields)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(seen, {})


if __name__ == "__main__":
    unittest.main()
