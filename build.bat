@echo off
rem Builds dist\postetui.exe (PyInstaller one-file) and dist\PostETUI-win64.zip,
rem the asset the one-line installer downloads from GitHub Releases.
setlocal
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

rem textual loads its widgets lazily and rich loads unicode tables lazily,
rem so PyInstaller must be told to collect their submodules.
"%PY%" -m PyInstaller --noconfirm --clean --onefile --name postetui ^
    --collect-submodules textual --collect-data textual --collect-submodules rich ^
    --add-data "postetui\assets;postetui\assets" ^
    postetui\__main__.py
if errorlevel 1 exit /b 1

set "STAGE=dist\PostETUI"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%\scripts"
copy /y dist\postetui.exe "%STAGE%\" >nul
copy /y postetui\assets\catalog.yaml "%STAGE%\" >nul
copy /y install.bat "%STAGE%\" >nul
copy /y install.ps1 "%STAGE%\" >nul
copy /y README.md "%STAGE%\" >nul
copy /y OPERATOR_GUIDE.md "%STAGE%\" >nul
xcopy /e /i /q /y docs\img "%STAGE%\docs\img" >nul
if exist scripts\*.ps1 copy /y scripts\*.ps1 "%STAGE%\scripts\" >nul
if exist scripts\*.py copy /y scripts\*.py "%STAGE%\scripts\" >nul

powershell.exe -NoProfile -Command "Compress-Archive -Path 'dist\PostETUI\*' -DestinationPath 'dist\PostETUI-win64.zip' -Force"
if errorlevel 1 exit /b 1
echo.
echo Built dist\postetui.exe and dist\PostETUI-win64.zip
