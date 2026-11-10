@echo off
rem Double-click once after downloading: installs everything and creates the
rem "Subtitle Maker" shortcut in this folder. Safe to run again (e.g. after updating).
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv is not installed. It installs Python and the packages this app needs.
  echo Install it with this command, then open a NEW terminal and run setup.cmd again:
  echo.
  echo     winget install --id=astral-sh.uv -e
  echo.
  pause
  exit /b 1
)

where nvidia-smi >nul 2>nul
if errorlevel 1 (
  echo Note: no NVIDIA graphics card driver found. Subtitle Maker will still work,
  echo but on the processor, which is much slower.
  echo.
)

echo Installing the packages this app needs. The first time downloads about 1.5 GB...
uv sync
if errorlevel 1 (
  echo.
  echo Install failed: see the message above.
  pause
  exit /b 1
)

set "LNK=%~dp0Subtitle Maker.lnk"
set "TARGET=%~dp0.venv\Scripts\pythonw.exe"
set "ARGS=app.py"
set "WD=%~dp0."
set "ICON=%~dp0assets\icon.ico,0"
powershell -NoProfile -NonInteractive -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=$env:TARGET; $s.Arguments=$env:ARGS; $s.WorkingDirectory=$env:WD; $s.IconLocation=$env:ICON; $s.Save()"

echo.
echo Done. Double-click "Subtitle Maker" in this folder to start.
echo The first video downloads the speech model once (about 3 GB).
pause
