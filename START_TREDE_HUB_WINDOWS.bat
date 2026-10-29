@echo on
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is required. Install Python 3.8+ from python.org and enable Add Python to PATH.
  pause
  exit /b 1
)
python -c "import imageio_ffmpeg" >nul 2>nul
if errorlevel 1 (
  echo Installing the video compression dependency...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Could not install the video compression dependency. Check your internet connection and try again.
    pause
    exit /b 1
  )
)
python server.py
pause
