@echo off
rem SmartDent - one-click start for Windows. Double-click this file.
rem First run: creates .venv, installs the packages (needs internet, about 1 GB, 5-15 minutes),
rem creates the database with demo logins, then opens SmartDent in your browser.
rem Later runs start in a few seconds and work offline.

setlocal
cd /d "%~dp0"
title SmartDent
echo.
echo   SmartDent - AI assistant for panoramic dental X-rays
echo   ----------------------------------------------------
echo.

rem 1. Find Python 3.10 or newer (tested versions first).
set "PY="
for %%V in (3.13 3.12 3.11 3.10 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo   Python 3.10 or newer was not found.
  echo   Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^),
  echo   then double-click start.bat again.
  goto :fail
)

rem 2. Create the private Python environment (.venv) the first time.
if not exist ".venv\Scripts\python.exe" (
  echo   [1/4] Creating the Python environment with: %PY%
  %PY% -m venv .venv || goto :fail
) else (
  echo   [1/4] Python environment found.
)
".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo   The .venv folder is broken ^(perhaps copied from another computer^).
  echo   Delete the .venv folder and double-click start.bat again.
  goto :fail
)

rem 3. Install the packages, only when requirements.txt changed since the last install.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  echo   [2/4] Installing packages. The first time this downloads about 1 GB and can take 5-15 minutes...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check || goto :pipfail
  copy /y requirements.txt ".venv\requirements.installed" >nul
) else (
  echo   [2/4] Packages already installed.
)

rem 4. Create the database, with demo logins if it is empty.
echo   [3/4] Preparing the database...
".venv\Scripts\python.exe" scripts\seed.py --demo || goto :fail

rem 5. Start SmartDent and open it in the browser.
echo   [4/4] Starting SmartDent. Demo logins are in README.md.
".venv\Scripts\python.exe" run.py --open
goto :end

:pipfail
echo.
echo   Installing the packages failed. Check the internet connection and run start.bat again.
echo   If it still fails, see "Troubleshooting" in README.md.
:fail
echo.
pause
exit /b 1

:end
echo.
echo   SmartDent has stopped.
pause
