@echo off
REM NOI Social Command Center - Startup Script (Windows)

echo ==================================
echo NOI Social Command Center
echo ==================================
echo.

REM Check if .env exists
if not exist .env (
    echo WARNING: .env file not found!
    echo Creating from .env.example...
    copy .env.example .env
    echo Created .env file
    echo ERROR: Please edit .env with your API credentials before running.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing dependencies...
pip install -q -r requirements.txt

echo.
echo Setup complete!
echo.
echo Starting application...
echo.
echo Dashboard will be available at: http://localhost:8000
echo Press Ctrl+C to stop
echo.

REM Run the application
python main.py