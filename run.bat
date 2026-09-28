@echo off
cd /d "%~dp0"
if not exist .venv (py -3 -m venv .venv || python -m venv .venv)
echo Installing libraries, the first run takes a few minutes...
.venv\Scripts\python -m pip install --disable-pip-version-check --prefer-binary -r requirements.txt || (pause & exit /b 1)
.venv\Scripts\python desktop.py
