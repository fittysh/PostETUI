@echo off
rem PostETUI installer. Works from an extracted release zip or a source clone.
rem See install.ps1 for what it does. No admin rights needed.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
