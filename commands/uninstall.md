---
description: Удалить статусную строку и кэш квот
---

Удали Kimi Quota Statusline:

1. Запусти через Bash кроссплатформенный деинсталлятор: `python3 ~/.kimi-code/plugins/managed/kimi-quota-statusline/uninstall.py` (в Windows — `python uninstall.py`; в macOS/Linux можно использовать обёртку uninstall.sh). Если этого пути нет, найди uninstall.py в текущем каталоге плагина.
2. Деинсталлятор предварительно создаст резервную копию `tui.toml`, удалит только команду этого плагина из `[status_line]`, его кэш квот и lock-файл.
3. После завершения напомни пользователю выполнить `/reload-tui`, чтобы восстановить стандартную статусную строку.
