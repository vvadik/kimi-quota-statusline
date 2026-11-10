#!/usr/bin/env python3
"""Удаление только команды этого плагина и его кэша квот."""
import os
import re
import shutil
import subprocess
import sys
import time

SECTION_RE = r'(?ms)^\[status_line\][ \t]*\r?\n.*?(?=^\[|\Z)'
RUNTIME_FILES = ('statusline-quota.json', 'statusline-quota-refresh.lock')


def _write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def _doctor(tui):
    if not shutil.which('kimi'):
        return 0
    try:
        result = subprocess.run(['kimi', 'doctor', 'tui', tui],
                                check=False, shell=(os.name == 'nt'))
    except OSError:
        print('Подсказка: не удалось запустить kimi doctor. Выполните /reload-tui '
              'и проверьте стандартную статусную строку вручную.')
        return 0
    if result.returncode == 0:
        print('Проверка kimi doctor пройдена')
    return result.returncode


def uninstall(tui, plugin_dir, doctor=True):
    if not os.path.exists(tui):
        print(f'Файл {tui} не найден, удаление не требуется')
        return 0
    with open(tui, encoding='utf-8') as f:
        text = f.read()
    if plugin_dir not in text and plugin_dir.replace('\\', '\\\\') not in text:
        print('Плагин не установлен: command не указывает на него, изменений не требуется')
        return 0
    shutil.copy(tui, f'{tui}.{time.strftime("%Y%m%d-%H%M%S")}.bak')

    def repl(match):
        body = match.group(0)
        def is_ours(line):
            if not re.match(r'\s*command\s*=', line):
                return False
            value = line.split('=', 1)[1].replace('\\\\', '\\')
            return plugin_dir in value and 'statusline.py' in value
        body = '\n'.join(line for line in body.split('\n') if not is_ours(line))
        rest = body.split('\n', 1)[1] if '\n' in body else ''
        if not re.search(r'(?m)^[a-zA-Z_]+\s*=', rest):
            return ''
        return body

    _write_atomic(tui, re.sub(SECTION_RE, repl, text))
    print(f'Команда плагина удалена из {tui}; резервная копия создана')
    return _doctor(tui) if doctor else 0


def cleanup_runtime(kc_home):
    for name in RUNTIME_FILES:
        try:
            os.remove(os.path.join(kc_home, name))
        except FileNotFoundError:
            pass
        except OSError as error:
            print(f'Подсказка: не удалось удалить {name}: {error}')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    kc_home = os.environ.get('KIMI_CODE_HOME', os.path.expanduser('~/.kimi-code'))
    rc = uninstall(os.path.join(kc_home, 'tui.toml'), plugin_dir)
    if rc == 0:
        cleanup_runtime(kc_home)
        print('Удаление завершено. Выполните /reload-tui, чтобы восстановить стандартную строку.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
