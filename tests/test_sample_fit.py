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


if __name__ == "__main__":
    unittest.main()
