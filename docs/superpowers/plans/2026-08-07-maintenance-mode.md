# План консервативного сопровождения (релиз v1.1.1 и чек-лист совместимости)

> Исторический план версии 1.1.1. Команды, функции и runtime-файлы относятся к той версии, а не к quota-only 2.0.0.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** опубликовать v1.1.1 (накопленные исправления: расход по сессии и динамический UA) и зафиксировать чек-лист совместимости после обновлений CLI в MAINTAINING.md.

**Architecture:** только релизные и документальные операции, новый код не требуется. Изменения рабочего дерева уже подготовлены и проверены: проверка → фиксация версии → дополнение документации → push и tag.

**Tech Stack:** Python 3 без зависимостей, git/GitHub (`gh` уже авторизован), Keep a Changelog.

## Global Constraints

- Репозиторий: `https://github.com/3209621-dotcom/kimi-quota-statusline`, ветка `main`.
- Публикация следует разделу 6 `docs/MAINTAINING.md` той версии; сообщения commit используют префикс типа и русское описание (`docs:`, `perf:`, `feat:`).
- Правило двуязычного README: любое изменение поведения синхронизируется в `README.md` и языковой версии README; соответствующие изменения уже есть в рабочем дереве и требуют только проверки.
- Версия в `kimi.plugin.json`: `1.1.0` → `1.1.1`; tag `v1.1.1`.
- Везде используется дата `2026-08-07`.

---

### Task 1: проверка перед публикацией

**Files:**
- Файлы не изменяются; проверяется рабочая версия `statusline.py`.

**Interfaces:**
- Consumes: все незакоммиченные изменения (`statusline.py`, `CHANGELOG.md`, оба README).
- Produces: подтверждение проверки, обязательное для Task 2.

- [ ] **Step 1: ручной рендеринг в цветном и текстовом режимах**

```bash
cd /Users/guo/Projects/kimi-quota-statusline
cat ~/.kimi-code/statusline-stdin.json | python3 statusline.py
cat ~/.kimi-code/statusline-stdin.json | KIMI_SL_NOCOLOR=1 python3 statusline.py
```

Expected: обе команды выводят одну строку с permission/моделью/5h/7d/token и стоимостью сессии, без traceback.

- [ ] **Step 2: время выполнения значительно меньше 300 мс**

```bash
time (cat ~/.kimi-code/statusline-stdin.json | python3 statusline.py > /dev/null)
```

Expected: real < 0,3 с (обычно < 0,1 с).

- [ ] **Step 3: официальный quota API и динамический UA**

```bash
python3 -c "
import statusline
d = statusline.fetch_official('0.31.1')
assert d and d.get('wk_limit'), 'official fetch failed'
print('OK', d.get('wk_used'), '/', d.get('wk_limit'))
"
```

Expected: `OK <used> / <limit>`. Token должен быть действителен (в той версии — 15 минут при работающем CLI); при ошибке сначала проверить `expires_at` в `~/.kimi-code/credentials/kimi-code.json`.

### Task 2: фиксация версии и commit v1.1.1

**Files:**
- Modify: `kimi.plugin.json` (`"version": "1.1.0"` → `"1.1.1"`).
- Modify: `CHANGELOG.md` (два пункта Unreleased переносятся в `## [1.1.1] - 2026-08-07`).
- Также включить: `statusline.py` и оба README.

**Interfaces:**
- Consumes: результат Task 1.
- Produces: локальный commit с version `1.1.1`, готовый к push в Task 4.

- [ ] **Step 1: изменить версию manifest**

`"version": "1.1.0"` → `"version": "1.1.1"`

- [ ] **Step 2: обновить CHANGELOG**

Перенести блок `### Changed` из `## [Unreleased]` под новый заголовок:

```markdown
## [1.1.1] - 2026-08-07

### Changed
- Расход рассчитывается по текущей сессии, а не по всем сессиям за день
- Версия User-Agent для официального API берётся из поля version снимка CLI
```

Заголовок `## [Unreleased]` остаётся пустым.

- [ ] **Step 3: проверить синхронность README**

```bash
git diff README.md | grep -c "^+.*Today's"        # число устаревших новых строк, ожидается 0
git diff README.ru-RU.md | grep -c '^+.*за день'   # проверка русской формулировки
```

Expected: изменения «за день → текущая сессия / Today's → Current session» синхронны, старого текста в добавленных строках нет. Любое расхождение исправить до продолжения.

- [ ] **Step 4: создать commit**

```bash
git add statusline.py CHANGELOG.md README.md README.ru-RU.md kimi.plugin.json
git commit -m "chore(release): v1.1.1 — расход по сессии и динамическая версия UA"
```

Expected: `git status --short` чистый; `git log --oneline -1` показывает созданный commit.

### Task 3: добавить чек-лист в MAINTAINING.md

**Files:**
- Modify: `docs/MAINTAINING.md` (новый раздел «Проверка совместимости после обновления CLI», последующие разделы перенумерованы).

**Interfaces:**
- Consumes: не зависит от Task 2, но коммитится после него.
- Produces: локальный commit с чек-листом сопровождения.

- [ ] **Step 1: вставить новый раздел после публикации и перенумеровать следующие**

Вставить:

```markdown
## Проверка совместимости после обновления CLI

После обновления Kimi Code (особенно minor) выполнить все пункты. Если всё проходит, код менять не нужно; иначе использовать раздел о каналах данных. Последняя база: CLI 0.31.1 (2026-08-07, все проверки пройдены).

1. Сопоставить официальный changelog: https://www.kimi.com/code/docs/en/kimi-code-cli/release-notes/changelog.html — status_line / plugin / wire / usages.
2. Проверить поля stdin: `cat ~/.kimi-code/statusline-stdin.json` — model, cwd, gitBranch, permissionMode, planMode, contextUsage, contextTokens, maxContextTokens, sessionId, version.
3. Проверить wire-записи текущей сессии: usage.record / thinkingEffort / swarm_mode, для каждой grep -c должен быть >0.
4. Проверить quota API: `python3 -c "import statusline; print(statusline.fetch_official())"` должен вернуть dict с wk_limit. Истёкший token даёт None; сначала убедиться, что CLI работает.
5. Выполнить `kimi doctor tui`.
6. Выполнить ручной рендеринг и измерить время; одна строка без ошибок, значительно меньше 300 мс.
```

Также обновить номера последующих разделов и ссылки на них.

- [ ] **Step 2: проверить заголовки**

```bash
grep -n '^## ' docs/MAINTAINING.md
```

Expected: правильный порядок разделов без повторяющихся номеров и висячих ссылок.

- [ ] **Step 3: создать commit**

```bash
git add docs/MAINTAINING.md
git commit -m "docs: добавить чек-лист совместимости после обновления CLI"
```

### Task 4: push, tag и удалённая проверка

**Files:**
- Файлы не изменяются; только git remote.

**Interfaces:**
- Consumes: commit из Task 2 и Task 3, а также ранее созданный spec commit `ca3d417`.
- Produces: актуальный origin/main и видимый на GitHub tag `v1.1.1`.

- [ ] **Step 1: опубликовать main**

```bash
git push origin main
```

Expected: успешный push без non-fast-forward.

- [ ] **Step 2: создать и опубликовать tag**

```bash
git tag v1.1.1 && git push origin v1.1.1
```

- [ ] **Step 3: проверить удалённый репозиторий**

```bash
gh api repos/3209621-dotcom/kimi-quota-statusline --jq '.pushed_at'
gh api repos/3209621-dotcom/kimi-quota-statusline/tags --jq '.[].name'
git tag --list 'v1.1.1'
```

Expected: `pushed_at` соответствует текущему времени, среди tags есть `v1.1.1`.

- [ ] **Step 4: финальная проверка**

```bash
git status --short && git log --oneline -4
```

Expected: рабочее дерево чистое, последние commit относятся к релизу v1.1.1 и tag указывает на соответствующий commit.
