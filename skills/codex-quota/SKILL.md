---
name: codex-quota
description: Read and display the user's real Codex five-hour and weekly usage limits, estimated weekly-quota consumption accumulated today, local real-time tokens for today, official prior-workday usage, weekly and monthly token statistics, remaining percentages, reset times, plan, subscription-expiration status, credit balance, and available rate-limit reset credits in chat or a native macOS menu bar popover. Use when the user asks about Codex quota, five-hour quota, today's weekly-quota consumption, today's tokens, yesterday's usage, weekly/monthly token statistics, usage allowance, weekly limits, remaining capacity, refresh/reset time, subscription validity, a quota menu bar item, or says 查看额度/五小时额度/5小时额度/今日周额度消耗/今日Tokens/昨日用量/周统计/月统计/周额度/额度刷新/订阅有效期/打开额度菜单栏.
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
state. Tell the user to click the quota percentages in the menu bar to expand or
collapse the quota panel. When both official windows exist, the status item uses
the compact form `5h 82% · 周 94%`; when only one exists, show only that window.
The panel opens below the item, refreshes
automatically every five minutes, and has manual refresh and quit buttons.
When the bundled `SessionStart` hook has been reviewed and trusted, it starts
the menu bar app asynchronously for local macOS sessions whose start source is
`startup` or `resume`. It must first check for an existing `CodexQuotaMenu`
process and skip launching when one already exists. Hook failure must never
block or fail the Codex session. The user can review, trust, or disable the hook
with `/hooks`; installing or enabling the plugin must not be described as
implicitly trusting it.
After any successful quota refresh—startup, manual, or the five-minute automatic
refresh—the app gives the official five-hour window priority. When that window
is present, launch one minimal real `codex exec --model gpt-5.5` request only if
its remaining percentage is 100; a weekly window at 100 must not trigger while
the five-hour window is below 100. Only fall back to a 100-percent weekly window
when the official response contains no five-hour window. Track cooldowns until
the triggering window resets so repeated refreshes do not consume again. After
a successful request, suppress the five-hour window for at least five hours and
the weekly fallback for at least seven days, extending to a later official
future reset time when present. Never shorten a successful cooldown because
`resetsAt` is stale, expired, or missing. Retry a failed request no sooner than
15 minutes.
After the minimal request succeeds, deliver a native macOS notification telling
the user that a 100% quota window was detected and one minimal Token consumption
was completed to anchor the reset time. Never send this success notification for
cooldown, not-needed, disabled, or failed results. Request notification permission
through the system when needed and present the banner even while the menu app is
foreground.

If the launcher says the menu app is already running, do not start another
copy. To stop it when the user explicitly asks, run:

```bash
python3 <plugin-root>/scripts/launch_menu_bar.py --stop
```

When the repository's `scripts/codex-use.sh` has been linked as `codex-use`,
the equivalent user-facing commands are `codex-use start`, `codex-use stop`,
`codex-use restart`, `codex-use status`, and `codex-use version`. The version
command prints both the plugin version and the native menu bar app version/build.

## Safety and accuracy

- Never consume a rate-limit reset credit automatically.
- The 100%-window keepalive must use `codex exec --model gpt-5.5` with a read-only
  sandbox, no tool calls, and a reply-only-`OK` prompt. Do not use an ephemeral
  session: archive the temporary session after completion so its numeric Token
  event remains available to today's local count. Persist only numeric attempt,
  success, reset/cooldown timestamps and window names in
  `~/.codex/codex-quota-monitor/quota-keepalive.json`; never save prompt,
  response, or authentication content. Honor `CODEX_QUOTA_KEEPALIVE=0` as an
  opt-out.
- After a successful keepalive, enforce a minimum cooldown equal to the
  triggering window duration: five hours for `five-hour`, seven days for the
  `weekly` fallback. A valid later official `resetsAt` may extend that cooldown,
  but stale, expired, or missing reset data must never reduce it. Keep the
  15-minute cooldown only for failed requests.
- Never print, copy, cache, log, or expose Codex authentication files or tokens.
  The native menu bar app has one narrow exception: it may read
  `~/.codex/auth.json` (or `$CODEX_HOME/auth.json`), take only
  `tokens.id_token`, decode its JWT payload in memory, and retain only the
  parsed subscription-expiration date. It must discard the token and payload
  immediately and must not inspect unrelated claims.
- Show the subscription-validity card above reset credits. Use an official
  subscription-expiration field only when app-server actually returns one.
  Never reinterpret `rateLimitResetCredits.credits[].expiresAt` as a plan or
  subscription expiry. When app-server returns no subscription expiration,
  read only the namespaced JWT claim
  `https://api.openai.com/auth.chatgpt_subscription_active_until` from
  `tokens.id_token`. Never use the ordinary JWT `exp` claim because it is the
  login-token expiration, not the subscription expiration. Display
  `暂无数据` when the dedicated claim is missing or invalid. Do not provide or
  document a manual subscription-date override. Use the local calendar for the
  inclusive remaining-day count and display the local expiration time through
  the minute as `yyyy-MM-dd HH:mm`.
- Locate the Codex CLI from `CODEX_QUOTA_CODEX_PATH`, the process `PATH`,
  standalone install locations such as `~/.local/bin`, Homebrew locations, and
  both current and legacy CLI paths embedded in `Codex.app`. A stale legacy
  `/usr/local/bin/codex` symlink must not prevent falling back to the current
  bundled CLI.
- The app-server owns authentication and returns only account metadata and quota
  state needed for the report.
- Prefer the official `codex` entry in `rateLimitsByLimitId`, then the official
  top-level `rateLimits` fallback. Ignore reserve buckets such as `gpt-reserve`
  and `base_model_inference` even when they expose the same 300-minute or
  10,080-minute windows; five-hour and weekly displays must come from the same
  Codex quota bucket.
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
