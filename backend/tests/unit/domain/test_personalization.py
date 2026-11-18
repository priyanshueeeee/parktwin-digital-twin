import unittest

from backend.app.services.personalization import apply_calibration, fit_bounded_residual_calibration


class PersonalizationTests(unittest.TestCase):
    def test_sparse_history_does_not_enable_personalization(self) -> None:
        result = fit_bounded_residual_calibration([0, 1], [20, 21], [22, 23])

        self.assertFalse(result.enabled)
        self.assertIn("INSUFFICIENT_PERSONALIZATION_HISTORY", result.warnings)

    def test_calibration_is_bounded_and_applied(self) -> None:
        result = fit_bounded_residual_calibration(
            [0, 10, 20],
            [20, 21, 22],
            [30, 31, 32],
            max_abs_intercept=2,
        )
        adjusted = apply_calibration([20, 21], [0, 10], result)

        self.assertTrue(result.enabled)
        self.assertEqual(result.intercept_adjustment, 2)
        self.assertEqual(adjusted, (22.0, 23.0))


if __name__ == "__main__":
    unittest.main()
