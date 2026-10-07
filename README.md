# NeboProject

Персональная версия утилиты для модерации: мониторинг latest.log, автоматические скриншоты и отправка уведомлений напрямую в Telegram или VK API.

Приложение не использует исходный GitHub-проект, Cloudflare Worker или встроенный секрет стороннего проекта.

Данные хранятся в `%APPDATA%\\NeboProject\\neboproject.db`, скриншоты — в `screenshots`.

### Telegram proxy
NeboProject supports per-application Telegram HTTP and SOCKS5 proxies. Configure them in the setup window under «Прокси». For SOCKS5, the build installs PySocks through `requests[socks]`.
