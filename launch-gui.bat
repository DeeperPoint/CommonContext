@echo off
:: Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
::
:: Launch the CommonContext GUI
:: Opens at http://localhost:8400

echo.
echo   CommonContext
echo   ============================
echo   Starting server...
echo.

cd /d "%~dp0"
start "" http://localhost:8400
.venv\Scripts\python.exe server.py
