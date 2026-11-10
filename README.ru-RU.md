<div align="center">
<img src="assets/hero.svg" alt="Kimi Quota Statusline — штатная строка и остаток квот" width="760" />
</div>

# Kimi Quota Statusline

Минимальная статусная строка для [Kimi Code CLI](https://github.com/MoonshotAI/kimi-code): штатные model/context, полезные маркеры активности и остаток официальных квот.

Активное состояние:

```text
AUTO plan | K3.1 Pro·max | swarm | ctx:83% left | used:178.1k | ⚙ 2 | project | 5h 97% left 4h53m | mo 89% left 28d12h
```

Без plan/swarm/активных задач:

```text
YOLO | K3.1 Pro·max | ctx:83% left | used:178.1k | ⚙ 0 | project | 5h 97% left 4h53m | mo 89% left 28d12h
```

## Отображение

- Режим разрешений: `MANUAL` приглушённый, `YOLO` зелёный, `AUTO` красный. Цвета соответствуют риску: Never Ask (`AUTO`) разрешает чувствительные операции, а Ask When Needed (`YOLO`) всё ещё запрашивает подтверждение.
- `plan` синим при активном Plan mode.
- Модель и глубина reasoning, например `K3.1 Pro·max`.
- Синий `swarm` при активном swarm mode.
- Остаток `ctx`, `used` токенов и короткое имя текущего каталога стандартным цветом терминала.
- `⚙ N`: зелёный при активных фоновых задачах, серый при `N = 0`.
- `5h` и `7d` как **остаток в процентах**, без заполняемого бара. Если `7d` недоступен, отображается официальная общая месячная квота `mo`.

Например, `5h 97% left 4h53m` означает, что осталось 97% пятичасовой квоты, а до сброса 4 часа 53 минуты. При использовании более 100% отображается `0% left`. Устаревшие данные помечаются `~`.

## Фоновые задачи

Маркер предназначен только для чтения. Детали открываются штатной интерактивной панелью Kimi:

```text
/tasks
```

Встроенный браузер задач поддерживает выбор стрелками, preview output/activity, обновление, фильтрацию и остановку задач. Плагин не создаёт HTML-панель и не отдаёт output задач.

Для маркера используются только `kind`, `status`, `pid` и временные поля из `tasks/*.json`. `output.log`, команды/описания задач и транскрипты субагентов не читаются. Для reasoning effort и swarm из `wire.jsonl` берутся только записи `thinkingEffort` и `swarm_mode.enter/exit`; содержимое нигде не сохраняется и никуда не отправляется.

## Установка

В Kimi Code выполните:

```text
/plugins install https://github.com/vvadik/kimi-quota-statusline
/kimi-quota-statusline:install
```

Затем выполните `/reload-tui` или откройте новую TUI-сессию. Для закрепления проверенного коммита используйте `https://github.com/vvadik/kimi-quota-statusline/commit/<sha>`.

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

При устаревшем кэше TUI запускает один короткий `--refresh`. Атомарная блокировка с owner token не позволяет нескольким терминалам создать параллельные запросы. Процесс выполняет не более одного запроса, атомарно записывает кэш с правами `0600` и завершается. Нет вызовов TUI — нет новых запросов.

`attempt_at` ограничивает и успешные, и неудачные попытки одной за 90 секунд. `fetched_at` обновляется только после валидного ответа. При ошибке прежние данные сохраняются; через 10 минут они затемняются и помечаются `~`.

Нет фонового сервера, циклических задач, prompt hooks, token/стоимости/TPS, git-маркера или HTML-панели задач.

## Удаление

```text
/kimi-quota-statusline:uninstall
```

Или выполните `python3 uninstall.py` из managed/source-каталога. Установка и удаление создают резервную копию `tui.toml`; удаление затрагивает только команду этого плагина, его кэш квот и lock-файл.

### Обновление с 1.6.2

Прежняя локальная панель и prompt hook были удалены в 2.0.0. После обновления перезагрузите плагины и TUI. Если старый `statusline.py --tasks-server` ещё работает, найдите PID в `~/.kimi-code/statusline-tasks.port`, проверьте командную строку через `ps -p <pid> -o command=` и завершайте процесс только после подтверждения, что это старый сервер.

После этого можно удалить старые `statusline-stdin.json`, `statusline-hook-payloads.jsonl`, `statusline-tasks.html`, `statusline-tasks.port`, `statusline-tokens.json` и `statusline-refresh.lock`. Текущие версии их не используют.

## Разработка

```bash
python3 tests/test_regressions.py
```

Тесты используют фиктивные учётные данные и локальные fake HTTP-серверы; реальный OAuth-токен и обращения к официальному API не нужны.

## Лицензия

[MIT](LICENSE)
