@echo off
:: Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
::
:: Launch the Knowledge Slot Curation Tool GUI
:: Opens at http://localhost:8400

echo.
echo   Knowledge Slot Curation Tool
echo   ============================
echo   Starting server...
echo.

cd /d "%~dp0"
start "" http://localhost:8400
.venv\Scripts\python.exe server.py
