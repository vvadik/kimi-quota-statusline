#!/bin/bash
# Обёртка совместимости: удаление реализовано в кроссплатформенном uninstall.py.
# В Windows запускайте напрямую python uninstall.py.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/uninstall.py" "$@"
