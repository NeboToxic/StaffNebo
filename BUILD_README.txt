СБОРКА NEBOPROJECT

Вариант 1 — Windows:
1. Установите Python 3.11.
2. Откройте эту папку в cmd.
3. Запустите build_windows.bat.
4. Готовый файл: dist\NeboProject.exe

Вариант 2 — GitHub Actions:
1. Загрузите проект в свой GitHub.
2. Actions -> Build Windows EXE -> Run workflow.
3. Скачайте artifact NeboProject-Windows.

Приложение не требует Cloudflare Worker или сервер исходного HelperTool.
Для Telegram нужен Bot Token + Chat ID.
Для VK нужен VK API Token + ID получателя.

### Telegram proxy
NeboProject supports per-application Telegram HTTP and SOCKS5 proxies. Configure them in the setup window under «Прокси». For SOCKS5, the build installs PySocks through `requests[socks]`.

ICON NOTE (NeboProject 1.1.8)
The project contains the new red Nebo icon in path/icon.ico and path/icon.png.
After rebuilding the EXE, remove/recreate an old desktop shortcut if Windows still shows the cached StaffControl icon.
The old icon can remain cached by Windows in an existing .lnk shortcut even when the new EXE contains the correct icon.
