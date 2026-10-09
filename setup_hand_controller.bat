@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 goto python_missing
)

".venv\Scripts\python.exe" -c "import cv2, mediapipe, pyautogui" >nul 2>&1
if not errorlevel 1 exit /b 0

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed
exit /b 0

:python_missing
echo Python 3.11 (64-bit) was not found. Install it, then run this file again.
exit /b 1

:install_failed
echo Dependency installation failed. Check your internet connection and Python 3.11 installation.
cursser ke speed thode fast kr do  1.75 
exit /b 1