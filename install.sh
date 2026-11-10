#!/bin/bash
# Обёртка совместимости: установка реализована в кроссплатформенном install.py.
# В Windows запускайте напрямую python install.py.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/install.py" "$@"
