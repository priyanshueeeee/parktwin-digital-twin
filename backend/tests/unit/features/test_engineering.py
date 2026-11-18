import unittest

from ml.data.schema import FEATURE_SPECS
from ml.features.engineering import build_feature_vector


class FeatureEngineeringTests(unittest.TestCase):
    def test_derived_features_are_deterministic_and_non_mutating(self) -> None:
        row = {spec.source_name: 0.1 for spec in FEATURE_SPECS}
        original = dict(row)

        first = build_feature_vector(row)
        second = build_feature_vector(row)

        self.assertEqual(first.features, second.features)
        self.assertEqual(row, original)
        self.assertIn("jitter_family_mean", first.features)
        self.assertIn("harmonicity_ratio", first.features)
        self.assertIn("DERIVED_FEATURES_INCLUDED", first.quality_flags)

    def test_feature_vector_can_return_only_raw_features(self) -> None:
        row = {spec.source_name: 0.1 for spec in FEATURE_SPECS}

        vector = build_feature_vector(row, include_derived=False)

        self.assertEqual(set(vector.features), {spec.canonical_name for spec in FEATURE_SPECS})
        self.assertEqual(vector.quality_flags, ())

    def test_missing_feature_fails_clearly(self) -> None:
        row = {spec.source_name: 0.1 for spec in FEATURE_SPECS[:-1]}

        with self.assertRaisesRegex(ValueError, "ppe"):
            build_feature_vector(row)


if __name__ == "__main__":
    unittest.main()
