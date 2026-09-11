@echo off
REM Windows exe build entry point. Actual build logic (with Korean text) lives
REM in build_windows.ps1 - PowerShell handles Unicode correctly regardless of
REM console codepage, which plain batch files here did not.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
pause
