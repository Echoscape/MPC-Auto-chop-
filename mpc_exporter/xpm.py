from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


def write_xpm(
    output_path: Path,
    program_name: str,
    sample_paths: Sequence[str],
    sample_names: Sequence[str],
    sample_ends: Sequence[int],
) -> None:
    if len(sample_paths) != len(sample_names):
        raise ValueError("Sample paths and names must have matching lengths.")
    if len(sample_paths) != len(sample_ends):
        raise ValueError("Sample paths and end points must have matching lengths.")
    if not sample_paths or len(sample_paths) > 64:
        raise ValueError("An MPC program must contain between 1 and 64 samples.")

    root = ET.Element("MPCVObject")
    version = ET.SubElement(root, "Version")
    _text(version, "File_Version", "2.1")
    _text(version, "Application", "MPC-V")
    _text(version, "Application_Version", "3.0.0.0")
    _text(version, "Platform", "Windows")

    program = ET.SubElement(root, "Program", {"type": "Drum"})
    _text(program, "ProgramName", program_name)
    pad_data = {
        "ProgramPads": {
            "Universal": {"value0": True},
            "Type": {"value0": 1},
            "universalPad": 32512,
            "pads": {f"value{index}": 0 for index in range(128)},
            "UnusedPads": {"value0": 1},
        }
    }
    _text(program, "ProgramPads", json.dumps(pad_data, indent=2))
    _text(program, "CueBusEnable", "False")
    audio_route = ET.SubElement(program, "AudioRoute")
    _text(audio_route, "AudioRoute", "2")
    _text(audio_route, "AudioRouteSubIndex", "0")
    _text(audio_route, "AudioRouteChannelBitmap", "3")
    _text(audio_route, "InsertsEnabled", "True")
    for index in range(1, 5):
        _text(program, f"Send{index}", "0.000000")
    _text(program, "Volume", "0.710000")
    _text(program, "Mute", "False")
    _text(program, "Solo", "False")
    _text(program, "Pan", "0.500000")
    _text(program, "AutomationFilter", "1")
    _text(program, "Pitch", "0.000000")
    _text(program, "TuneCoarse", "0")
    _text(program, "TuneFine", "0")
    _text(program, "Mono", "False")
    _text(program, "Program_Polyphony", "16")
    _text(program, "PortamentoTime", "0.000000")
    _text(program, "PortamentoLegato", "False")
    _text(program, "PortamentoQuantized", "False")
    _text(program, "Program.Xfader.Route", "0")

    instruments = ET.SubElement(program, "Instruments")
    for pad_index in range(128):
        instrument = ET.SubElement(instruments, "Instrument", {"number": str(pad_index)})
        _add_instrument_defaults(instrument)
        layers = ET.SubElement(instrument, "Layers")
        active = pad_index < len(sample_paths)
        for layer_index in range(4):
            layer = ET.SubElement(layers, "Layer", {"number": str(layer_index + 1)})
            _add_layer_defaults(
                layer,
                active and layer_index == 0,
                sample_names[pad_index] if active and layer_index == 0 else "",
                sample_paths[pad_index] if active and layer_index == 0 else "",
                sample_ends[pad_index] if active and layer_index == 0 else 0,
            )

    ET.indent(root, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output_path, encoding="UTF-8", xml_declaration=True)


def _add_instrument_defaults(instrument: ET.Element) -> None:
    _text(instrument, "CueBusEnable", "False")
    route = ET.SubElement(instrument, "AudioRoute")
    _text(route, "AudioRoute", "0")
    _text(route, "AudioRouteSubIndex", "0")
    _text(route, "AudioRouteChannelBitmap", "3")
    _text(route, "InsertsEnabled", "True")
    for index in range(1, 5):
        _text(instrument, f"Send{index}", "0.000000")
    values = (
        ("Volume", "0.707946"),
        ("Mute", "False"),
        ("Solo", "False"),
        ("Pan", "0.500000"),
        ("AutomationFilter", "1"),
        ("TuneCoarse", "0"),
        ("TuneFine", "0"),
        ("Mono", "True"),
        ("Polyphony", "1"),
        ("FilterKeytrack", "0.000000"),
        ("LowNote", "0"),
        ("HighNote", "127"),
        ("IgnoreBaseNote", "False"),
        ("ZonePlay", "1"),
        ("MuteGroup", "0"),
        ("MuteTarget1", "0"),
        ("MuteTarget2", "0"),
        ("MuteTarget3", "0"),
        ("MuteTarget4", "0"),
        ("SimultTarget1", "0"),
        ("SimultTarget2", "0"),
        ("SimultTarget3", "0"),
        ("SimultTarget4", "0"),
        ("LfoPitch", "0.000000"),
        ("LfoCutoff", "0.000000"),
        ("LfoVolume", "0.000000"),
        ("LfoPan", "0.000000"),
        ("OneShot", "True"),
        ("FilterType", "2"),
        ("Cutoff", "1.000000"),
        ("Resonance", "0.000000"),
        ("FilterEnvAmt", "0.000000"),
        ("AfterTouchToFilter", "0.000000"),
        ("VelocityToStart", "0.000000"),
        ("VelocityToFilterAttack", "0.000000"),
        ("VelocityToFilter", "0.000000"),
        ("VelocityToFilterEnvelope", "0.000000"),
        ("FilterAttack", "0.000000"),
        ("FilterDecay", "0.047244"),
        ("FilterSustain", "1.000000"),
        ("FilterRelease", "0.000000"),
        ("FilterHold", "0.000000"),
        ("FilterDecayType", "True"),
        ("FilterADEnvelope", "True"),
        ("VolumeHold", "0.000000"),
        ("VolumeDecayType", "True"),
        ("VolumeADEnvelope", "True"),
        ("VolumeAttack", "0.000000"),
        ("VolumeDecay", "0.047244"),
        ("VolumeSustain", "1.000000"),
        ("VolumeRelease", "0.000000"),
        ("VelocityToPitch", "0.000000"),
        ("VelocityToVolumeAttack", "0.000000"),
        ("VelocitySensitivity", "1.000000"),
        ("VelocityToPan", "0.000000"),
    )
    for tag, value in values:
        _text(instrument, tag, value)
    lfo = ET.SubElement(instrument, "LFO")
    _text(lfo, "Type", "Sine")
    _text(lfo, "Rate", "0.500000")
    _text(lfo, "Sync", "0")
    _text(lfo, "Reset", "False")
    _text(instrument, "WarpTempo", "120.000000")
    _text(instrument, "BpmLock", "True")
    _text(instrument, "WarpEnable", "False")
    _text(instrument, "StretchPercentage", "100")


def _add_layer_defaults(
    layer: ET.Element,
    active: bool,
    sample_name: str,
    sample_path: str,
    sample_end: int,
) -> None:
    values = (
        ("Active", str(active)),
        ("Volume", "1.000000"),
        ("Pan", "0.500000"),
        ("Pitch", "0.000000"),
        ("TuneCoarse", "0"),
        ("TuneFine", "0"),
        ("VelStart", "0"),
        ("VelEnd", "127"),
        ("SampleStart", "0"),
        ("SampleEnd", str(sample_end)),
        ("Loop", "False"),
        ("LoopStart", "0"),
        ("LoopEnd", "0"),
        ("LoopCrossfadeLength", "0"),
        ("LoopTune", "0"),
        ("Mute", "False"),
        ("RootNote", "0"),
        ("KeyTrack", "False"),
        ("SampleName", sample_name),
        ("SampleFile", sample_path),
        ("SliceIndex", "129"),
        ("Direction", "0"),
        ("Offset", "0"),
        ("SliceStart", "0"),
        ("SliceEnd", "0"),
        ("SliceLoopStart", "0"),
        ("SliceLoop", "0"),
        ("SliceLoopCrossFadeLength", "0"),
    )
    for tag, value in values:
        _text(layer, tag, value)


def _text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = value
    return node
