@echo off
setlocal

py -3.11 -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

pyinstaller --noconfirm --clean --windowed --name MPCFolderChopper ^
  --collect-all librosa ^
  --collect-all scipy ^
  --collect-all imageio_ffmpeg ^
  main.py
if errorlevel 1 exit /b 1

echo Built dist\MPCFolderChopper\MPCFolderChopper.exe
