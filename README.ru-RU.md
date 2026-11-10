<div align="center">
<img src="assets/hero.svg" alt="Kimi Quota Statusline — официальные квоты 5h и 7d" width="760" />
</div>

# Kimi Quota Statusline

Намеренно минимальная статусная строка для [Kimi Code CLI](https://github.com/MoonshotAI/kimi-code): **только официальные квоты 5h и 7d в терминальном TUI**.

- Шесть делений, фактический процент использования и обратный отсчёт до сброса.
- Общий для всех терминалов кэш с интервалом обновления **90 секунд**.
- Обновление происходит только пока визуальный Kimi TUI вызывает статусную строку. Нет TUI — нет запросов.
- Нет фонового сервера, циклических задач, hooks, месячной квоты, token/стоимости/TPS, git/cwd, swarm и панели задач.
- Транскрипты сессий, журналы задач и stdin-снимки не читаются и не сохраняются.

## Установка

В Kimi Code выполните:

```text
/plugins install https://github.com/vvadik/kimi-quota-statusline
/kimi-quota-statusline:install
```

Затем выполните `/reload-tui` или откройте новую TUI-сессию. Чтобы закрепить проверенный коммит, используйте URL `https://github.com/vvadik/kimi-quota-statusline/commit/<sha>`.

Ручная установка:

```bash
git clone https://github.com/vvadik/kimi-quota-statusline.git
python3 kimi-quota-statusline/install.py
```

Требования: Kimi Code CLI с поддержкой `[status_line]`, Python 3, macOS / Linux / Windows.

## Сеть и кэш

Разрешены только два официальных endpoint:

- `https://api.kimi.com/coding/v1/usages`
- `https://api.kimi.ai/coding/v1/usages`

HTTP, другие хосты, нестандартные порты, URL с учётными данными и все перенаправления отклоняются. Плагин читает существующий OAuth `access_token`, но не использует `refresh_token`, не обращается к серверу аутентификации и не изменяет учётные данные.

Когда TUI вызывает `statusline.py` с устаревшим кэшем, запускается один короткий процесс `--refresh`. Атомарная блокировка с токеном владельца не позволяет нескольким терминалам запустить параллельные обновления. Процесс выполняет не более одного запроса, атомарно записывает кэш с правами `0600` и завершается.

`attempt_at` ограничивает и успешные, и неудачные попытки одной за 90 секунд. `fetched_at` изменяется только после получения валидных данных. При ошибке прежние данные сохраняются; через 10 минут они затемняются и помечаются `~`.

## Удаление

```text
/kimi-quota-statusline:uninstall
```

Или выполните `python3 uninstall.py` из managed/source-каталога. Установка и удаление создают резервную копию `tui.toml`; удаление затрагивает только команду этого плагина, его кэш квот и lock-файл.

### Обновление с 1.6.2

Версия 2.0.0 удаляет прежнюю локальную панель и prompt hook. После обновления перезагрузите плагины и TUI. Если старый `statusline.py --tasks-server` уже работал, найдите PID в `~/.kimi-code/statusline-tasks.port`, проверьте командную строку через `ps -p <pid> -o command=` и завершайте процесс только после подтверждения, что это старый сервер статусной строки. Не завершайте процесс по одному PID.

После этого можно удалить старые `statusline-stdin.json`, `statusline-hook-payloads.jsonl`, `statusline-tasks.html`, `statusline-tasks.port`, `statusline-tokens.json` и `statusline-refresh.lock`. Версия 2.0.0 их не использует.

## Разработка

```bash
python3 tests/test_regressions.py
```

Тесты используют фиктивные учётные данные и локальные fake HTTP-серверы; реальный OAuth-токен и обращения к официальному API не нужны.

## Лицензия

[MIT](LICENSE)
