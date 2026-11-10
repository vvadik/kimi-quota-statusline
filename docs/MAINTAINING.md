# Руководство для сопровождающих

## Цель и границы проекта

Версия 2.2.0 сохраняет штатные `model | ctx | used`, добавляет permission/plan, effort, swarm, короткий cwd и маркер `⚙ N`, затем показывает остаток `5h` и `7d` без progress bar. Если `7d` отсутствует, вторым сегментом отображается `mo` из `limit_month_total`; `limit_month_code` не используется. `win`, token/стоимость/TPS, git, HTML-панель, HTTP-сервер, prompt hook и stdin/debug-снимки не восстанавливаются. Невизуальные клиенты не должны инициировать сетевые запросы этого плагина.

Цвета соответствуют риску: `AUTO` (Never Ask) красный, `YOLO` (Ask When Needed) зелёный, `MANUAL` приглушённый, `plan` и `swarm` синие, активные задачи зелёные, отсутствие задач серое. Квоты показывают `remaining = max(0, round((1 - used / limit) * 100))`, а не использованную долю.

Проект полностью русифицирован: новый текст пишите на русском или английском, но не на китайском. Английский и русский README обновляются синхронно.

## Метаданные сессий и задач

Разрешены только узкие read-only источники:

- `thinkingEffort` и `swarm_mode.enter/exit` из текущего `wire.jsonl` для effort/swarm;
- `kind`, `status`, `pid` и время из `tasks/*.json` для `⚙ N` и отбрасывания зависших running.

Не читайте `output.log`, команды/описания задач или транскрипты субагентов. Не создавайте HTTP/HTML-панель: детали открываются штатной `/tasks`. Текстовые model/cwd проходят очистку ANSI/OSC перед выводом.

## Файлы

- `statusline.py`: разбор endpoint и OAuth slot, обработка и отображение квот, общий кэш, атомарная блокировка и короткий refresh.
- `install.py` / `uninstall.py`: резервное копирование и изменение `tui.toml`; POSIX использует `shlex.quote` и JSON-строку TOML; удаление очищает новые cache/lock.
- `kimi.plugin.json`: версия и описание; **добавлять hooks запрещено**.
- `commands/*.md`: подсказки для slash-команд установки и удаления.
- `tests/test_regressions.py`: стандартный `unittest`, фиктивные учётные данные, fake opener и loopback HTTP-серверы.
- `tests/windows-e2e.ps1`: изолированные Windows-проверки рендеринга, refresh и установки/удаления; файл должен сохранять UTF-8 BOM.
- `.github/workflows/ci.yml`: тесты и smoke на Ubuntu/macOS/Windows.

## Активность и конкурентность

Kimi TUI вызывает statusline не чаще одного раза в секунду. Это единственный сигнал активности. `main()` использует из stdin только `version`, не сохраняет ввод и не читает sessions.

`maybe_refresh()` при `attempt_at` старше 90 секунд для того же environment:

1. Создаёт HOME при необходимости (только новый каталог с mode 0700; права существующего `~/.kimi-code` не меняются).
2. Создаёт lock через `O_CREAT | O_EXCL`; содержимое — случайный owner token из 32 hex-символов.
3. Только владелец lock запускает detached `--refresh <token> <version>`.
4. Дочерний процесс один раз вызывает `fetch_official()`, пишет cache и в `finally` удаляет lock только при совпадении owner token.
5. При ошибке `Popen` родитель удаляет свой lock; lock старше 60 секунд считается зависшим.

Отдельного HTTP-сервера, потоков, watchdog и цикла refresh нет. После прекращения вызовов TUI новые процессы не создаются; timeout одного запроса — 8 секунд.

## Формат кэша

`statusline-quota.json` содержит только:

- `version = 2`;
- `environment = <разрешённый usages URL>|<credential slot>`;
- `attempt_at` — обновляется после каждой завершённой попытки, включая ошибку, недопустимый endpoint, отсутствующий или истёкший token;
- `fetched_at` — обновляется только после валидного ответа;
- `h5_*` / `wk_*` / `mo_*` — used, limit, reset.

При ошибке сохраняются прежние quota и `fetched_at` того же environment, но `attempt_at` обновляется, чтобы не обращаться к API каждую секунду. После смены environment прежние данные не отображаются. Данные старше 600 секунд помечаются `~` и затемняются.

Запись выполняется через уникальный временный файл в том же каталоге, mode 0600, flush, fsync и `os.replace`. В cache запрещено писать access/refresh token, stdin, session id или prompt.

## Сетевой контракт

Официальный источник: MoonshotAI/kimi-code, `packages/oauth/src/managed-usage.ts`.

Разрешены только:

- `https://api.kimi.com/coding/v1/usages`
- `https://api.kimi.ai/coding/v1/usages`

`resolve_environment()` читает base URL и OAuth key из `[providers."managed:kimi-code"]`; при отсутствии использует `.com` и `oauth/kimi-code`. Допустимы только `oauth/kimi-code` и `oauth/kimi-code-env-<16 hex>`. URL должен использовать HTTPS, стандартный порт, точный путь и не содержать userinfo/query/fragment. Недопустимая конфигурация отклоняется до чтения token.

`OPENER` использует `NoRedirectHandler`: любой redirect считается ошибкой. Проверка final URL после запроса не заменяет запрет, поскольку Authorization мог уже быть передан другому хосту. Максимальный размер ответа — 1 МиБ. Читается только существующий `access_token`; обращений к `auth.kimi.com`, использования `refresh_token` и записи учётных данных нет.

В современном ответе используются `usages.limit_5h` / `limit_7d` с `used_ratio`; старые `limits[]` / `usage` служат независимым fallback. `limit_month_total` также сохраняется и отображается как `mo` только при отсутствии `limit_7d`; `limit_month_code` игнорируется. Ошибочные значения одного окна не должны портить другое.

## Тестирование и публикация

```bash
python3 tests/test_regressions.py
```

Тесты не должны использовать реальный HOME, учётные данные или официальный API. При изменении конкурентности сохраняйте тесты одного refresh при параллельных вызовах, backoff после ошибки, stale lock и owner token. При изменении endpoint — тесты другого host, HTTP, userinfo, port, traversal и redirect. При изменении installer — фактический запуск POSIX-пути с метасимволами.

Перед публикацией:

1. Дождаться успешных локальных и изолированных Docker-тестов.
2. Синхронно обновить английский и русский README, CHANGELOG, версию manifest и этот файл.
3. Проверить отсутствие иероглифов Han, token, runtime cache, тестового вывода и `__pycache__` в diff.
4. После push дождаться зелёного CI на трёх платформах и только затем устанавливать pinned commit.
5. При обновлении с 1.6.2 следовать README: проверить и завершить старый `--tasks-server`; не завершать процесс автоматически по одному PID из port-файла.
