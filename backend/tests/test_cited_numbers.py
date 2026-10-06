import unittest

from app.evidence import CitationError, render_cited

SOURCES = {
    "commercial_area": {"by_middle": [{"code": "I201", "count": 1234, "lq": 1.24}]},
    "floating_population": {
        "age_share": {"age_20": 0.31, "10": 0.05},
        "time_share": {"11_14": 0.2},
        "flag": True,
    },
}
COUNT = ("commercial_area", "/by_middle/0/count")
LQ = ("commercial_area", "/by_middle/0/lq")


class CitedNumberTests(unittest.TestCase):
    def reason(self, text, refs):
        with self.assertRaises(CitationError) as caught:
            render_cited(text, refs, SOURCES)
        return caught.exception.reason

    def test_values_are_filled_from_source(self):
        self.assertEqual(
            render_cited("점포 {0}개, 주변 대비 {1}배", [COUNT, LQ], SOURCES),
            "점포 1,234개, 주변 대비 1.24배",
        )

    def test_text_without_numbers_is_unchanged(self):
        self.assertEqual(render_cited("경쟁이 적습니다.", [], SOURCES), "경쟁이 적습니다.")

    def test_bare_number_is_rejected(self):
        self.assertEqual(self.reason("점포 1234개", [COUNT]), "number_uncited")

    def test_array_index_digits_are_not_a_free_pass(self):
        self.assertEqual(self.reason("{0}개 중 0번째", [COUNT]), "number_uncited")

    def test_segment_label_digits_are_allowed(self):
        self.assertEqual(
            render_cited("20대 비중 {0}", [("floating_population", "/age_share/age_20")], SOURCES),
            "20대 비중 0.31",
        )

    def test_numeric_dict_keys_are_labels_but_list_indexes_are_not(self):
        self.assertEqual(
            render_cited("10대 비중 {0}", [("floating_population", "/age_share/10")], SOURCES),
            "10대 비중 0.05",
        )
        self.assertEqual(
            render_cited(
                "11~14시 비중 {0}", [("floating_population", "/time_share/11_14")], SOURCES
            ),
            "11~14시 비중 0.2",
        )

    def test_out_of_range_placeholder(self):
        self.assertEqual(self.reason("{1}개", [COUNT]), "placeholder_out_of_range")

    def test_non_scalar_or_bool_value(self):
        self.assertEqual(
            self.reason("{0}", [("floating_population", "/flag")]), "placeholder_value_invalid"
        )
        self.assertEqual(
            self.reason("{0}", [("commercial_area", "/by_middle/0")]), "placeholder_value_invalid"
        )

    def test_unit_must_fit_the_path(self):
        self.assertEqual(self.reason("{0}명", [COUNT]), "unit_mismatch")
        self.assertEqual(self.reason("{0}만 개", [COUNT]), "unit_mismatch")


class PopulationUnitTests(unittest.TestCase):
    def test_quarter_totals_and_area_counts_have_units(self):
        from app.mocks import mock_floating_population_data

        sources = {"floating_population": mock_floating_population_data()}
        for text, path in (
            ("20대 유동인구 {0}명", "/population/by_age/20"),
            ("월요일 유동인구 {0}명", "/population/by_day/mon"),
            ("반경 안 상권 {0}개", "/radius_profile/points/0/trade_area_count"),
            ("반경 안 유동인구 {0}명", "/radius_profile/points/0/total"),
        ):
            with self.subTest(path=path):
                rendered = render_cited(text, [("floating_population", path)], sources)
                self.assertNotIn("{", rendered)
        with self.assertRaises(CitationError):
            render_cited(
                "20대 비중 {0}명", [("floating_population", "/population/age_share/20")], sources
            )


if __name__ == "__main__":
    unittest.main()
