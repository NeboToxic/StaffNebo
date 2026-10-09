NeboProject 1.3.0 — Windows x64, Python 3.12
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-lock.txt -r requirements-build.txt
python run_tests.py
python -m PyInstaller --clean --noconfirm NeboProject.spec
python tools/package_release.py

Результат: dist/NeboProject.exe; release/*-Windows.zip, *-Source.zip, SHA256SUMS.txt.
Spec поддерживает пути с кириллицей.

Проверка GUI в PowerShell:
$env:QT_QPA_PLATFORM='offscreen'
$env:QT_QPA_FONTDIR='C:\Windows\Fonts'
$env:NEBO_DATA_DIR=Join-Path $env:TEMP ('nebo-smoke-'+[guid]::NewGuid())
python main.py --smoke-test

Та же проверка: dist/NeboProject.exe --smoke-test.
Отчёт smoke-result.txt и снимки находятся в NEBO_DATA_DIR.
Проверки не отправляют реальные сообщения.
