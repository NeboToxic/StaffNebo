@echo off
setlocal
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm StaffControl.spec
if errorlevel 1 pause & exit /b 1
echo.
echo READY: dist\StaffControl.exe
pause
