@echo off
echo ============================================
echo  Annotic Automator - Setup and Run
echo ============================================
echo.

echo Installing dependencies...
pip install playwright openai-whisper librosa soundfile numpy
playwright install chromium

echo.
echo Running automator...
python annotic_automator.py

echo.
echo Done.
pause
