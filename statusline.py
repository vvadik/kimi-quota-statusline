#!/usr/bin/env python3
"""Штатные model/context сегменты Kimi TUI и официальные квоты 5h/7d/mo."""

import glob
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
SESSIONS = os.path.join(HOME, 'sessions')
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
TAIL_BYTES = 524288
OAUTH_KEY_RE = re.compile(r'^oauth/(kimi-code(?:-env-[0-9a-f]{16})?)$')
CACHE_VERSION = 2

USE_ANSI = os.environ.get('KIMI_SL_NOCOLOR') != '1'
RESET, BOLD, DIM = '\033[0m', '\033[1m', '\033[2m'
GREEN, RED, BLUE = '\033[32m', '\033[31m', '\033[34m'


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
        add_quota('mo', usages.get('limit_month_total'), modern=True)
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
        'version': CACHE_VERSION,
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
    elif previous.get('version') == CACHE_VERSION and previous.get('environment') == env_key:
        cache['fetched_at'] = previous.get('fetched_at', 0)
        for key in ('h5_used', 'h5_limit', 'h5_reset', 'wk_used', 'wk_limit', 'wk_reset',
                    'mo_used', 'mo_limit', 'mo_reset'):
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
    matches = cache.get('version') == CACHE_VERSION and cache.get('environment') == env_key
    attempt_at = cache.get('attempt_at', 0) if matches else 0
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
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return c(label + ' —', DIM)
    remaining = max(0, round((1.0 - ratio) * 100))
    marker = '~' if stale else ''
    segment = c(f'{label} {marker}{remaining}% left', DIM)
    hint = reset_hint(cache.get(prefix + '_reset', ''), now)
    return segment + (c(' ' + hint, DIM) if hint else '')


def render_quota(cache, environment, now=None):
    now = time.time() if now is None else now
    env_key = environment['key'] if environment else 'invalid'
    matches = cache.get('version') == CACHE_VERSION and cache.get('environment') == env_key
    if not matches:
        cache = {}
    try:
        stale = now - float(cache.get('fetched_at', 0)) > STALE_AFTER_S
    except (TypeError, ValueError, OverflowError):
        stale = True
    if cache.get('wk_limit'):
        label, prefix = '7d', 'wk'
    elif cache.get('mo_limit'):
        label, prefix = 'mo', 'mo'
    else:
        label, prefix = '7d', 'wk'
    return (quota_segment('5h', 'h5', cache, stale, now) + ' | '
            + quota_segment(label, prefix, cache, stale, now))


def session_state(session_id):
    effort, swarm = '', False
    if not session_id:
        return effort, swarm
    hits = glob.glob(os.path.join(SESSIONS, '*', session_id, 'agents', 'main', 'wire.jsonl'))
    if not hits:
        return effort, swarm
    try:
        with open(hits[0], 'rb') as f:
            end = os.path.getsize(hits[0])
            got_effort = got_swarm = False
            while end > 0 and not (got_effort and got_swarm):
                start = max(0, end - TAIL_BYTES)
                f.seek(start)
                lines = f.read(end - start).splitlines()
                if start > 0 and lines:
                    lines = lines[1:]
                need_effort = not got_effort
                need_swarm = not got_swarm
                for line in lines:
                    if b'thinkingEffort' in line and need_effort:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        value = record.get('thinkingEffort')
                        if not value and isinstance(record.get('event'), dict):
                            value = record['event'].get('thinkingEffort')
                        if isinstance(value, str) and value:
                            effort = value
                            got_effort = True
                    elif b'swarm_mode' in line and need_swarm:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        kind = record.get('type')
                        if kind == 'swarm_mode.enter':
                            swarm = True
                            got_swarm = True
                        elif kind == 'swarm_mode.exit':
                            swarm = False
                            got_swarm = True
                end = start
    except OSError:
        pass
    return effort, swarm


def _pid_alive(pid):
    if os.name == 'nt':
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError, OverflowError):
        return False


def running_task_count(session_id):
    if not session_id:
        return 0
    count = 0
    pattern = os.path.join(SESSIONS, '*', session_id, 'agents', 'main', 'tasks', '*.json')
    for path in glob.glob(pattern):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                task = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(task, dict) or task.get('status') != 'running':
            continue
        if task.get('kind') == 'process' and task.get('pid') and not _pid_alive(task['pid']):
            continue
        if task.get('kind') != 'process':
            wire = os.path.join(os.path.dirname(os.path.dirname(path)), 'wire.jsonl')
            try:
                if time.time() - os.stat(wire).st_mtime > 120:
                    continue
            except OSError:
                continue
        count += 1
    return count


def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def safe_text(value, limit=80):
    text = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', str(value))
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = ''.join(ch for ch in text if ch.isprintable())
    return text[:limit]


def render_snapshot(snapshot, effort='', swarm=False, tasks=0):
    parts = []
    mode = snapshot.get('permissionMode') or snapshot.get('permission_mode')
    if mode:
        mode = str(mode)
        style = DIM if mode == 'manual' else (GREEN if mode == 'yolo' else RED)
        parts.append(c(mode.upper(), style, DIM if mode == 'manual' else BOLD))
    if snapshot.get('planMode') or snapshot.get('plan_mode'):
        parts.append(c('plan', BLUE, BOLD))
    model = snapshot.get('model') or 'unknown'
    if isinstance(model, dict):
        model = model.get('alias') or model.get('id') or model.get('name') or 'unknown'
    model = safe_text(model) or 'unknown'
    if effort:
        model += '·' + safe_text(effort, 20)
    parts.append(model)
    if swarm:
        parts.append(c('swarm', BLUE, BOLD))
    max_tokens = finite_number(snapshot.get('maxContextTokens'))
    used_tokens = finite_number(snapshot.get('contextTokens'))
    usage = finite_number(snapshot.get('contextUsage'))
    remaining = None
    if max_tokens is not None and max_tokens > 0 and used_tokens is not None:
        remaining = 100 - used_tokens * 100 / max_tokens
    elif usage is not None:
        remaining = 100 - usage * 100
    if remaining is not None:
        parts.append(f'ctx:{remaining:.0f}% left')
    if used_tokens is not None and used_tokens > 0:
        if used_tokens >= 1000:
            parts.append(f'used:{used_tokens / 1000:.1f}k')
        else:
            parts.append(f'used:{int(used_tokens)}')
    parts.append(c(f'⚙ {tasks}', GREEN if tasks else DIM))
    cwd = snapshot.get('cwd') or snapshot.get('work_dir') or snapshot.get('workDir')
    if cwd:
        cwd = str(cwd)
        if cwd == os.path.expanduser('~'):
            directory = '~'
        else:
            directory = os.path.basename(cwd.rstrip('/')) or cwd
        directory = safe_text(directory, 21)
        if len(directory) > 20:
            directory = directory[:19] + '…'
        if directory:
            parts.append(directory)
    return ' | '.join(parts)


def render_status(cache, environment, snapshot, effort='', swarm=False, tasks=0, now=None):
    native = render_snapshot(snapshot, effort, swarm, tasks)
    return native + ' | ' + render_quota(cache, environment, now)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdin, 'buffer'):
        raw = sys.stdin.buffer.read().decode('utf-8', 'replace')
    else:
        raw = sys.stdin.read()
    try:
        snapshot = json.loads(raw) if raw.strip() else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
    except ValueError:
        snapshot = {}
    environment = resolve_environment()
    cache = read_cache()
    maybe_refresh(cache, environment, str(snapshot.get('version') or ''))
    session_id = snapshot.get('sessionId') or snapshot.get('session_id') or ''
    effort, swarm = session_state(session_id)
    tasks = running_task_count(session_id)
    print(render_status(cache, environment, snapshot, effort, swarm, tasks))


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
