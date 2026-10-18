import unittest

import numpy as np

from mpc_exporter.audio import AudioAnalysis, boundaries_for_method, choose_boundaries


class BoundaryTests(unittest.TestCase):
    def test_even_boundaries_have_requested_count_and_cover_duration(self):
        boundaries = choose_boundaries(12.0, 32, [])

        self.assertEqual(len(boundaries), 33)
        self.assertEqual(boundaries[0], 0.0)
        self.assertEqual(boundaries[-1], 12.0)
        self.assertTrue(all(left < right for left, right in zip(boundaries, boundaries[1:])))

    def test_candidate_boundaries_are_monotonic_and_keep_track_edges(self):
        boundaries = choose_boundaries(20.0, 8, [0.1, 2.3, 2.4, 5.1, 7.6, 10.0, 12.7, 15.1, 19.8])

        self.assertEqual(len(boundaries), 9)
        self.assertEqual(boundaries[0], 0.0)
        self.assertEqual(boundaries[-1], 20.0)
        self.assertTrue(all(left < right for left, right in zip(boundaries, boundaries[1:])))

    def test_method_selects_its_matching_detection_times(self):
        analysis = AudioAnalysis(
            bpm=120,
            key="C major",
            key_confidence=0.2,
            beat_times=(1.0, 2.0, 3.0),
            onset_times=(0.5, 1.5, 2.5),
            warnings=(),
        )

        beat_boundaries = boundaries_for_method(4.0, 2, "beat-bar", analysis)
        onset_boundaries = boundaries_for_method(4.0, 2, "onset", analysis)

        self.assertEqual(beat_boundaries[1], 2.0)
        self.assertEqual(onset_boundaries[1], 1.5)

    def test_silent_track_returns_unknown_analysis(self):
        from mpc_exporter.audio import analyze_audio

        analysis = analyze_audio(np.zeros(22_050, dtype=np.float32))

        self.assertIsNone(analysis.bpm)
        self.assertIsNone(analysis.key)
        self.assertTrue(analysis.warnings)


if __name__ == "__main__":
    unittest.main()
