# codex-quota-monitor 会话交接文档

更新日期：2026-09-28

仓库：`/Users/hsiaowei/Workspace/codex-quota-monitor`

GitHub：<https://github.com/hsiaowei/codex-quota-monitor>

## 1. 文档目的

本文档用于在关闭当前 Codex 会话后继续维护 `codex-quota-monitor`。它记录项目已经确认的产品规则、版本演进、关键实现、当前 Git 与本机安装状态、最新故障的根因和修复，以及下一会话应继续完成的工作。

## 2. 当前状态摘要

- `v0.9.1` 在 `v0.9.0` CLI 路径兼容修复基础上增加订阅有效期卡片、菜单栏双额度显示，以及设置订阅日期后自动重启菜单栏的行为。
- 本次发布流程会把 `v0.9.1` 提交并推送到 GitHub 的 `origin/main`。
- 本机 Codex 插件缓存已经重新安装为 `0.9.1+codex.20260928051613`。
- 原生菜单栏程序已经重新构建为 `CodexQuotaMenu v0.9.1 (build 19)`。
- 当前受限执行环境无法连接 macOS LaunchServices，自动打开应用返回 `kLSServerCommunicationErr`；源码与应用已构建完成，回到普通终端运行 `codex-use restart` 即可启动。
- 48 项 Python 单元测试全部通过，插件清单校验和 Skill 校验均通过，`git diff --check` 通过。
- 当前受限执行环境无法连接 macOS LaunchServices，因此无法在本会话内真正打开菜单栏应用。用户需要在普通 macOS 终端执行 `codex-use restart`。

## 3. 项目目标与最终产品形态

该项目是 macOS 原生菜单栏 Codex 额度监控组件，同时提供 Codex 插件 Skill 和终端脚本。菜单栏状态项在两个窗口都存在时显示 `5h 82% · 周 94%`，点击后展开额度面板。

主要功能：

1. 显示真实 Codex 5 小时额度和周额度：剩余百分比、已用百分比、重置时间和倒计时。
2. 固定选择官方 `limitId = codex` 的额度桶，不得误选 `base_model_inference`、`gpt-reserve` 等备用桶。
3. 本机实时计算今日 Tokens。
4. 显示昨日官方 Tokens；周末回退时显示上周五。
5. 显示本周和本月 Tokens，并拆分成“官方历史 + 今日实时”。
6. 显示“今日消耗”，即本机当天观察到的周额度 `usedPercent` 上涨量。
7. 官方历史接口失败时使用上一次成功缓存，并明确标注缓存状态。
8. 额度为 100% 时按既定条件执行一次最小 Codex 请求，固定额度窗口的重置时间，并防止重复触发。
9. 通过 `codex-use start|stop|restart|status|version|subscription` 管理菜单栏应用和订阅到期日。

## 4. 已确认的数据与显示规则

### 4.1 5 小时额度与周额度

- 5 小时额度来自官方 300 分钟窗口。
- 周额度来自官方 10080 分钟窗口。
- 两个区块使用相同布局：标题左上、放大的剩余百分比右上、进度条居中、已用百分比左下、倒计时右下。
- 两个区块之间保留间距并显示细分隔线。
- 菜单栏状态项同时显示可用的 5 小时和周额度；缺少某个窗口时自动只显示现有额度。
- 周额度标题显示为类似：`周额度（今日消耗：约4%）`。
- 重置倒计时根据官方 `resetsAt` 计算；它不是缓存历史数据，因此不因官方历史 Tokens 缓存而标黄。

### 4.2 今日 Tokens

- 今日 Tokens 由本机 Codex 活动会话和归档会话中的数值事件实时累计。
- 对跨目录的同一事件去重，并保存单会话最大值与累计检查点，防止 Codex 升级、重启、归档、迁移或日志截断后今日统计回退。
- 本机缓存：`~/.codex/codex-quota-monitor/daily-local-token-cache.json`。
- 只统计本机可观察到的数据，不包含其他电脑、网页端或尚未同步的云端任务。

### 4.3 昨日或上周五

- 平日显示“昨日”。
- 如果昨日为周六或周日，则回退显示“上周五”。
- 官方指定日期尚无数据时显示“暂无数据”，不得显示为 `0`。
- “上周五”不是固定字段名，而是顶部官方对比日期行在周末回退时的标签。

### 4.4 官方历史缓存

官方历史接口不可用而本机已有成功缓存时：

- `ⓘ`、缓存时间只显示在“昨日/上周五”这一行。
- 文案格式为：`数据缓存时间 MM-dd HH:mm:ss`，使用本地时间。
- 点击 `ⓘ`，说明“官方接口当前不可用，黄色数据来自本机缓存”。
- 所有来自缓存的官方数据改成黄色：昨日/上周五数值、本周的“官方历史”、本月的“官方历史”。
- “今日实时”继续使用正常颜色。
- 官方接口恢复后，黄色、`ⓘ` 和缓存时间全部自动消失。
- 首次运行且没有缓存时显示“暂无数据”，不显示 `0`。
- 缓存文件：`~/.codex/codex-quota-monitor/official-usage-cache.json`。

### 4.5 本周与本月

显示格式：

```text
本周：150.1万（官方历史） + 50.1万（今日实时）
本月：350.1万（官方历史） + 50.1万（今日实时）
```

- 周/月合计只把今日以前的官方历史与今日实时相加，官方当天数据不得重复加入。
- Tokens 不足 1 亿时以“万”为单位，保留一位小数并四舍五入。
- 达到 1 亿时显示“亿 + 万”，例如 `1亿2345.6万`。
- 余下万数为零时只显示整数亿，例如 `2亿`，不得显示 `2亿0.0万`。

### 4.6 今日周额度消耗

- 持续观察官方周额度 `usedPercent`。
- 百分比上涨计入今日累计；滚动窗口释放旧用量造成的下降不扣减。
- 因官方百分比为整数精度且插件停止期间可能漏记，显示时必须带“约”。
- 缓存文件：`~/.codex/codex-quota-monitor/daily-weekly-quota-cache.json`。

### 4.7 订阅有效期卡片（v0.9.1）

- 卡片位于 5 小时额度区块下方、“额度重置券”上方，并用细分隔线与额度区块分开。
- 视觉采用浅绿色圆角卡片：日历图标、左侧“订阅有效期 N天”、右侧本地日期 `yyyy-MM-dd`。
- 当前官方 app-server 的 `account/read` 和 `account/rateLimits/read` 没有承诺返回 Plus/Pro 订阅到期日；缺少数据时必须显示“暂无数据”。
- `rateLimitResetCredits.credits[].expiresAt` 只属于额度重置券，严禁把它显示成订阅到期日。
- 可从未来官方字段读取，也可使用 `CODEX_QUOTA_SUBSCRIPTION_EXPIRY_DAY` 或应用偏好 `subscriptionExpiryDay` 补充本机真实日期；官方值优先。
- 本机只设置日（1–31）：设置日小于今天日期数字时归到下个月，否则归到本月；不存在该日的月份会继续顺延，到期日当天仍计为有效。
- 推荐使用 `codex-use subscription 17` 设置、`codex-use subscription` 查看、`codex-use subscription clear` 清除；设置或清除后菜单栏会自动重启，无需再手动执行 `restart`。旧版完整时间仅保留兼容读取。

## 5. 最小 Token 请求规则

### 5.1 触发时机

以下三种成功刷新后都要检查：

1. 菜单栏应用启动后的首次刷新。
2. 用户点击手动刷新。
3. 每 5 分钟自动刷新。

30 秒定时器只更新倒计时和界面，不执行额度接口刷新，也不触发最小请求。

### 5.2 触发条件

- 官方返回 5 小时额度时，只看 5 小时额度。
- 5 小时剩余为 100% 时执行一次最小请求。
- 即使周额度为 100%，只要 5 小时额度不是 100%，就不得执行。
- 只有官方完全没有返回 5 小时窗口时，才回退检查周额度是否为 100%。

### 5.3 请求内容与模型

- 固定使用 `gpt-5.5`。
- 命令通过 `codex exec --json --model gpt-5.5 --sandbox read-only` 执行。
- 提示词为：`不要调用任何工具，只回复 OK。`
- 使用只读沙箱、跳过 Git 仓库检查、忽略用户配置，不使用额度重置券。
- 成功后自动归档临时任务；Token 事件仍计入今日 Tokens。
- 成功后弹出 macOS 系统通知，让用户知道已执行最小消耗。

### 5.4 防重复逻辑（v0.8.3）

- 使用文件锁，避免多个刷新路径并发触发。
- 发起请求前先写入 15 分钟临时抑制时间，防止请求尚未完成时另一路径再次触发。
- 成功后，5 小时窗口至少抑制 5 小时，周额度回退至少抑制 7 天。
- 如果官方 `resetsAt` 更晚，则抑制到该时间。
- 过期或缺失的 `resetsAt` 不得缩短最小冷却期。
- 请求失败才使用 15 分钟重试冷却。
- 状态文件：`~/.codex/codex-quota-monitor/quota-keepalive.json`。
- 可用环境变量 `CODEX_QUOTA_KEEPALIVE=0` 临时禁用。

## 6. 定时任务与刷新机制

当前菜单栏程序包含两个固定定时器和一个实时观察通道：

1. 每 30 秒：更新 5 小时和周额度倒计时，不请求官方接口。
2. 每 5 分钟：执行完整额度刷新，并检查是否需要最小 Token 请求。
3. `account/rateLimits/updated`：监听 app-server 的额度变化通知，用于及时更新额度与“今日消耗”。

手动刷新和启动首次刷新走同一套完整刷新与最小请求检查流程。

## 7. 版本演进

本地已有标签：`v0.4.1`、`v0.5.0`、`v0.5.1`、`v0.6.1`、`v0.6.2`、`v0.7.1`、`v0.7.2`、`v0.7.3`、`v0.8.0`、`v0.8.1`、`v0.8.2`、`v0.8.3`。

近期版本重点：

- `v0.7.3`：修复额度桶选择，固定使用官方 `codex` 桶；为 `codex-use` 增加 `version`。
- `v0.8.0`：在启动、手动刷新和每 5 分钟刷新后检查 100% 额度并执行最小请求。
- `v0.8.1`：最小请求成功后增加 macOS 系统通知；纠正此前误写的 `v8.0/v8.0.1` 命名。
- `v0.8.2`：优先以 5 小时额度为触发条件；周额度仅在缺失 5 小时窗口时回退；最小请求固定使用 GPT-5.5。
- `v0.8.3`：修复同一额度窗口重复执行最小请求的问题，增加并发锁、预抑制、成功最小冷却期和测试。
- `v0.9.0`：当前本地未发布版本；因 CLI 定位机制发生较大兼容性调整，将原计划的 `v0.8.4` 重新定义为 `v0.9.0`。
- `v0.9.1`：当前开发版本；在额度重置券上方增加订阅有效期卡片，并把菜单栏状态项改为同时显示 5 小时和周额度。

当前 Git 分支：

- `main`：本地和 `origin/main` 的已提交状态均停在 `v0.8.3` 提交 `43be99a`。
- `release/0.4.1` 至 `release/0.7.3`：存在本地及远端发布分支。
- `v0.8.0` 至 `v0.8.3`：本地存在版本标签。

## 8. v0.9.0 最新故障与修复

### 8.1 用户现象

升级 GPT/Codex 桌面应用后，菜单栏组件显示“找不到 Codex CLI”，无法读取额度。

### 8.2 根因

旧软链接：

```text
/usr/local/bin/codex -> /Applications/Codex.app/Contents/Resources/codex
```

已经失效。升级后的 CLI 位于：

```text
/Applications/Codex.app/Contents/Resources/codex-cli/bin/codex
/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex
```

旧组件只检查 `/usr/local/bin/codex`、`/opt/homebrew/bin/codex` 和菜单栏进程有限的 `PATH`，因此升级后找不到 CLI。

本次排查时观察到：

- Codex 桌面应用版本：`26.924.22138`。
- 内嵌 CLI 版本：`codex-cli 0.158.0-alpha.2.1`。
- `codex login status` 返回 `Logged in using ChatGPT`。

### 8.3 已实现修复

原生菜单栏、额度脚本和 keepalive 脚本现在依次检查：

1. `CODEX_QUOTA_CODEX_PATH` 显式路径。
2. 当前进程 `PATH`。
3. `~/.local/bin/codex`。
4. `/usr/local/bin/codex`。
5. `/opt/homebrew/bin/codex`。
6. 通过 macOS bundle id `com.openai.codex` 动态定位 Codex.app 内的新旧 CLI。
7. `/Applications/Codex.app` 内的新包装脚本、新二进制和旧路径。
8. `/Applications/ChatGPT.app` 中可能的内嵌 CLI 路径。

失效的旧软链接不会阻止继续检查后续候选路径。

### 8.4 修改文件

- `.codex-plugin/plugin.json`：版本升级为 `0.9.0`。
- `macos/Info.plist`：应用版本升级为 `0.9.0`，build `17`。
- `macos/CodexQuotaMenu.m`：统一原生菜单和额度观察器的 CLI 定位逻辑。
- `scripts/codex_quota.py`：增加新版、旧版和自定义路径发现。
- `scripts/quota_keepalive.py`：同步 CLI 路径发现逻辑。
- `scripts/test_codex_quota.py`：增加内嵌 CLI 回退与环境变量优先级测试。
- `scripts/test_quota_keepalive.py`：增加内嵌 CLI 回退测试。
- `README.md`：增加 v0.9.0 版本信息和“找不到 Codex CLI”排障说明。
- `skills/codex-quota/SKILL.md`：增加 CLI 路径兼容要求。

### 8.5 验证结果

```text
Ran 45 tests
OK
Built /Users/hsiaowei/Workspace/codex-quota-monitor/dist/CodexQuotaMenu.app
Plugin validation passed
Skill is valid!
```

在最小化 `PATH=/usr/bin:/bin` 的测试中，Python 组件仍能找到新版 Codex.app 内嵌 CLI，证明修复不依赖旧软链接。

### 8.6 v0.9.1 界面调整

- 弹窗高度从 470 增加到 540 点，为订阅有效期卡片保留完整空间，不压缩现有额度区块。
- 订阅卡片位于额度重置券上方；显示剩余天数和到期时间，无数据时显示“暂无数据 / 官方未提供”。
- 菜单栏状态项选择紧凑的 `5h 82% · 周 94%`，比两个无标签百分比更容易辨认；只返回一个窗口时退化为单项。
- 实时额度通知会与上一次完整快照合并，因此更新周额度时保留 5 小时值，更新 5 小时额度时也保留周额度值。

## 9. 当前已知限制与独立网络问题

路径问题已经修复，但本次受限执行环境中直接调用新版 `codex app-server` 时还观察到网络发送失败：

- `account/read`：`workspace routing discovery failed`。
- `account/rateLimits/read`：请求 ChatGPT 额度端点时发送失败。
- `account/usage/read`：请求 Token 使用档案端点时发送失败。

同时，`scutil --proxy` 显示 macOS HTTP、HTTPS、SOCKS 和 PAC 代理均未启用。因此这属于路径修复以外的网络/代理状态问题。若菜单栏重启后错误从“找不到 Codex CLI”变为接口或网络错误，应先开启 Clash Verge 系统代理，再点击刷新。

当前执行环境还无法连接 macOS LaunchServices，`open dist/CodexQuotaMenu.app` 返回 `kLSServerCommunicationErr`。这只是当前 Codex 受限环境无法操作图形会话，不代表应用构建失败。

## 10. 当前本机安装状态

- marketplace：`codex-quota-monitor-local`
- marketplace 根目录：`/Users/hsiaowei/Workspace/codex-quota-monitor`
- 已安装插件：`codex-quota-monitor@codex-quota-monitor-local`
- 已安装缓存版本：`0.9.1+codex.20260928051613`
- 安装缓存目录：`~/.codex/plugins/cache/codex-quota-monitor-local/codex-quota-monitor/0.9.1+codex.20260928051613`
- 源码正式版本保持 `0.9.1`，不会把一次性 cachebuster 写回正式版本号。
- `codex-use` 路径：`/usr/local/bin/codex-use`
- `codex-use version` 输出：

```text
codex-quota-monitor v0.9.1
CodexQuotaMenu v0.9.1 (build 19)
```

插件安装或更新后，需要新建 Codex 会话才能加载新 Skill；旧会话不会中途重新载入插件。

## 11. 后续验证与发布检查

### 11.1 在普通终端验证

```bash
codex-use restart
```

确认菜单栏重新出现，并验证不再显示“找不到 Codex CLI”。

如果出现网络错误：

1. 开启 Clash Verge 系统代理。
2. 运行 `codex login status`，确认使用 ChatGPT 登录。
3. 运行 `python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py"` 查看详细错误。
4. 再运行 `codex-use restart`。

设置订阅日期时会自动重启，无需另外执行重启命令：

```bash
codex-use subscription 26
```

### 11.2 v0.9.1 发布检查

发布前执行：

```bash
cd "$HOME/Workspace/codex-quota-monitor"
git status --short
python3 -m unittest discover -s scripts -p 'test_*.py'
./scripts/build_menu_bar_app.sh
git diff --check
```

审核差异后提交并推送：

```bash
git add .codex-plugin/plugin.json README.md macos/Info.plist \
  macos/CodexQuotaMenu.m scripts/codex_quota.py \
  scripts/quota_keepalive.py scripts/test_codex_quota.py \
  scripts/test_quota_keepalive.py skills/codex-quota/SKILL.md \
  doc/session-handoff-2026-09-28.md
git commit -m "feat: add subscription card and dual quota status in v0.9.1"
git push origin main
```

推送前应再次确认没有覆盖用户的其他未提交修改。不要读取、打印或提交任何 Codex 登录令牌和认证文件。

## 12. 常用命令

```bash
# 查看版本
codex-use version

# 启动、停止、重启、查看状态
codex-use start
codex-use stop
codex-use restart
codex-use status

# 终端读取额度
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py"
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py" --json

# 完整测试
cd "$HOME/Workspace/codex-quota-monitor"
python3 -m unittest discover -s scripts -p 'test_*.py'

# 构建原生菜单栏程序
./scripts/build_menu_bar_app.sh

# 检查插件
codex plugin marketplace list
codex plugin list
```

## 13. 关键源码入口

- `macos/CodexQuotaMenu.m`：原生菜单栏界面、额度读取、定时器、实时通知、刷新和最小请求调度。
- `scripts/codex_quota.py`：终端额度读取、额度桶选择、本机今日 Tokens、官方历史和缓存统计。
- `scripts/quota_keepalive.py`：100% 额度最小请求、防重复与冷却逻辑。
- `scripts/codex-use.sh`：菜单栏启动、停止、重启、状态与版本命令。
- `scripts/launch_menu_bar.py`：构建和打开原生应用。
- `scripts/test_codex_quota.py`：额度、Tokens、缓存、CLI 路径与版本相关测试。
- `scripts/test_quota_keepalive.py`：最小请求触发、优先级、防重复与冷却测试。
- `skills/codex-quota/SKILL.md`：Codex 插件对话能力和安全约束。
- `README.md`：完整安装、使用、升级、排障和卸载手册。

## 14. 安全与维护约束

- 不读取、不输出、不复制、不解析 Codex 认证文件或令牌。
- 官方账号和额度数据只通过本机 `codex app-server` 获取。
- 不把本机缓存、构建缓存、登录信息或用户会话内容提交到 Git。
- 处理 Git 时保留用户已有修改；禁止使用 `git reset --hard` 等破坏性命令。
- 修改原生 UI 后必须重新构建；更新插件内容后必须重新安装缓存并新建 Codex 会话。
- app-server 是内部依赖点，Codex 升级后应优先重新验证 CLI 路径、初始化协议、`account/read`、`account/rateLimits/read` 和 `account/usage/read`。
