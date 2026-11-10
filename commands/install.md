---
description: Дополнить штатную model/context строку квотами 5h/7d/mo
---

Установи Kimi Quota Statusline:

1. Запусти через Bash кроссплатформенный установщик плагина: `python3 ~/.kimi-code/plugins/managed/kimi-quota-statusline/install.py` (в Windows — `python install.py`; в macOS/Linux можно использовать обёртку install.sh). Если этого пути нет, найди install.py в текущем каталоге плагина.
2. Установщик автоматически создаст резервную копию `tui.toml`, запишет `[status_line].command` и проверит конфигурацию через `kimi doctor`.
3. После завершения напомни пользователю выполнить `/reload-tui`, чтобы применить изменения.
4. Сообщи, что плагин показывает permission/plan, model/effort, swarm, context, cwd и маркер фоновых задач, а квоты выводит как остаток 5h/7d (или mo без 7d). Детали задач открываются штатной /tasks; общий кэш 90 секунд работает только при активном TUI.
