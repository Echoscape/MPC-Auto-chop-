import io
import tempfile
import wave
import zipfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mpc_exporter.audio import AudioAnalysis
from mpc_exporter.exporter import ExportOptions, export_folder


class PerTrackZipTests(unittest.TestCase):
    def test_exports_one_zip_per_track_and_continues_after_decode_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            (source / "first").mkdir(parents=True)
            (source / "second").mkdir()
            (source / "third").mkdir()
            for relative in (
                Path("first/song.wav"),
                Path("second/song.wav"),
                Path("third/song.wav"),
            ):
                (source / relative).write_bytes(b"input placeholder")

            def prepare_audio(audio_path: Path, work_root: Path):
                if audio_path.parent.name == "first":
                    raise RuntimeError("simulated decoder failure")
                decoded_dir = work_root / f"decoded_{audio_path.parent.name}"
                decoded_dir.mkdir()
                decoded_wav = decoded_dir / "decoded.wav"
                sample_rate = 44_100
                pcm = np.zeros(sample_rate * 4 * 2, dtype="<i2").tobytes()
                with wave.open(str(decoded_wav), "wb") as output:
                    output.setnchannels(2)
                    output.setsampwidth(2)
                    output.setframerate(sample_rate)
                    output.writeframes(pcm)
                analysis = AudioAnalysis(
                    bpm=120.0,
                    key="C major",
                    key_confidence=0.2,
                    beat_times=(1.0, 2.0, 3.0),
                    onset_times=(0.5, 1.5, 2.5),
                    warnings=(),
                )
                return analysis, 4.0, decoded_wav

            output_folder = root / "per-track-zips"
            options = ExportOptions(
                input_folder=source,
                output_folder=output_folder,
                methods=("beat-bar", "onset"),
            )
            with patch("mpc_exporter.exporter._prepare_audio", side_effect=prepare_audio):
                result = export_folder(options)

            self.assertEqual(result.song_count, 2)
            self.assertEqual(result.kit_count, 8)
            self.assertEqual(len(result.errors), 1)
            self.assertEqual(len(result.zip_paths), 2)
            self.assertEqual(
                {path.name for path in result.zip_paths},
                {"second_song.zip", "third_song.zip"},
            )
            for zip_path in result.zip_paths:
                with zipfile.ZipFile(zip_path) as archive:
                    files = archive.namelist()
                    self.assertIn("metadata.csv", files)
                    self.assertIn("manifest.csv", files)
                    self.assertEqual(
                        len([name for name in files if name.endswith(".xpm")]), 4
                    )
                    self.assertEqual(
                        len([name for name in files if name.endswith(".wav")]), 192
                    )
                    self.assertTrue(
                        any(name.startswith("Beat-Bar/32-pad/") for name in files)
                    )
                    for xpm_path in (name for name in files if name.endswith(".xpm")):
                        program = ET.fromstring(archive.read(xpm_path))
                        layers = program.findall(
                            "./Program/Instruments/Instrument/Layers/Layer"
                        )
                        for layer in layers:
                            if layer.findtext("Active") != "True":
                                continue
                            sample_path = (
                                f"{xpm_path.rsplit('/', 1)[0]}/"
                                f"{layer.findtext('SampleFile')}"
                            )
                            with wave.open(
                                io.BytesIO(archive.read(sample_path)), "rb"
                            ) as sample:
                                self.assertEqual(
                                    layer.findtext("SampleEnd"),
                                    str(sample.getnframes()),
                                )


if __name__ == "__main__":
    unittest.main()
