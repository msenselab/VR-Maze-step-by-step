@echo off
REM Setup virtual environment on Windows

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo Creating virtual environment...
uv venv .venv

echo Installing dependencies...
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

echo.
echo Done! Activate with:  .venv\Scripts\activate
