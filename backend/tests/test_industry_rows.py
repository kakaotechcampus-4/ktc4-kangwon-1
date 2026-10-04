import unittest

from pydantic import ValidationError

from app.agents.commercial_area.schemas import MiddleCategory
from app.industries import lookup


def middle_row(code="I201", name=None):
    industry = lookup.get(code)
    return {
        "code": code,
        "name": name or industry.name,
        "major_code": industry.major_code,
        "major_name": industry.major_name,
        "count": 3,
        "share": 0.1,
        "density_per_km2": 1.0,
        "diff_type_count": 1,
        "jacobian": 0.5,
        "major_cluster_count": 2,
        "major_cluster_diversity": 0.3,
    }


class IndustryRowTests(unittest.TestCase):
    def test_known_row_reports_owner(self):
        self.assertEqual(MiddleCategory.model_validate(middle_row()).owner_code, "I201")

    def test_unknown_code_is_rejected(self):
        row = middle_row()
        row["code"] = "Z999"
        with self.assertRaises(ValidationError):
            MiddleCategory.model_validate(row)

    def test_name_must_match_code(self):
        with self.assertRaises(ValidationError):
            MiddleCategory.model_validate(middle_row(name=lookup.get("I212").name))


if __name__ == "__main__":
    unittest.main()
