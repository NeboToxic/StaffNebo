@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
python -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
python run_tests.py
if errorlevel 1 goto failed
python -m PyInstaller --clean --noconfirm NeboProject.spec
if errorlevel 1 goto failed
echo READY: dist\NeboProject.exe
pause
exit /b 0
:failed
echo BUILD FAILED
pause
exit /b 1
