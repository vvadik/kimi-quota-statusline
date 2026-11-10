<div align="center">

<img src="assets/hero.svg" alt="Kimi Quota Statusline — native status and remaining quotas" width="760" />

<p><a href="README.ru-RU.md"><b>Документация на русском</b></a></p>

</div>

# Kimi Quota Statusline

A minimal [Kimi Code CLI](https://github.com/MoonshotAI/kimi-code) TUI status line with native model/context information, useful activity markers, and remaining official quotas.

Active example:

```text
AUTO plan | K3.1 Pro·max | swarm | ctx:83% left | used:178.1k | ⚙ 2 | project | 5h 97% left 4h53m | mo 89% left 28d12h
```

Without plan/swarm/active tasks:

```text
YOLO | K3.1 Pro·max | ctx:83% left | used:178.1k | ⚙ 0 | project | 5h 97% left 4h53m | mo 89% left 28d12h
```

## Display

- Permission mode: `MANUAL` dim, `YOLO` green, `AUTO` red. These colors match the actual risk: Never Ask (`AUTO`) permits sensitive operations, while Ask When Needed (`YOLO`) still confirms them.
- `plan` in blue when Plan mode is active.
- Model and reasoning effort, such as `K3.1 Pro·max`.
- Blue `swarm` marker when swarm mode is active.
- `ctx` remaining, `used` tokens, and the short current directory name in the default terminal color.
- `⚙ N`: green when background tasks are running, dim when `N = 0`.
- `5h` and `7d` as **remaining percentage**, without a progress bar. If `7d` is unavailable, the official monthly total is shown as `mo`.

For example, `5h 97% left 4h53m` means 97% of the five-hour quota remains and the window resets in 4 hours 53 minutes. Usage above 100% is displayed as `0% left`. Data older than 10 minutes retains the `~` stale marker.

## Background tasks

The marker is intentionally read-only. Use Kimi's native interactive panel for details:

```text
/tasks
```

The upstream task browser supports arrow-key selection, output/activity preview, refresh, filtering, and stopping tasks. The plugin does not render its own HTML dashboard or expose task output.

Only `kind`, `status`, `pid`, and timing metadata from `tasks/*.json` is used for the marker. `output.log`, task commands/descriptions, and subagent transcripts are not read. Reasoning effort and swarm state require only `thinkingEffort` and `swarm_mode.enter/exit` records from the current session's `wire.jsonl`; nothing is persisted or sent anywhere.

## Install

In Kimi Code, run:

```text
/plugins install https://github.com/vvadik/kimi-quota-statusline
/kimi-quota-statusline:install
```

Then run `/reload-tui` or open a new TUI session. To pin a reviewed commit, use `https://github.com/vvadik/kimi-quota-statusline/commit/<sha>`.

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

When the TUI calls `statusline.py`, a stale cache causes one short-lived `--refresh` process. An atomic owner-token lock prevents concurrent terminals from spawning duplicate refreshes. The process performs at most one request, writes the cache atomically with mode `0600`, and exits. No TUI calls means no new requests.

`attempt_at` limits both successful and failed attempts to one per 90 seconds. `fetched_at` changes only after valid data arrives. On failure, previous data is retained; after 10 minutes it is dimmed and marked with `~`.

No background server, recurring loop, prompt hooks, token/cost/TPS accounting, git badge, or task HTML dashboard is used.

## Uninstall

```text
/kimi-quota-statusline:uninstall
```

Or run `python3 uninstall.py` from the managed/source directory. The installer and uninstaller back up `tui.toml`; uninstall removes only this plugin's command, quota cache, and refresh lock.

### Upgrading from 1.6.2

The old local dashboard and prompt hook were removed in 2.0.0. Reload plugins and the TUI after upgrading. If an old `statusline.py --tasks-server` is still running, inspect the PID in `~/.kimi-code/statusline-tasks.port`, verify its command line with `ps -p <pid> -o command=`, and terminate it only after confirming that it is the old statusline server.

Old `statusline-stdin.json`, `statusline-hook-payloads.jsonl`, `statusline-tasks.html`, `statusline-tasks.port`, `statusline-tokens.json`, and `statusline-refresh.lock` can then be removed. They are not used by current versions.

## Development

```bash
python3 tests/test_regressions.py
```

Tests use fake credentials and local fake HTTP servers; no real OAuth token or official API request is needed.

## License

[MIT](LICENSE)
