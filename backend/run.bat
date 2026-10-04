@echo off
call venv\Scripts\activate.bat
echo Server: http://localhost:8000/api/health
echo Docs:   http://localhost:8000/docs
uvicorn app.main:app --reload --port 8000
pause
