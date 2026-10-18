# MPC Folder Chopper

MPC Folder Chopper is a Windows desktop app for batch-analyzing MP3/WAV files
and exporting chopped samples with Akai MPC 3 drum-program (`.xpm`) files.

## What it exports

- Beat/bar-aligned chops, onset-detected chops, or both.
- A 32-pad and a 64-pad program for every selected chop method and input song.
- Chopped 44.1 kHz, stereo, 16-bit WAV files referenced by each MPC program.
- One ZIP per successfully processed audio track. Each ZIP contains that
  track's MPC programs, samples, `metadata.csv`, `manifest.csv`, and instructions.
- MP3 and WAV files found in the selected folder and its subfolders.

Beat/bar boundaries are selected from detected beats near evenly spaced target
points. Onset boundaries are selected from detected audio onsets. If detection
does not return usable candidates, the app uses even boundaries and reports
that fallback in `metadata.csv`. BPM and key are estimates, not guaranteed
ground truth.

## Build the Windows executable

Build on Windows (the build script uses Python 3.11):

1. Install Python 3.11 from python.org and enable the Python launcher.
2. Run `build_windows.bat`.
3. The executable is created at `dist\MPCFolderChopper\MPCFolderChopper.exe`.

The first build downloads the Python dependencies. Build on Windows rather than
trying to cross-compile the executable from Linux or macOS.

## Run from source

With Python 3.11:

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

## Use the export in MPC 3

The app creates an `MPC_Exports` folder by default. It contains one ZIP per
source track. Extract a track ZIP; it contains method folders and `32-pad` and
`64-pad` kit folders. Open/import the `.xpm` program in MPC 3 and keep its
adjacent `Samples` folder in place so the program can locate the WAV files.
