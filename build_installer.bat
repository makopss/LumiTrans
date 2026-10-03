@echo off
title LumiTrans Windows Installer Builder
pushd "%~dp0"

echo ========================================================
echo  LumiTrans 윈도우 설치 버전 (Setup.exe) 자동 빌드
echo ========================================================
echo.

set PY_EXE=python
if exist ".venv\Scripts\python.exe" set PY_EXE=".venv\Scripts\python.exe"

set TARGET_EDITION=%1
if not "%TARGET_EDITION%"=="" goto RUN_BUILD

echo [빌드 에디션을 선택해 주세요]
echo  1. 라이트 버전 빌드 (Lite, 약 190~220MB - STT/LLM 모델 첫 실행 시 다운로드)
echo  2. 풀 버전 빌드     (Full, 약 750~800MB - STT 모델 및 CUDA 12 가속 라이브러리 전체 내장)
echo  3. 둘 다 빌드       (Full 및 Lite 에디션 모두 생성) [기본값]
echo.
set /p CHOICE="선택 (1/2/3, 기본값: 3): "

if "%CHOICE%"=="1" (
    set TARGET_EDITION=--edition lite
) else if "%CHOICE%"=="2" (
    set TARGET_EDITION=--edition full
) else (
    set TARGET_EDITION=--edition all
)

:RUN_BUILD
echo.
%PY_EXE% scripts\build_windows_installer.py %TARGET_EDITION%

if errorlevel 1 (
    echo.
    echo [ERROR] 빌드 중 오류가 발생했습니다. 위 로그를 확인하세요.
    pause
    popd
    exit /b 1
)

echo.
echo [SUCCESS] 빌드가 성공적으로 완료되었습니다!
pause
popd
