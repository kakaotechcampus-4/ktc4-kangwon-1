"""배포하는 실제 상권영역 파일로 좌표 해석을 검증합니다."""

import unittest
from unittest.mock import patch

from app.agents.business_lifecycle.area_resolver import resolve_area
from app.agents.business_lifecycle.config import Settings
from app.schemas import Site


class BusinessAreaDataTests(unittest.TestCase):
    def test_gaerong_address_resolves_with_bundled_files(self):
        site = Site(
            input_address="서울 송파구 오금로 404",
            road_address="서울 송파구 오금로 404",
            latitude=37.4975927810188,
            longitude=127.135121781578,
        )
        with patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지")):
            area = resolve_area(site, Settings())
        self.assertEqual(area.area_code, "3120240")
        self.assertEqual(area.area_name, "개롱역")
        self.assertEqual(area.district_code, "11710")


if __name__ == "__main__":
    unittest.main()
