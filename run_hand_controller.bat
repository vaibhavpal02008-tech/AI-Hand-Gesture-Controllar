@echo off
setlocal
cd /d "%~dp0"

call "%~dp0setup_hand_controller.bat"
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" hand_pc_controller.py
if errorlevel 1 pause
exit /b %errorlevel%

