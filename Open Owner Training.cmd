@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" ".local\pilots\owner_20261122\open_training.py"
if errorlevel 1 pause
