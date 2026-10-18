from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import librosa
import numpy as np


SAMPLE_RATE = 22_050
KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)


@dataclass(frozen=True)
class AudioAnalysis:
    bpm: float | None
    key: str | None
    key_confidence: float | None
    beat_times: tuple[float, ...]
    onset_times: tuple[float, ...]
    warnings: tuple[str, ...]


def analyze_audio(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> AudioAnalysis:
    if samples.size == 0:
        raise ValueError("The decoded audio track is empty.")

    warnings: list[str] = []
    if float(np.max(np.abs(samples))) < 1e-6:
        return AudioAnalysis(
            bpm=None,
            key=None,
            key_confidence=None,
            beat_times=(),
            onset_times=(),
            warnings=("Audio is silent; BPM and key could not be estimated.",),
        )

    tempo, beat_times_array = librosa.beat.beat_track(
        y=samples, sr=sample_rate, units="time", trim=False
    )
    tempo_values = np.asarray(tempo).reshape(-1)
    bpm = float(tempo_values[0]) if tempo_values.size else 0.0
    if not np.isfinite(bpm) or bpm <= 0:
        bpm = None
        warnings.append("BPM could not be estimated.")

    onset_times_array = librosa.onset.onset_detect(
        y=samples, sr=sample_rate, units="time", backtrack=False
    )
    beat_times = tuple(float(value) for value in beat_times_array if np.isfinite(value))
    onset_times = tuple(float(value) for value in onset_times_array if np.isfinite(value))
    if not beat_times:
        warnings.append("No beats detected; beat/bar chops will use even boundaries.")
    if not onset_times:
        warnings.append("No onsets detected; onset chops will use even boundaries.")

    chroma = librosa.feature.chroma_stft(y=samples, sr=sample_rate)
    chroma_mean = np.mean(chroma, axis=1)
    key, confidence = _estimate_key(chroma_mean)
    if confidence < 0.015:
        warnings.append("Key estimate has low confidence.")

    return AudioAnalysis(
        bpm=bpm,
        key=key,
        key_confidence=confidence,
        beat_times=beat_times,
        onset_times=onset_times,
        warnings=tuple(warnings),
    )


def _estimate_key(chroma: np.ndarray) -> tuple[str, float]:
    if chroma.shape != (12,) or not np.all(np.isfinite(chroma)):
        return "Unknown", 0.0

    chroma = chroma - np.mean(chroma)
    chroma_norm = float(np.linalg.norm(chroma))
    if chroma_norm < 1e-12:
        return "Unknown", 0.0

    best_key = "Unknown"
    best_score = -1.0
    next_score = -1.0
    for tonic, name in enumerate(KEY_NAMES):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, tonic)
            rotated = rotated - np.mean(rotated)
            score = float(np.dot(chroma, rotated) / (chroma_norm * np.linalg.norm(rotated)))
            if score > best_score:
                next_score = best_score
                best_score = score
                best_key = f"{name} {mode}"
            elif score > next_score:
                next_score = score

    return best_key, max(0.0, best_score - next_score)


def choose_boundaries(
    duration: float,
    count: int,
    candidate_times: Sequence[float],
) -> list[float]:
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("Audio duration must be greater than zero.")
    if count < 1:
        raise ValueError("Pad count must be at least one.")

    if not candidate_times:
        return [duration * index / count for index in range(count + 1)]

    candidates = sorted(
        {
            float(time)
            for time in candidate_times
            if np.isfinite(time) and 0 < float(time) < duration
        }
    )
    if not candidates:
        return [duration * index / count for index in range(count + 1)]

    minimum_gap = min(0.04, duration / (count * 2))
    boundaries = [0.0]
    for index in range(1, count):
        target = duration * index / count
        lower = boundaries[-1] + minimum_gap
        upper = duration - (count - index) * minimum_gap
        viable = [time for time in candidates if lower <= time <= upper]
        chosen = min(viable, key=lambda time: abs(time - target)) if viable else target
        chosen = min(max(chosen, lower), upper)
        boundaries.append(chosen)
    boundaries.append(duration)
    return boundaries


def boundaries_for_method(
    duration: float, count: int, method: str, analysis: AudioAnalysis
) -> list[float]:
    if method == "beat-bar":
        candidates = analysis.beat_times
    elif method == "onset":
        candidates = analysis.onset_times
    else:
        raise ValueError(f"Unsupported chop method: {method}")
    return choose_boundaries(duration, count, candidates)
