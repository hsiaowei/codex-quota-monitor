---
name: codex-quota
description: Read and display the user's real Codex usage limits, local real-time tokens for today, official prior-workday usage, weekly and monthly token statistics, weekly quota, remaining percentage, reset time, plan, credit balance, and available rate-limit reset credits in chat or a native macOS menu bar popover. Use when the user asks about Codex quota, today's tokens, yesterday's usage, weekly/monthly token statistics, usage allowance, weekly limits, remaining capacity, refresh/reset time, a quota menu bar item, or says 查看额度/今日Tokens/昨日用量/周统计/月统计/周额度/额度刷新/打开额度菜单栏.
---

# Codex Quota

Use the bundled read-only script to retrieve live account limits from the local
Codex app-server. Do not estimate quota from conversation length or token count.

## Run

Resolve `../../scripts/codex_quota.py` relative to this `SKILL.md`, then run:

```bash
python3 <plugin-root>/scripts/codex_quota.py
```

The script prints a Chinese Markdown quota card. Return that output to the user
without changing percentages or reset times. You may make the surrounding prose
shorter, but keep the data exact.

When the user asks for machine-readable output, run:

```bash
python3 <plugin-root>/scripts/codex_quota.py --json
```

When the user explicitly asks to see the full account email, add `--show-email`.
Otherwise keep the default masked email.

## macOS menu bar

When the user asks to open, show, launch, or use the quota menu bar item,
resolve `../../scripts/launch_menu_bar.py` relative to this `SKILL.md`, then run:

```bash
python3 <plugin-root>/scripts/launch_menu_bar.py
```

The command launches a native macOS menu bar app. It may require a narrowly
scoped approval because it opens a local GUI and reads local Codex account
state. Tell the user to click the `C <percent>%` menu bar item to expand or
collapse the quota panel. The panel opens below the item, refreshes
automatically every five minutes, and has manual refresh and quit buttons.

If the launcher says the menu app is already running, do not start another
copy. To stop it when the user explicitly asks, run:

```bash
python3 <plugin-root>/scripts/launch_menu_bar.py --stop
```

## Safety and accuracy

- This skill is read-only. Never consume a rate-limit reset credit automatically.
- Never open, print, copy, or parse Codex authentication files or tokens.
- The app-server owns authentication and returns only account metadata and quota
  state needed for the report.
- Prefer `rateLimitsByLimitId` when present; the script handles this selection.
- Read today's tokens from local `token_count` session events and sum only
  `last_token_usage.total_tokens` whose event timestamp is on the current local
  calendar day. This is a local-device total, not an account-wide estimate.
- Read the comparison day from the exact official `dailyUsageBuckets` date. If
  yesterday is Saturday or Sunday, use the preceding Friday. If that exact
  official bucket is missing, display `暂无数据`; never turn a missing bucket into
  zero.
- Weekly and monthly token statistics equal official historical daily buckets
  before today plus today's local real-time total. Never add the official
  current-day bucket, because that would double-count today.
- Display all token counts in units of `万`, with exactly one decimal place and
  round-half-up behavior.
- Local session files may be parsed only for event timestamps, event types, and
  numeric token counters. Never display, save, or inspect prompt or response
  contents.
- Treat `usedPercent` as authoritative. Remaining percentage is `100-usedPercent`.
- A weekly window is 10,080 minutes. Other returned windows must also be shown.
- If Codex returns no weekly window, say so; do not invent one.
- If the command is blocked from accessing local Codex state, retry it with a
  narrowly scoped approval for this script. If it still fails, report the exact
  error and suggest signing into Codex with ChatGPT-managed authentication.
- If the user asks to refresh, run the script again rather than reusing old data.
