@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" ".local\pilots\owner_20261122\open_training_lan.py"
if errorlevel 1 pause
