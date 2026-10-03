@echo off
title Live Audio Subtitle Translator
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else (
    python run.py
)
if errorlevel 1 pause
popd
