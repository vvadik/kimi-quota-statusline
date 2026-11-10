#!/usr/bin/env python3
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import install
import statusline
import uninstall


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class FakeOpener:
    def __init__(self, payload=b'{}', error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def open(self, request, timeout=0):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.payload)


class StatuslineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.old = {name: getattr(statusline, name) for name in
                    ('HOME', 'CACHE', 'LOCK', 'CONFIG_FILE', 'CRED_DIR', 'OPENER', 'USE_ANSI')}
        statusline.HOME = os.path.join(self.root, 'kc')
        statusline.CACHE = os.path.join(statusline.HOME, 'statusline-quota.json')
        statusline.LOCK = os.path.join(statusline.HOME, 'statusline-quota-refresh.lock')
        statusline.CONFIG_FILE = os.path.join(statusline.HOME, 'config.toml')
        statusline.CRED_DIR = os.path.join(statusline.HOME, 'credentials')
        statusline.USE_ANSI = False
        os.makedirs(statusline.CRED_DIR)
        self.env = {
            'key': 'https://api.kimi.com/coding/v1/usages|kimi-code',
            'url': 'https://api.kimi.com/coding/v1/usages',
            'slot': 'kimi-code',
            'cred_file': os.path.join(statusline.CRED_DIR, 'kimi-code.json'),
        }
        self.write_cred()

    def tearDown(self):
        for name, value in self.old.items():
            setattr(statusline, name, value)
        self.temp.cleanup()

    def write_cred(self, token='FAKE_TOKEN', expires_at=None):
        with open(self.env['cred_file'], 'w', encoding='utf-8') as f:
            json.dump({'access_token': token,
                       'expires_at': time.time() + 600 if expires_at is None else expires_at}, f)

    def write_config(self, base_url=statusline.DEFAULT_BASE_URL, oauth_key='oauth/kimi-code'):
        with open(statusline.CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write('[providers."managed:kimi-code"]\n'
                    f'base_url = "{base_url}"\n\n'
                    '[providers."managed:kimi-code".oauth]\n'
                    f'key = "{oauth_key}"\n')

    def cache(self, **updates):
        value = {'version': 1, 'environment': self.env['key'],
                 'attempt_at': time.time(), 'fetched_at': time.time()}
        value.update(updates)
        return value


class QuotaParsingTests(StatuslineCase):
    def test_modern_windows_and_monthly_ignored(self):
        quota = statusline.parse_quota({'usages': {
            'limit_5h': {'used_ratio': 0.15, 'reset_time': 'h'},
            'limit_7d': {'used_ratio': '0.81', 'reset_time': 'w'},
            'limit_month_total': {'used_ratio': 0.99, 'reset_time': 'm'},
        }})
        self.assertEqual(quota['h5_used'], 0.15)
        self.assertEqual(quota['wk_used'], 0.81)
        self.assertEqual(quota['h5_reset'], 'h')
        self.assertNotIn('mo_used', quota)

    def test_legacy_fallback_is_independent(self):
        quota = statusline.parse_quota({
            'usage': {'used': 81, 'limit': 100, 'resetTime': 'old-w'},
            'limits': [{'window': {'duration': 300, 'timeUnit': 'TIME_UNIT_MINUTE'},
                        'detail': {'used': 15, 'limit': 100, 'resetTime': 'old-h'}}],
            'usages': {'limit_5h': {'used_ratio': 'bad'}, 'limit_7d': {'used_ratio': 0}},
        })
        self.assertEqual(quota['h5_used'], 15)
        self.assertEqual(quota['h5_limit'], 100)
        self.assertEqual(quota['wk_used'], 0)
        self.assertEqual(quota['wk_limit'], 1.0)

    def test_bad_values_do_not_poison_other_window(self):
        for bad in ('oops', None, True, -0.1, float('nan'), float('inf'), [], {}):
            quota = statusline.parse_quota({'usages': {
                'limit_5h': {'used_ratio': bad}, 'limit_7d': {'used_ratio': 0.25}}})
            self.assertNotIn('h5_used', quota)
            self.assertEqual(quota['wk_used'], 0.25)

    def test_no_valid_window_returns_none(self):
        self.assertIsNone(statusline.parse_quota({'usages': {'limit_month_total': {'used_ratio': 0.5}}}))
        self.assertIsNone(statusline.parse_quota([]))

    def test_overuse_keeps_actual_percentage(self):
        cache = self.cache(h5_used=1.2, h5_limit=1.0)
        rendered = statusline.render_quota(cache, self.env)
        self.assertIn('120%', rendered)


class RenderTests(StatuslineCase):
    def test_only_5h_and_7d_are_rendered(self):
        cache = self.cache(h5_used=15, h5_limit=100, wk_used=80, wk_limit=100,
                           h5_reset='2099-01-01T00:00:00Z', mo_used=0.9, mo_limit=1)
        rendered = statusline.render_quota(cache, self.env)
        self.assertIn('5h', rendered)
        self.assertIn('15%', rendered)
        self.assertIn('7d', rendered)
        self.assertIn('80%', rendered)
        self.assertNotIn('mo', rendered)
        self.assertNotIn('90%', rendered)
        self.assertNotIn('git', rendered)

    def test_placeholders_and_environment_isolation(self):
        rendered = statusline.render_quota(self.cache(), self.env)
        self.assertEqual(rendered, '5h — · 7d —')
        other = dict(self.env, key='other-environment')
        self.assertEqual(statusline.render_quota(self.cache(h5_used=1, h5_limit=1), other),
                         '5h — · 7d —')

    def test_stale_marker(self):
        cache = self.cache(fetched_at=time.time() - 601, h5_used=0.5, h5_limit=1)
        self.assertIn('~50%', statusline.render_quota(cache, self.env))

    def test_reset_hint(self):
        now = int(time.time())
        reset = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now + 3 * 86400))
        self.assertEqual(statusline.reset_hint(reset, now), '3d0h')
        self.assertEqual(statusline.reset_hint('bad', now), '')

    def test_main_does_not_persist_or_echo_stdin(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({'version': 'test', 'cwd': '/tmp/\x1b]52;c;U1VDQ0VTUw==\x07',
                                            'gitBranch': 'main', 'model': 'secret-model'}))
        old_refresh = statusline.maybe_refresh
        statusline.maybe_refresh = lambda *args: False
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                statusline.main()
        finally:
            sys.stdin = old_stdin
            statusline.maybe_refresh = old_refresh
        self.assertEqual(output.getvalue().strip(), '5h — · 7d —')
        self.assertNotIn('secret-model', output.getvalue())
        self.assertNotIn(']52', output.getvalue())
        self.assertFalse(os.path.exists(os.path.join(statusline.HOME, 'statusline-stdin.json')))


class EndpointTests(StatuslineCase):
    def test_official_endpoints(self):
        for base in ('https://api.kimi.com/coding/v1', 'https://api.kimi.ai/coding/v1/',
                     'HTTPS://API.KIMI.COM/coding/v1'):
            self.write_config(base)
            environment = statusline.resolve_environment()
            self.assertIsNotNone(environment)
            self.assertTrue(environment['url'].endswith('/coding/v1/usages'))

    def test_scoped_oauth_key(self):
        key = 'oauth/kimi-code-env-0123456789abcdef'
        self.write_config('https://api.kimi.ai/coding/v1', key)
        environment = statusline.resolve_environment()
        self.assertTrue(environment['cred_file'].endswith('kimi-code-env-0123456789abcdef.json'))

    def test_rejected_urls_and_keys(self):
        urls = ('http://api.kimi.com/coding/v1', 'https://evil.example/coding/v1',
                'https://<REDACTED_PASSWORD>:<REDACTED_PASSWORD>@api.kimi.com/coding/v1',
                'https://api.kimi.com:444/coding/v1', 'https://api.kimi.com/other',
                'https://api.kimi.com/coding/v1?x=1', 'not-a-url')
        for url in urls:
            self.write_config(url)
            self.assertIsNone(statusline.resolve_environment(), url)
        for key in ('oauth/../../secret', 'oauth/kimi-code-env-xyz', '../kimi-code', 'oauth/kimi-code/extra'):
            self.write_config(oauth_key=key)
            self.assertIsNone(statusline.resolve_environment(), key)

    def test_fetch_uses_bearer_and_parses(self):
        payload = b'{"usages":{"limit_5h":{"used_ratio":0.25},"limit_7d":{"used_ratio":0.5}}}'
        opener = FakeOpener(payload)
        statusline.OPENER = opener
        quota = statusline.fetch_official('test', self.env)
        self.assertEqual(quota['h5_used'], 0.25)
        request = opener.calls[0][0]
        self.assertEqual(request.full_url, self.env['url'])
        self.assertEqual(request.headers['Authorization'], 'Bearer FAKE_TOKEN')
        self.assertEqual(opener.calls[0][1], statusline.REQUEST_TIMEOUT_S)

    def test_expired_or_invalid_credentials_do_not_open_network(self):
        opener = FakeOpener()
        statusline.OPENER = opener
        self.write_cred(expires_at=time.time() - 1)
        self.assertIsNone(statusline.fetch_official(environment=self.env))
        self.write_cred()
        with open(self.env['cred_file'], 'w') as f:
            json.dump([], f)
        self.assertIsNone(statusline.fetch_official(environment=self.env))
        self.assertEqual(opener.calls, [])

    def test_response_size_limit(self):
        statusline.OPENER = FakeOpener(b'x' * (statusline.MAX_RESPONSE_BYTES + 1))
        self.assertIsNone(statusline.fetch_official(environment=self.env))

    def test_redirect_is_not_followed_or_forwarded(self):
        target_calls = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                target_calls.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        class Redirect(BaseHTTPRequestHandler):
            target = ''

            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', type(self).target)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *args):
                pass

        target = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        redirect = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever, daemon=True)
                   for server in (target, redirect)]
        for thread in threads:
            thread.start()
        try:
            Redirect.target = f'http://127.0.0.1:{target.server_address[1]}/stolen'
            request = urllib.request.Request(
                f'http://127.0.0.1:{redirect.server_address[1]}/redirect',
                headers={'Authorization': 'Bearer FAKE_TOKEN'})
            opener = urllib.request.build_opener(statusline.NoRedirectHandler)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                opener.open(request, timeout=2)
            caught.exception.close()
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(target_calls, [])
        finally:
            for server in (redirect, target):
                server.shutdown()
                server.server_close()


class CacheAndActivityTests(StatuslineCase):
    def test_successful_refresh_writes_restricted_cache_without_token(self):
        self.write_config()
        old_fetch = statusline.fetch_official
        statusline.fetch_official = lambda *args: {'h5_used': 0.1, 'h5_limit': 1.0}
        try:
            cache = statusline.refresh_cache()
        finally:
            statusline.fetch_official = old_fetch
        self.assertGreater(cache['fetched_at'], 0)
        with open(statusline.CACHE) as f:
            raw = f.read()
        self.assertNotIn('FAKE_TOKEN', raw)
        self.assertNotIn('access_token', raw)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(statusline.CACHE).st_mode), 0o600)

    def test_failed_refresh_preserves_data_but_updates_attempt(self):
        self.write_config()
        old_time = time.time() - 1000
        with open(statusline.CACHE, 'w') as f:
            json.dump(self.cache(attempt_at=old_time, fetched_at=old_time,
                                 h5_used=0.4, h5_limit=1.0), f)
        old_fetch = statusline.fetch_official
        statusline.fetch_official = lambda *args: None
        try:
            cache = statusline.refresh_cache()
        finally:
            statusline.fetch_official = old_fetch
        self.assertEqual(cache['fetched_at'], old_time)
        self.assertEqual(cache['h5_used'], 0.4)
        self.assertGreater(cache['attempt_at'], old_time)

    def test_fresh_cache_does_not_spawn(self):
        old_popen = statusline.subprocess.Popen
        statusline.subprocess.Popen = lambda *args, **kwargs: self.fail('unexpected Popen')
        try:
            self.assertFalse(statusline.maybe_refresh(self.cache(), self.env))
        finally:
            statusline.subprocess.Popen = old_popen

    def test_concurrent_terminals_spawn_only_one_refresh(self):
        cache = self.cache(attempt_at=0)
        calls = []
        old_popen = statusline.subprocess.Popen

        class Process:
            pass

        def popen(command, **kwargs):
            calls.append(command)
            return Process()

        statusline.subprocess.Popen = popen
        try:
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(lambda _: statusline.maybe_refresh(cache, self.env), range(40)))
        finally:
            statusline.subprocess.Popen = old_popen
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(calls), 1)
        statusline.release_lock(calls[0][3])

    def test_failed_popen_releases_owned_lock(self):
        old_popen = statusline.subprocess.Popen
        statusline.subprocess.Popen = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('no spawn'))
        try:
            self.assertFalse(statusline.maybe_refresh(self.cache(attempt_at=0), self.env))
        finally:
            statusline.subprocess.Popen = old_popen
        self.assertFalse(os.path.exists(statusline.LOCK))

    def test_stale_lock_is_replaced(self):
        os.makedirs(statusline.HOME, exist_ok=True)
        with open(statusline.LOCK, 'w') as f:
            f.write('old')
        old = time.time() - statusline.LOCK_S - 1
        os.utime(statusline.LOCK, (old, old))
        calls = []
        old_popen = statusline.subprocess.Popen
        statusline.subprocess.Popen = lambda command, **kwargs: calls.append(command) or object()
        try:
            self.assertTrue(statusline.maybe_refresh(self.cache(attempt_at=0), self.env))
        finally:
            statusline.subprocess.Popen = old_popen
        statusline.release_lock(calls[0][3])

    def test_only_lock_owner_can_release(self):
        os.makedirs(statusline.HOME, exist_ok=True)
        token = statusline.acquire_lock()
        statusline.release_lock('wrong')
        self.assertTrue(os.path.exists(statusline.LOCK))
        statusline.release_lock(token)
        self.assertFalse(os.path.exists(statusline.LOCK))


class InstallerTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Проверка относится только к POSIX sh')
    def test_posix_shell_metacharacters_are_inert(self):
        with tempfile.TemporaryDirectory() as root:
            canary = os.path.join(root, 'SHELL_COMMAND_RAN')
            directory = os.path.join(root, 'plugin;touch ' + canary + ';#')
            target = os.path.join(directory, 'statusline.py')
            os.makedirs(directory)
            with open(target, 'w') as f:
                f.write('print("ok")\n')
            line = install.build_command(target, os_name='posix')
            command = tomllib.loads('[status_line]\n' + line)['status_line']['command']
            result = subprocess.run(['sh', '-c', command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'ok')
            self.assertFalse(os.path.exists(canary))

    def test_install_uninstall_and_runtime_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            tui = os.path.join(root, 'tui.toml')
            target = os.path.join(root, 'plugin with spaces', 'statusline.py')
            os.makedirs(os.path.dirname(target))
            open(target, 'w').close()
            self.assertEqual(install.install(tui, target, doctor=False), 0)
            self.assertEqual(install.install(tui, target, doctor=False), 0)
            self.assertEqual(uninstall.uninstall(tui, os.path.dirname(target), doctor=False), 0)
            with open(tui) as f:
                self.assertNotIn('statusline.py', f.read())
            for name in uninstall.RUNTIME_FILES:
                open(os.path.join(root, name), 'w').close()
            uninstall.cleanup_runtime(root)
            for name in uninstall.RUNTIME_FILES:
                self.assertFalse(os.path.exists(os.path.join(root, name)))

    def test_manifest_has_no_hooks(self):
        path = os.path.join(os.path.dirname(__file__), '..', 'kimi.plugin.json')
        with open(path, encoding='utf-8') as f:
            manifest = json.load(f)
        self.assertEqual(manifest['version'], '2.0.0')
        self.assertNotIn('hooks', manifest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
