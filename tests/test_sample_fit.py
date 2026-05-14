import math
import unittest

from openclaw_fit_skill.fit_summary import (
    parse_fit_file,
    render_text_summary,
    summarize_activity,
)


class TestSampleFitSummary(unittest.TestCase):
    def test_sample_fit_parses_and_summarizes(self) -> None:
        activity = parse_fit_file("sample.fit")
        summary = summarize_activity(activity, source_path="sample.fit")

        # Basic structure
        self.assertEqual(summary["source"], "sample.fit")
        self.assertEqual(summary["sport"], "running")
        self.assertEqual(summary["sub_sport"], "virtual_activity")

        # Sanity checks for parsed volume
        self.assertGreater(summary["record_count"], 1000)
        self.assertGreaterEqual(summary["lap_count"], 1)

        # Regression checks pinned to current sample.fit values
        self.assertTrue(math.isclose(summary["distance"]["meters"], 6347.53, rel_tol=0, abs_tol=0.01))
        self.assertTrue(math.isclose(summary["timing"]["moving_s"], 3933.953, rel_tol=0, abs_tol=0.01))
        self.assertEqual(summary["heart_rate"]["max_bpm"], 175)

        # Human-readable rendering should include key lines
        text = render_text_summary(summary)
        self.assertIn("Source: sample.fit", text)
        self.assertIn("Activity: running (virtual_activity)", text)
        self.assertIn("Distance:", text)
        self.assertIn("Heart Rate:", text)

    def test_sample_fit_detail_interval_metrics(self) -> None:
        activity = parse_fit_file("sample.fit")
        summary = summarize_activity(
            activity,
            source_path="sample.fit",
            detail_interval="10m",
        )

        coach_detail = summary["coach_detail"]
        self.assertEqual(coach_detail["interval"], "10m")
        self.assertEqual(coach_detail["interval_seconds"], 600)
        self.assertGreater(len(coach_detail["interval_metrics"]), 1)

        zones = coach_detail["heart_rate_zones"]
        self.assertIsNotNone(zones)
        self.assertIn("distribution", zones)
        self.assertEqual(zones["zone_scheme"], "50-60,60-70,70-80,80-90,90-100")

        splits = coach_detail["distance_splits_1km"]
        self.assertGreaterEqual(len(splits), 1)

    def test_sample_fit_custom_hr_zone_scheme(self) -> None:
        activity = parse_fit_file("sample.fit")
        summary = summarize_activity(
            activity,
            source_path="sample.fit",
            hr_zone_scheme="55-65,65-75,75-85,85-92,92-100",
        )
        zones = summary["coach_detail"]["heart_rate_zones"]
        self.assertIsNotNone(zones)
        self.assertEqual(zones["zone_scheme"], "55-65,65-75,75-85,85-92,92-100")
        distribution = zones["distribution"]
        self.assertIn("z1_55_65", distribution)
        self.assertIn("z5_92_100", distribution)

    def test_sample_fit_custom_bpm_hr_zone_scheme(self) -> None:
        activity = parse_fit_file("sample.fit")
        summary = summarize_activity(
            activity,
            source_path="sample.fit",
            hr_zone_scheme="105-124,124-143,143-162,162-175,175-190",
            hr_zone_mode="bpm",
        )
        zones = summary["coach_detail"]["heart_rate_zones"]
        self.assertIsNotNone(zones)
        self.assertEqual(zones["zone_mode"], "bpm")
        self.assertEqual(zones["zone_scheme"], "105-124,124-143,143-162,162-175,175-190")
        distribution = zones["distribution"]
        self.assertIn("z1_105_124", distribution)
        self.assertIn("z5_175_190", distribution)
        in_zone_samples = sum(
            distribution[name]["samples"]
            for name in ["z1_105_124", "z2_124_143", "z3_143_162", "z4_162_175", "z5_175_190"]
        )
        self.assertGreater(in_zone_samples, 0)


if __name__ == "__main__":
    unittest.main()
