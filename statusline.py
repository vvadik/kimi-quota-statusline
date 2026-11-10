#!/usr/bin/env python3
"""Kimi TUI status line with official 5h and 7d quotas only."""

import json
import math
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.environ.get('KIMI_CODE_HOME', os.path.expanduser('~/.kimi-code'))
CACHE = os.path.join(HOME, 'statusline-quota.json')
LOCK = os.path.join(HOME, 'statusline-quota-refresh.lock')
CONFIG_FILE = os.path.join(HOME, 'config.toml')
CRED_DIR = os.path.join(HOME, 'credentials')

DEFAULT_BASE_URL = 'https://api.kimi.com/coding/v1'
ALLOWED_BASE_URLS = {
    'https://api.kimi.com/coding/v1',
    'https://api.kimi.ai/coding/v1',
}
REFRESH_INTERVAL_S = 90
STALE_AFTER_S = 600
LOCK_S = 60
REQUEST_TIMEOUT_S = 8
MAX_RESPONSE_BYTES = 1024 * 1024
OAUTH_KEY_RE = re.compile(r'^oauth/(kimi-code(?:-env-[0-9a-f]{16})?)$')

USE_ANSI = os.environ.get('KIMI_SL_NOCOLOR') != '1'
RESET, BOLD, DIM = '\033[0m', '\033[1m', '\033[2m'
GREEN, YELLOW, RED = '\033[32m', '\033[33m', '\033[31m'


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirectHandler)


def c(text, *codes):
    if not USE_ANSI or not text:
        return text
    return ''.join(codes) + str(text) + RESET


def normalize_usages_url(base_url):
    if not isinstance(base_url, str):
        return None
    try:
        parts = urllib.parse.urlsplit(base_url.strip())
        if (parts.scheme.lower() != 'https' or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment):
            return None
        if parts.port not in (None, 443):
            return None
        host = parts.hostname.lower() if parts.hostname else ''
        path = parts.path.rstrip('/')
        base = f'https://{host}{path}'
    except (TypeError, ValueError):
        return None
    if base not in ALLOWED_BASE_URLS:
        return None
    return base + '/usages'


def resolve_environment():
    base_url = DEFAULT_BASE_URL
    oauth_key = 'oauth/kimi-code'
    try:
        section = ''
        with open(CONFIG_FILE, encoding='utf-8', errors='replace') as f:
            for raw in f:
                line = raw.strip()
                if line.startswith('['):
                    section = line.strip('[] ')
                elif '=' in line and not line.startswith('#'):
                    key, _, value = line.partition('=')
                    value = value.strip().strip('"')
                    if section == 'providers."managed:kimi-code"' and key.strip() == 'base_url' and value:
                        base_url = value
                    elif section == 'providers."managed:kimi-code".oauth' and key.strip() == 'key' and value:
                        oauth_key = value
    except OSError:
        pass

    usages_url = normalize_usages_url(base_url)
    match = OAUTH_KEY_RE.fullmatch(oauth_key)
    if usages_url is None or match is None:
        return None
    slot = match.group(1)
    return {
        'key': usages_url + '|' + slot,
        'url': usages_url,
        'slot': slot,
        'cred_file': os.path.join(CRED_DIR, slot + '.json'),
    }


def parse_quota(payload):
    if not isinstance(payload, dict):
        return None
    out = {}

    def add_quota(prefix, detail, modern=False):
        if not isinstance(detail, dict):
            return
        used = detail.get('used_ratio') if modern else detail.get('used', 0)
        limit = 1.0 if modern else detail.get('limit')
        if isinstance(used, bool) or isinstance(limit, bool):
            return
        try:
            used, limit = float(used), float(limit)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(used) or not math.isfinite(limit) or used < 0 or limit <= 0:
            return
        reset = detail.get('reset_time' if modern else 'resetTime', '')
        out[prefix + '_used'] = used
        out[prefix + '_limit'] = limit
        out[prefix + '_reset'] = reset if isinstance(reset, str) else ''

    add_quota('wk', payload.get('usage'))
    limits = payload.get('limits')
    for item in limits if isinstance(limits, list) else []:
        if not isinstance(item, dict):
            continue
        window = item.get('window')
        if (isinstance(window, dict) and window.get('duration') == 300
                and window.get('timeUnit') == 'TIME_UNIT_MINUTE'):
            add_quota('h5', item.get('detail'))
    usages = payload.get('usages')
    if isinstance(usages, dict):
        add_quota('h5', usages.get('limit_5h'), modern=True)
        add_quota('wk', usages.get('limit_7d'), modern=True)
    return out or None


def fetch_official(ver='', environment=None):
    environment = environment or resolve_environment()
    if environment is None:
        return None
    try:
        with open(environment['cred_file'], encoding='utf-8') as f:
            cred = json.load(f)
        if not isinstance(cred, dict):
            return None
        if cred.get('expires_at', 0) < time.time() + 10:
            return None
        token = cred.get('access_token')
        if not isinstance(token, str) or not token:
            return None
        safe_ver = ''.join(ch for ch in str(ver) if 32 <= ord(ch) < 127 and ch not in '\r\n')[:64]
        req = urllib.request.Request(environment['url'], headers={
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/json',
            'User-Agent': 'kimi-code-cli/' + safe_ver if safe_ver else 'kimi-code-cli',
        })
        with OPENER.open(req, timeout=REQUEST_TIMEOUT_S) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return None
        return parse_quota(json.loads(raw.decode('utf-8')))
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        return None


def read_cache():
    try:
        with open(CACHE, encoding='utf-8') as f:
            cache = json.load(f)
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def empty_cache(environment, now):
    return {
        'version': 1,
        'environment': environment['key'] if environment else 'invalid',
        'attempt_at': now,
        'fetched_at': 0,
    }


def write_cache(cache):
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.statusline-quota-', dir=HOME, text=True)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(cache, f, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CACHE)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def refresh_cache(ver=''):
    now = time.time()
    environment = resolve_environment()
    previous = read_cache()
    quota = fetch_official(ver, environment)
    cache = empty_cache(environment, now)
    env_key = cache['environment']
    if quota is not None:
        cache['fetched_at'] = now
        cache.update(quota)
    elif previous.get('environment') == env_key:
        cache['fetched_at'] = previous.get('fetched_at', 0)
        for key in ('h5_used', 'h5_limit', 'h5_reset', 'wk_used', 'wk_limit', 'wk_reset'):
            if key in previous:
                cache[key] = previous[key]
    write_cache(cache)
    return cache


def _detached_kwargs(os_name=os.name):
    if os_name == 'nt':
        return {'creationflags': 0x00000008 | 0x00000200}
    return {'start_new_session': True}


def acquire_lock():
    for _ in range(2):
        token = secrets.token_hex(16)
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w', encoding='ascii') as f:
                f.write(token)
            return token
        except FileExistsError:
            try:
                if time.time() - os.stat(LOCK).st_mtime <= LOCK_S:
                    return None
                os.remove(LOCK)
            except FileNotFoundError:
                continue
            except OSError:
                return None
        except OSError:
            return None
    return None


def release_lock(token):
    if not token:
        return
    try:
        with open(LOCK, encoding='ascii') as f:
            if f.read() != token:
                return
        os.remove(LOCK)
    except OSError:
        pass


def maybe_refresh(cache, environment, ver=''):
    now = time.time()
    env_key = environment['key'] if environment else 'invalid'
    attempt_at = cache.get('attempt_at', 0) if cache.get('environment') == env_key else 0
    try:
        due = now - float(attempt_at) >= REFRESH_INTERVAL_S
    except (TypeError, ValueError, OverflowError):
        due = True
    if not due:
        return False
    try:
        os.makedirs(HOME, mode=0o700, exist_ok=True)
    except OSError:
        return False
    token = acquire_lock()
    if token is None:
        return False
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), '--refresh', token, str(ver or '')],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **_detached_kwargs())
    except OSError:
        release_lock(token)
        return False
    return True


def reset_hint(iso, now=None):
    if not isinstance(iso, str) or not iso:
        return ''
    try:
        from datetime import datetime
        now = time.time() if now is None else now
        timestamp = datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()
        seconds = int(timestamp - now)
        if seconds <= 0:
            return ''
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes = seconds // 60
        if days:
            return f'{days}d{hours}h'
        if hours:
            return f'{hours}h{minutes}m' if minutes else f'{hours}h'
        return f'{minutes}m'
    except (ValueError, TypeError, OverflowError, OSError):
        return ''


def quota_segment(label, prefix, cache, stale, now):
    if not cache.get(prefix + '_limit'):
        return c(label + ' —', DIM)
    try:
        ratio = cache[prefix + '_used'] / cache[prefix + '_limit']
        if not math.isfinite(ratio) or ratio < 0:
            return c(label + ' —', DIM)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return c(label + ' —', DIM)
    filled = min(6, max(0, round(min(1.0, ratio) * 6)))
    color = GREEN if ratio < 0.6 else (YELLOW if ratio < 0.85 else RED)
    percent = str(round(100 * ratio))
    if stale:
        segment = c(label + ' ', DIM) + c('█' * filled + '░' * (6 - filled), DIM)
        segment += ' ' + c('~' + percent + '%', DIM)
    else:
        segment = c(label + ' ', DIM) + c('█' * filled, color) + c('░' * (6 - filled), DIM)
        segment += ' ' + c(percent + '%', color, BOLD)
    hint = reset_hint(cache.get(prefix + '_reset', ''), now)
    return segment + (c(' ' + hint, DIM) if hint else '')


def render_quota(cache, environment, now=None):
    now = time.time() if now is None else now
    env_key = environment['key'] if environment else 'invalid'
    if cache.get('environment') != env_key:
        cache = {}
    try:
        stale = now - float(cache.get('fetched_at', 0)) > STALE_AFTER_S
    except (TypeError, ValueError, OverflowError):
        stale = True
    return (quota_segment('5h', 'h5', cache, stale, now) + c(' · ', DIM)
            + quota_segment('7d', 'wk', cache, stale, now))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdin, 'buffer'):
        raw = sys.stdin.buffer.read().decode('utf-8', 'replace')
    else:
        raw = sys.stdin.read()
    try:
        snapshot = json.loads(raw) if raw.strip() else {}
    except ValueError:
        snapshot = {}
    environment = resolve_environment()
    cache = read_cache()
    maybe_refresh(cache, environment, str(snapshot.get('version') or ''))
    print(render_quota(cache, environment))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--refresh':
        token = sys.argv[2] if len(sys.argv) > 2 else ''
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            sys.exit(2)
        try:
            refresh_cache(sys.argv[3] if len(sys.argv) > 3 else '')
        finally:
            release_lock(token)
    else:
        main()
