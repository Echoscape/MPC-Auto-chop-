from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import imageio_ffmpeg
import librosa
import numpy as np

from .audio import AudioAnalysis, boundaries_for_method, analyze_audio
from .xpm import write_xpm


METHOD_LABELS = {
    "beat-bar": "Beat-Bar",
    "onset": "Onset",
}
PAD_COUNTS = (32, 64)
SUPPORTED_EXTENSIONS = {".mp3", ".wav"}


@dataclass(frozen=True)
class ExportOptions:
    input_folder: Path
    output_folder: Path
    methods: tuple[str, ...]


@dataclass(frozen=True)
class ExportResult:
    song_count: int
    kit_count: int
    errors: tuple[tuple[str, str], ...]
    output_folder: Path
    zip_paths: tuple[Path, ...]


ProgressCallback = Callable[[str], None]


def find_audio_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError(f"Input folder does not exist: {folder}")
    return sorted(
        (
            path
            for path in folder.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: str(path).casefold(),
    )


def export_folder(
    options: ExportOptions, progress: ProgressCallback | None = None
) -> ExportResult:
    input_folder = options.input_folder.resolve()
    output_folder = options.output_folder.resolve()
    if not input_folder.is_dir():
        raise ValueError(f"Input folder does not exist: {input_folder}")
    if not options.methods or any(method not in METHOD_LABELS for method in options.methods):
        raise ValueError("Select at least one supported chop method.")
    if len(set(options.methods)) != len(options.methods):
        raise ValueError("Chop methods must not contain duplicates.")

    audio_files = find_audio_files(input_folder)
    if not audio_files:
        raise ValueError(f"No MP3 or WAV files were found in {input_folder}.")

    output_folder.mkdir(parents=True, exist_ok=True)
    success_count = 0
    kit_count = 0
    errors: list[tuple[str, str]] = []
    zip_paths: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="mpc_export_") as temporary:
        work_root = Path(temporary)
        used_names: set[str] = set()

        for index, audio_path in enumerate(audio_files, start=1):
            relative = audio_path.relative_to(input_folder)
            _notify(progress, f"Analyzing {index}/{len(audio_files)}: {relative}")
            source_wav: Path | None = None
            track_root: Path | None = None
            track_kit_count = 0
            track_manifest_rows: list[dict[str, str]] = []
            try:
                song_name = _unique_track_name(relative, used_names)
                track_root = work_root / song_name
                track_root.mkdir()
                analysis, duration, source_wav = _prepare_audio(audio_path, track_root)
                kits_root = track_root / "kits"
                for method in options.methods:
                    for pad_count in PAD_COUNTS:
                        method_boundaries = boundaries_for_method(
                            duration, pad_count, method, analysis
                        )
                        kit_dir = (
                            kits_root
                            / METHOD_LABELS[method]
                            / f"{pad_count}-pad"
                        )
                        sample_dir = kit_dir / "Samples"
                        sample_dir.mkdir(parents=True, exist_ok=True)
                        sample_paths: list[str] = []
                        sample_names: list[str] = []
                        sample_ends: list[int] = []
                        for pad_index in range(pad_count):
                            sample_filename = f"{song_name}_{pad_index + 1:02d}.wav"
                            sample_path = sample_dir / sample_filename
                            sample_end = _write_audio_slice(
                                source_wav,
                                sample_path,
                                method_boundaries[pad_index],
                                method_boundaries[pad_index + 1],
                            )
                            sample_paths.append(f"Samples/{sample_filename}")
                            sample_names.append(sample_path.stem)
                            sample_ends.append(sample_end)

                        program_name = f"{song_name} {pad_count} {METHOD_LABELS[method]}"
                        program_path = kit_dir / f"{song_name}_{pad_count}.xpm"
                        write_xpm(
                            program_path,
                            program_name,
                            sample_paths,
                            sample_names,
                            sample_ends,
                        )
                        track_manifest_rows.append(
                            _manifest_row(
                                relative,
                                analysis,
                                method,
                                pad_count,
                                program_path.relative_to(kits_root).as_posix(),
                            )
                        )
                        track_kit_count += 1

                _write_csv(
                    track_root / "metadata.csv",
                    ["source_file", "bpm", "key", "key_confidence", "analysis_notes"],
                    [_metadata_row(relative, analysis)],
                )
                _write_csv(
                    track_root / "manifest.csv",
                    [
                        "source_file",
                        "bpm",
                        "key",
                        "key_confidence",
                        "chop_method",
                        "pad_count",
                        "program_file",
                        "sample_count",
                    ],
                    track_manifest_rows,
                )
                (track_root / "README.txt").write_text(_readme(), encoding="utf-8")
                shutil.rmtree(source_wav.parent, ignore_errors=True)

                zip_path = _available_zip_path(output_folder, song_name)
                _create_track_zip(kits_root, track_root, zip_path)
                zip_paths.append(zip_path)
                success_count += 1
                kit_count += track_kit_count
                _notify(
                    progress,
                    f"Created {zip_path.name} for {relative} "
                    f"({format_bpm(analysis.bpm)} BPM, {analysis.key or 'Unknown'}).",
                )
            except Exception as error:
                if source_wav is not None:
                    shutil.rmtree(source_wav.parent, ignore_errors=True)
                if track_root is not None:
                    shutil.rmtree(track_root, ignore_errors=True)
                message = f"{type(error).__name__}: {error}"
                errors.append((str(relative), message))
                _notify(progress, f"Failed {relative}: {message}")

        if not success_count:
            details = "; ".join(f"{name}: {reason}" for name, reason in errors)
            raise RuntimeError(f"No audio files could be exported. {details}")

    _notify(progress, f"Created {len(zip_paths)} per-track ZIP files in {output_folder}.")
    return ExportResult(
        success_count,
        kit_count,
        tuple(errors),
        output_folder,
        tuple(zip_paths),
    )


def _prepare_audio(audio_path: Path, work_root: Path) -> tuple[AudioAnalysis, float, Path]:
    decoded_dir = Path(tempfile.mkdtemp(prefix="decoded_", dir=work_root))
    decoded_wav = decoded_dir / "decoded.wav"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(decoded_wav),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        reason = error.stderr.strip() or str(error)
        shutil.rmtree(decoded_dir, ignore_errors=True)
        raise RuntimeError(f"Could not decode audio: {reason}") from error
    try:
        with wave.open(str(decoded_wav), "rb") as decoded:
            sample_rate = decoded.getframerate()
            decoded_sample_rate = sample_rate
            channels = decoded.getnchannels()
            sample_width = decoded.getsampwidth()
            frame_count = decoded.getnframes()
            pcm = decoded.readframes(frame_count)
        if sample_width != 2:
            raise RuntimeError(f"Expected 16-bit decoded audio, got {sample_width * 8}-bit.")
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if sample_rate != 22_050:
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=22_050)
            sample_rate = 22_050
        analysis = analyze_audio(audio, sample_rate)
        duration = frame_count / decoded_sample_rate
        return analysis, duration, decoded_wav
    except Exception:
        shutil.rmtree(decoded_dir, ignore_errors=True)
        raise


def _write_audio_slice(
    source_wav: Path,
    output_path: Path,
    start: float,
    end: float,
) -> int:
    if end <= start:
        raise ValueError(f"Invalid slice boundaries: {start:.4f}s to {end:.4f}s.")
    with wave.open(str(source_wav), "rb") as source:
        sample_rate = source.getframerate()
        first_frame = round(start * sample_rate)
        last_frame = min(round(end * sample_rate), source.getnframes())
        if last_frame <= first_frame:
            raise ValueError("A chop was too short to contain an audio frame.")
        source.setpos(first_frame)
        audio = source.readframes(last_frame - first_frame)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as output:
            output.setparams(source.getparams())
            output.writeframes(audio)
        return last_frame - first_frame


def _unique_track_name(relative_path: Path, used_names: set[str]) -> str:
    components = [sanitize_name(part) for part in relative_path.with_suffix("").parts]
    base = "_".join(components) or "track"
    candidate = base
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate


def sanitize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = re.sub(r"\s+", "_", value)
    if not value or value in {".", ".."}:
        return "track"
    if value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }:
        value = f"_{value}"
    return value[:100]


def format_bpm(bpm: float | None) -> str:
    return f"{bpm:.1f}" if bpm is not None else "Unknown"


def _metadata_row(relative: Path, analysis: AudioAnalysis) -> dict[str, str]:
    return {
        "source_file": relative.as_posix(),
        "bpm": format_bpm(analysis.bpm),
        "key": analysis.key or "Unknown",
        "key_confidence": (
            f"{analysis.key_confidence:.3f}"
            if analysis.key_confidence is not None
            else "Unknown"
        ),
        "analysis_notes": " ".join(analysis.warnings),
    }


def _manifest_row(
    relative: Path,
    analysis: AudioAnalysis,
    method: str,
    pad_count: int,
    program_file: str,
) -> dict[str, str]:
    return {
        "source_file": relative.as_posix(),
        "bpm": format_bpm(analysis.bpm),
        "key": analysis.key or "Unknown",
        "key_confidence": (
            f"{analysis.key_confidence:.3f}"
            if analysis.key_confidence is not None
            else "Unknown"
        ),
        "chop_method": METHOD_LABELS[method],
        "pad_count": str(pad_count),
        "program_file": program_file,
        "sample_count": str(pad_count),
    }


def _available_zip_path(output_folder: Path, song_name: str) -> Path:
    candidate = output_folder / f"{song_name}.zip"
    suffix = 2
    while candidate.exists():
        candidate = output_folder / f"{song_name}_{suffix}.zip"
        suffix += 1
    return candidate


def _create_track_zip(kits_root: Path, track_root: Path, zip_path: Path) -> None:
    descriptor, temporary_zip_name = tempfile.mkstemp(
        prefix=f".{zip_path.stem}_", suffix=".tmp", dir=zip_path.parent
    )
    os.close(descriptor)
    temporary_zip = Path(temporary_zip_name)
    try:
        with zipfile.ZipFile(
            temporary_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            for path in sorted(kits_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(kits_root).as_posix())
            for path in sorted(track_root.iterdir()):
                if path.is_file():
                    archive.write(path, path.name)
        os.replace(temporary_zip, zip_path)
    finally:
        temporary_zip.unlink(missing_ok=True)


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _readme() -> str:
    return (
        "MPC Folder Chopper export\n"
        "=========================\n\n"
        "This ZIP contains the export for one input audio track. It has one folder\n"
        "per chop method and pad count. Open the matching\n"
        ".xpm drum program in MPC 3. Keep its adjacent Samples folder in place so\n"
        "the program can find its WAV chops. Samples are 44.1 kHz, stereo, 16-bit WAV.\n\n"
        "Beat-Bar chops are placed on detected beat positions. Onset chops are\n"
        "placed on detected audio onsets. Both methods create 32-pad and 64-pad\n"
        "programs. If analysis cannot detect enough boundaries, remaining chops\n"
        "are evenly spaced; details are listed in metadata.csv.\n\n"
        "metadata.csv contains this track's estimated BPM and musical key.\n"
        "manifest.csv lists the programs included in this ZIP.\n"
    )


def _notify(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)
