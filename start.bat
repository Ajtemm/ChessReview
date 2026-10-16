@echo off
rem Pokrece Chess Review server i otvara aplikaciju u browseru.
rem Gasenje: Ctrl+C u ovom prozoru (ili zatvori prozor).

rem Radimo iz foldera u kome je ovaj fajl, odakle god da je pokrenut
cd /d "%~dp0"
title Chess Review

if not exist ".venv\Scripts\python.exe" (
    echo Nije pronadjeno virtuelno okruzenje .venv.
    echo Napravi ga komandama:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Chess Review radi na http://localhost:8000
echo Za gasenje pritisni Ctrl+C ili zatvori ovaj prozor.
echo.

rem Browser otvaramo posle ~3 s, kad server vec radi
start "" /b cmd /c "ping -n 4 127.0.0.1 >nul & explorer http://localhost:8000"

".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000

rem Ako se server ugasi zbog greske, prozor ostaje otvoren da se vidi poruka
pause
