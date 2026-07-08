@echo off
title FitVision AI Backend
cd /d "%~dp0"

echo [1/2] Starting PostgreSQL Database via Docker...
docker-compose up -d

echo [2/2] Starting FastAPI Server...
call venv\Scripts\activate.bat
python main.py

pause
