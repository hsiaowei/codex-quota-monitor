---
name: codex-quota
description: Read and display the user's real Codex five-hour and weekly usage limits, estimated weekly-quota consumption accumulated today, local real-time tokens for today, official prior-workday usage, weekly and monthly token statistics, remaining percentages, reset times, plan, credit balance, and available rate-limit reset credits in chat or a native macOS menu bar popover. Use when the user asks about Codex quota, five-hour quota, today's weekly-quota consumption, today's tokens, yesterday's usage, weekly/monthly token statistics, usage allowance, weekly limits, remaining capacity, refresh/reset time, a quota menu bar item, or says 查看额度/五小时额度/5小时额度/今日周额度消耗/今日Tokens/昨日用量/周统计/月统计/周额度/额度刷新/打开额度菜单栏.
---

# Codex Quota

Use the bundled script to retrieve live account limits from the local Codex
app-server. Do not estimate quota from conversation length or token count. The
script may persist only official daily numeric usage buckets and their successful
fetch time for outage fallback; it must never cache authentication material.

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

When the repository's `scripts/codex-use.sh` has been linked as `codex-use`,
the equivalent user-facing commands are `codex-use start`, `codex-use stop`,
`codex-use restart`, and `codex-use status`.

## Safety and accuracy

- Never consume a rate-limit reset credit automatically.
- Never open, print, copy, or parse Codex authentication files or tokens.
- The app-server owns authentication and returns only account metadata and quota
  state needed for the report.
- Prefer `rateLimitsByLimitId` when present; the script handles this selection.
- Read today's tokens from both active and archived local `token_count` session
  events, deduplicate events that appear in both locations, and sum only
  `last_token_usage.total_tokens` whose event timestamp is on the current local
  calendar day. Preserve each session's largest observed daily numeric total in
  the local daily cache so a Codex update or restart cannot make today's value
  go backwards when a session file is moved, truncated, or temporarily
  unavailable. Use numeric cumulative-token checkpoints to add later growth if
  a resumed session log contains only the post-restart segment. This is a
  local-device total, not an account-wide estimate.
- Read the comparison day from the exact official `dailyUsageBuckets` date. If
  yesterday is Saturday or Sunday, use the preceding Friday. If that exact
  official bucket is missing, display `暂无数据`; never turn a missing bucket into
  zero.
- After a successful official daily-usage response, cache only its date/token
  map and the local successful-fetch timestamp. If that API is unavailable,
  reuse the last cache, mark all cached official values yellow, and show `ⓘ`
  plus `（数据缓存时间MM-dd HH:mm:ss）` only on the comparison row. Clicking
  `ⓘ` must explain that the official API is unavailable and the yellow values
  come from local cache. Keep today's local value in its normal color. Clear all
  cache indicators automatically as soon as live official data returns.
- If neither live official data nor a cache exists, display `暂无数据` for the
  comparison, weekly official, and monthly official values; never display zero
  for missing data.
- Weekly and monthly token statistics equal official historical daily buckets
  before today plus today's local real-time total. Never add the official
  current-day bucket, because that would double-count today.
- Display token counts below 100,000,000 in units of `万`. At or above
  100,000,000, split them into `亿` plus the remaining `万`, for example
  `1亿2345.6万`. Keep exactly one decimal place on the `万` portion and use
  round-half-up behavior. Omit the `万` portion when its rounded remainder is
  zero, so 200,000,000 displays as `2亿`, not `2亿0.0万`.
- Local session files may be parsed only for event timestamps, event types, and
  numeric token counters. The daily local cache may contain only the local date,
  session filename, numeric Token totals/cumulative checkpoints, and update
  timestamp. Never display, save, or inspect prompt or response contents.
- Treat `usedPercent` as authoritative. Remaining percentage is `100-usedPercent`.
- Treat an official 300-minute window as the `5 小时额度`. Display its used
  and remaining percentages, reset time, and countdown separately from the
  10,080-minute weekly window. If the API does not return it, display `暂无数据`;
  never synthesize a five-hour quota. In the macOS popover, use the same visual
  hierarchy for both windows: title at upper left, large remaining percentage
  at upper right, progress bar, used percentage at lower left, countdown at
  lower right, and reset time beneath. Separate the two blocks with whitespace
  and a thin divider.
- Estimate today's weekly-quota consumption by locally accumulating only positive
  changes in the official weekly `usedPercent`. Do not subtract decreases caused
  by rolling-window recovery. Listen for `account/rateLimits/updated` in the menu
  app and retain the five-minute snapshot refresh as fallback. Persist only the
  local date, numeric percentage snapshots, accumulated increase, and timestamps;
  never persist authentication data. Label this daily result with `约`, reset it
  on the next local calendar day, and explain that the first day begins when
  tracking is enabled. Display it inside the weekly quota heading, for example
  `周额度（今日消耗：约2%）`, instead of as a separate row.
- A five-hour window is 300 minutes and a weekly window is 10,080 minutes.
  Other returned windows must also be shown.
- If Codex returns no weekly window, say so; do not invent one.
- If the command is blocked from accessing local Codex state, retry it with a
  narrowly scoped approval for this script. If it still fails, report the exact
  error and suggest signing into Codex with ChatGPT-managed authentication.
- If the user asks to refresh, run the script again rather than reusing old data.
