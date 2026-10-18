import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from mpc_exporter.exporter import sanitize_name
from mpc_exporter.xpm import write_xpm


class XpmTests(unittest.TestCase):
    def test_xpm_references_samples_and_defines_all_pad_instruments(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "song.xpm"
            write_xpm(
                output,
                "A & B",
                ["Samples/song_01.wav", "Samples/song_02.wav"],
                ["song_01", "song_02"],
                [44100, 22050],
            )
            root = ET.parse(output).getroot()

        self.assertEqual(root.findtext("./Program/ProgramName"), "A & B")
        self.assertEqual(root.find("./Program").get("type"), "Drum")
        instruments = root.findall("./Program/Instruments/Instrument")
        self.assertEqual(len(instruments), 128)
        self.assertEqual(
            instruments[0].findtext("./Layers/Layer/SampleFile"), "Samples/song_01.wav"
        )
        self.assertEqual(
            instruments[1].findtext("./Layers/Layer/SampleName"), "song_02"
        )
        self.assertEqual(instruments[0].findtext("./Layers/Layer/SampleEnd"), "44100")
        self.assertEqual(instruments[1].findtext("./Layers/Layer/SampleEnd"), "22050")
        self.assertEqual(instruments[2].findtext("./Layers/Layer/SampleFile"), "")
        self.assertEqual(instruments[2].findtext("./Layers/Layer/SampleEnd"), "0")

    def test_xpm_rejects_mismatched_sample_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                write_xpm(Path(temporary) / "bad.xpm", "bad", ["a.wav"], [], [1])

    def test_windows_invalid_filename_characters_are_sanitized(self):
        self.assertEqual(sanitize_name("CON"), "_CON")
        self.assertEqual(sanitize_name("A/B?.wav"), "A_B_.wav")


if __name__ == "__main__":
    unittest.main()
