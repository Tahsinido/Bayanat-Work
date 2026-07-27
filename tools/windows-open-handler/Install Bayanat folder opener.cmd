@echo off
REM Double-click this file to enable "Open" on local folder links in Bayanat.
REM No administrator rights are required - it only writes to your own account.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
