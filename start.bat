@echo off
echo Starting Geoid Converter...

REM Start backend
start "Backend" cmd /c "cd backend && pip install -r requirements.txt && python main.py"

REM Wait for backend to start
timeout /t 5

REM Start frontend
start "Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Press any key to stop servers...
pause
