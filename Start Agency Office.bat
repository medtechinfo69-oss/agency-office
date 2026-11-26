@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1 || (
  echo Python is not available in PATH.
  echo Install Python 3 and enable "Add Python to PATH", then run this file again.
  pause
  exit /b 1
)

where npm >nul 2>&1 || (
  echo Node.js and npm are not available in PATH.
  echo Install Node.js, then run this file again.
  pause
  exit /b 1
)

if not exist .env if exist .env.example copy /Y .env.example .env >nul

set "PYTHON=%CD%\backend\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Creating backend environment...
  python -m venv backend\.venv || (
    echo Could not create the Python environment.
    pause
    exit /b 1
  )
)

"%PYTHON%" -c "import fastapi,uvicorn,httpx,dotenv" >nul 2>&1
if errorlevel 1 (
  echo Installing backend dependencies...
  "%PYTHON%" -m pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo Could not install backend dependencies.
    pause
    exit /b 1
  )
)

if not exist frontend\node_modules (
  echo Installing frontend dependencies...
  pushd frontend
  call npm install --no-audit --no-fund
  popd
  if errorlevel 1 (
    echo Could not install frontend dependencies.
    pause
    exit /b 1
  )
)

echo Starting Agency Office...
start "Agency Office Backend" /D "%CD%\backend" "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
start "Agency Office Frontend" /D "%CD%\frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"

powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i=0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173' -TimeoutSec 1 | Out-Null; Start-Process 'http://localhost:5173'; exit 0 } catch {} Start-Sleep -Milliseconds 500 }; Write-Host 'The app did not start in time. Check the two service windows.'"

endlocal
