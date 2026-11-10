<div align="center">

<img src="assets/hero.svg" alt="Kimi Quota Statusline — official 5h and 7d quotas" width="760" />

<p><a href="README.ru-RU.md"><b>Документация на русском</b></a></p>

</div>

# Kimi Quota Statusline

A deliberately minimal [Kimi Code CLI](https://github.com/MoonshotAI/kimi-code) TUI status line: **official 5h and 7d quota bars only**.

- `5h` and `7d`: six cells, actual used percentage, and reset countdown.
- One shared cache with a **90-second refresh interval** across all terminals.
- Refreshes only while a visual Kimi TUI invokes the status line. No TUI means no requests.
- No background server, recurring loop, hooks, monthly quota, token/cost/TPS, git/cwd, swarm, or task dashboard.
- No session transcript, task log, or stdin snapshots are read or persisted.

## Install

In Kimi Code, run:

```text
/plugins install https://github.com/vvadik/kimi-quota-statusline
/kimi-quota-statusline:install
```

Then run `/reload-tui` or open a new TUI session. To pin a reviewed commit, use `https://github.com/vvadik/kimi-quota-statusline/commit/<sha>` as the install URL.

Manual alternative:

```bash
git clone https://github.com/vvadik/kimi-quota-statusline.git
python3 kimi-quota-statusline/install.py
```

Requirements: Kimi Code CLI with `[status_line]` support and Python 3 on macOS, Linux, or Windows.

## Network and cache

Only these official endpoints are accepted:

- `https://api.kimi.com/coding/v1/usages`
- `https://api.kimi.ai/coding/v1/usages`

HTTP, other hosts, non-standard ports, credential-bearing URLs, and all redirects are rejected. The plugin reads an existing OAuth `access_token` but never uses `refresh_token`, contacts an auth server, or changes credentials.

When the TUI calls `statusline.py`, a stale cache causes one short-lived `--refresh` process. An atomic owner-token lock prevents concurrent terminals from spawning duplicate refreshes. The process performs at most one request, writes the cache atomically with mode `0600`, and exits.

`attempt_at` limits both successful and failed attempts to one per 90 seconds. `fetched_at` changes only after valid data arrives. On failure, previous data is retained; after 10 minutes it is dimmed and marked with `~`.

## Uninstall

```text
/kimi-quota-statusline:uninstall
```

Or run `python3 uninstall.py` from the managed/source directory. The installer and uninstaller back up `tui.toml`; uninstall removes only this plugin's command, quota cache, and refresh lock.

### Upgrading from 1.6.2

Version 2.0.0 removes the old local dashboard and prompt hook. Reload plugins and the TUI after upgrading. If an old `statusline.py --tasks-server` was already running, inspect the PID in `~/.kimi-code/statusline-tasks.port`, verify its command line with `ps -p <pid> -o command=`, and terminate it only if it is the old statusline server. Do not kill a PID without checking it.

Old `statusline-stdin.json`, `statusline-hook-payloads.jsonl`, `statusline-tasks.html`, `statusline-tasks.port`, `statusline-tokens.json`, and `statusline-refresh.lock` can then be removed. They are not used by 2.0.0.

## Development

```bash
python3 tests/test_regressions.py
```

Tests use fake credentials and local fake HTTP servers; no real OAuth token or official API request is needed.

## License

[MIT](LICENSE)
