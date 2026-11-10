#!/usr/bin/env python3
"""Установка статусной строки model/context и квот с резервной копией tui.toml."""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

SECTION_RE = r'(?ms)^\[status_line\][ \t]*\r?\n.*?(?=^\[|\Z)'
_CMD_UNSAFE = set(' &|<>^()%"!,;=')


def _write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def _cmd_needs_quotes(s):
    return any(ch in _CMD_UNSAFE for ch in s)


def build_command(target, os_name=None, executable=None):
    os_name = os_name or os.name
    if os_name == 'nt':
        raw_exe = executable or sys.executable
        exe = raw_exe.replace('\\', '\\\\')
        tgt = target.replace('\\', '\\\\')
        if not _cmd_needs_quotes(raw_exe) and not _cmd_needs_quotes(target):
            return f'command = "{exe} {tgt}"'
        print('Подсказка: путь к интерпретатору или плагину содержит пробелы/метасимволы cmd. '
              'В некоторых сборках CLI такая команда может не запуститься, и TUI вернётся '
              'к встроенной строке. Если после /reload-tui строка не появилась, '
              'переместите плагин в каталог без пробелов и переустановите.')
        return f'command = "\\"{exe}\\" \\"{tgt}\\""'
    command = 'python3 ' + shlex.quote(target)
    return 'command = ' + json.dumps(command, ensure_ascii=False)


def _doctor(tui):
    if not shutil.which('kimi'):
        return 0
    try:
        result = subprocess.run(['kimi', 'doctor', 'tui', tui],
                                check=False, shell=(os.name == 'nt'))
    except OSError:
        print('Подсказка: не удалось запустить kimi doctor. Выполните /reload-tui '
              'и проверьте статусную строку вручную.')
        return 0
    if result.returncode == 0:
        print('Проверка kimi doctor пройдена')
    return result.returncode


def install(tui, target, os_name=None, executable=None, doctor=True):
    cmd_line = build_command(target, os_name, executable)
    if os.path.exists(tui):
        with open(tui, encoding='utf-8') as f:
            text = f.read()
    else:
        text = ''
    if text and not text.endswith('\n'):
        text += '\n'
    match = re.search(SECTION_RE, text)
    section = match.group(0) if match else ''
    if target in section or target.replace('\\', '\\\\') in section:
        print('Уже установлено: [status_line].command указывает на этот плагин, изменений не требуется')
        return 0
    if re.search(r'(?m)^command\s*=', section):
        print('Внимание: [status_line].command указывает на другой скрипт и будет заменён '
              '(исходный файл сохранён в резервной копии)')
    if os.path.exists(tui):
        shutil.copy(tui, f'{tui}.{time.strftime("%Y%m%d-%H%M%S")}.bak')
    if section:
        def repl(found):
            body = found.group(0)
            if re.search(r'(?m)^command\s*=', body):
                return re.sub(r'(?m)^command\s*=.*$', lambda _: cmd_line, body, count=1)
            return body.rstrip('\n') + '\n' + cmd_line + '\n'
        text = re.sub(SECTION_RE, repl, text)
    else:
        text += f'\n[status_line]\n{cmd_line}\n'
    os.makedirs(os.path.dirname(tui), exist_ok=True)
    _write_atomic(tui, text)
    print(f'Записано: {tui}')
    return _doctor(tui) if doctor else 0


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(plugin_dir, 'statusline.py')
    if not os.path.isfile(target):
        print(f'Ошибка: {target} не существует')
        return 1
    kc_home = os.environ.get('KIMI_CODE_HOME', os.path.expanduser('~/.kimi-code'))
    rc = install(os.path.join(kc_home, 'tui.toml'), target)
    if rc == 0:
        print('Установка завершена. Выполните /reload-tui в Kimi Code TUI или откройте новую сессию.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
