@echo off
rem PostETUI launcher for a source clone. Double-click, or type "postetui" after install.bat.
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo PostETUI is not set up yet. Double-click install.bat first.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m postetui %*
