# codex-quota-monitor 安装与操作手册

`codex-quota-monitor` 是一个适用于 macOS 的 Codex 额度监控插件，可在原生菜单栏弹窗和 Codex 对话中显示真实 5 小时额度、周额度、刷新时间以及 Token 使用统计。

仓库地址：[github.com/hsiaowei/codex-quota-monitor](https://github.com/hsiaowei/codex-quota-monitor)
<img width="381" height="405" alt="image" src="https://github.com/user-attachments/assets/4644852e-b345-4da5-96ca-6bd96dfd076e" />

## 1. 功能

- Codex 5 小时额度与周额度的剩余百分比、已用百分比、刷新时间和倒计时
- 今日周额度消耗：实时累计官方周额度 `usedPercent` 的上涨量
- 今日 Tokens：根据这台 Mac 的本机 Codex 会话实时累计
- 昨日官方 Tokens；如果昨日是周六或周日，则显示上周五
- 本周与本月 Tokens：官方历史数据 + 今日本机实时数据
- ChatGPT 套餐、credits 余额和额度重置券
- 官方用量接口不可用时，自动显示上次成功获取的本机缓存
- Token 不足 1 亿时以“万”显示；达到 1 亿后按“亿 + 万”分段显示，例如 `1亿2345.6万`。余下的万数为 0 时直接显示 `2亿`，小数保留一位并四舍五入

## 2. 完整安装

以下步骤适用于一台尚未安装本插件的 Mac。建议按顺序执行，不要跳过“安装前检查”。

### 2.1 系统和软件要求

| 项目 | 要求 | 检查命令 |
|---|---|---|
| 操作系统 | macOS 13 或更高版本 | `sw_vers -productVersion` |
| Codex CLI | 必须可在终端运行；额度接口依赖本机 `codex app-server` | `codex --version` |
| Codex 登录 | 必须使用 ChatGPT 账号登录；API Key 登录不提供此插件所需的 ChatGPT 额度 | `codex login status` |
| Git | 用于下载和更新项目 | `git --version` |
| Python | Python 3.10 或更高版本 | `python3 --version` |
| Xcode Command Line Tools | 首次构建原生菜单栏应用需要 | `xcrun clang --version` |

如果最后一条命令提示找不到开发工具，执行：

```bash
xcode-select --install
```

完成系统弹窗中的安装后，再次运行 `xcrun clang --version`。Xcode Command Line Tools 通常也会提供 Git；如果 `git --version` 仍失败，请参考 [Git 官方安装说明](https://git-scm.com/download/mac)。

如果 `codex --version` 失败，请先按 [OpenAI Codex CLI 官方说明](https://learn.chatgpt.com/docs/codex/cli) 安装或更新 CLI。如果 `python3 --version` 低于 3.10，请从 [Python 官方网站](https://www.python.org/downloads/macos/) 安装新版 Python。

`codex login status` 应显示 `Logged in using ChatGPT`。如果尚未登录，请先运行 `codex login` 并按提示完成 ChatGPT 登录。

Codex 插件和 marketplace 的机制可参考 [OpenAI Plugins 文档](https://developers.openai.com/plugins/)。

### 2.2 下载项目

建议把项目固定放在 `$HOME/Workspace/codex-quota-monitor`，后续的快捷命令会使用这个稳定路径：

```bash
mkdir -p "$HOME/Workspace"
git clone https://github.com/hsiaowei/codex-quota-monitor.git "$HOME/Workspace/codex-quota-monitor"
cd "$HOME/Workspace/codex-quota-monitor"
```

如果目录已经存在，不要再次克隆。执行以下命令核对仓库来源：

```bash
git -C "$HOME/Workspace/codex-quota-monitor" remote get-url origin
```

结果应包含 `hsiaowei/codex-quota-monitor`。如果它指向其他项目，请不要覆盖该目录，先在 Finder 中确认并处理路径冲突。

### 2.3 注册本地插件市场

仓库自带标准 marketplace 文件 `.agents/plugins/marketplace.json`。执行：

```bash
codex plugin marketplace add "$HOME/Workspace/codex-quota-monitor"
```

然后检查：

```bash
codex plugin marketplace list
```

列表中应出现：

```text
codex-quota-monitor-local
```

这一步只需要执行一次。它让 Codex 知道从哪个本地仓库读取插件，不需要手动修改 `~/.codex/config.toml`。

如果提示同名 marketplace 已存在，先用 `codex plugin marketplace list` 核对其 `ROOT`。ROOT 正确指向当前仓库时无需重复添加；ROOT 错误时，按“常见问题”中的 marketplace 路径修复步骤处理。

### 2.4 安装插件

```bash
codex plugin add codex-quota-monitor@codex-quota-monitor-local
```

检查安装结果：

```bash
codex plugin list
```

应能看到 `codex-quota-monitor@codex-quota-monitor-local`，状态为 `installed, enabled`。

### 2.5 安装 `codex-use` 快捷命令

默认使用系统公共命令目录。终端询问管理员密码时，输入过程不会显示字符，这是 macOS 的正常行为：

```bash
sudo mkdir -p /usr/local/bin
sudo ln -s "$HOME/Workspace/codex-quota-monitor/scripts/codex-use.sh" /usr/local/bin/codex-use
```

验证：

```bash
command -v codex-use
codex-use --help
```

正常情况下，第一条命令返回 `/usr/local/bin/codex-use`，第二条命令显示 `start`、`stop`、`restart` 和 `status`。

如果 `ln` 提示 `File exists`，先运行：

```bash
ls -l /usr/local/bin/codex-use
```

如果它已经指向当前仓库中的 `scripts/codex-use.sh`，无需处理；如果指向旧目录，先执行 `sudo unlink /usr/local/bin/codex-use`，再重新运行上面的 `ln -s` 命令。

如果没有管理员权限，可以改用个人命令目录：

```bash
mkdir -p "$HOME/.local/bin"
ln -s "$HOME/Workspace/codex-quota-monitor/scripts/codex-use.sh" "$HOME/.local/bin/codex-use"
```

然后在 `~/.zshrc` 中加入以下一行，并重新打开终端：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

正常 Git 克隆会保留脚本的执行权限。只有运行时出现 `Permission denied`，才需要执行：

```bash
chmod +x "$HOME/Workspace/codex-quota-monitor/scripts/codex-use.sh"
```

### 2.6 首次启动

```bash
codex-use start
```

首次启动会自动编译原生菜单栏应用，可能需要几秒钟。成功后会显示：

```text
已打开 Codex 额度菜单栏。点击顶部的“C …%”可以展开或收起额度面板。
```

macOS 顶部菜单栏会出现 `C …%`。点击它即可展开额度面板。

### 2.7 完成安装验证

依次执行：

```bash
codex-use status
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py"
codex plugin list
```

确认以下结果：

1. `codex-use status` 显示菜单栏正在运行。
2. Python 命令能打印 Codex 实际额度，而不是登录或权限错误。
3. `codex plugin list` 显示插件已安装并启用。

最后关闭当前 Codex 任务并新建一个任务，再输入：

> 打开 Codex 额度菜单栏

插件安装后必须新建任务，已有任务不会在中途重新加载新插件。

如果新任务仍看不到插件，请完全退出并重新打开 Codex 桌面应用，然后再次新建任务。插件不支持 Codex IDE 扩展中的插件浏览与安装。

## 3. 日常使用

### 3.1 展开和收起

点击 macOS 顶部菜单栏的 `C 剩余百分比` 即可展开额度窗口。再次点击，或点击窗口外部，可收起窗口。

### 3.2 手动刷新

打开额度窗口，点击右上角的“刷新”按钮。程序会监听 app-server 的额度变化通知，并每 5 分钟自动补查一次；5 小时额度和周额度倒计时每 30 秒更新一次。

### 3.3 退出

打开额度窗口，点击右上角的“退出”按钮，或者运行：

```bash
codex-use stop
```

注意：当前停止命令按进程名关闭 `CodexQuotaMenu`。如果同时运行了多个项目副本，它们会一起停止。

## 4. `codex-use` 命令

### 启动

```bash
codex-use start
```

### 停止

```bash
codex-use stop
```

### 重启

```bash
codex-use restart
```

### 查看状态

```bash
codex-use status
```

### 强制重建并重启

修改过原生界面、普通重启没有更新，或者应用无法正常打开时执行：

```bash
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --stop
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --rebuild
```

## 5. 在终端查看额度

显示中文额度卡片：

```bash
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py"
```

显示机器可读 JSON：

```bash
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py" --json
```

默认会遮住部分邮箱地址。明确需要完整邮箱时执行：

```bash
python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py" --show-email
```

## 6. 更新与重新安装

### 6.1 更新源码

```bash
cd "$HOME/Workspace/codex-quota-monitor"
git pull --ff-only
```

### 6.2 重新安装插件缓存

先移除已安装的缓存副本，再从已更新的本地 marketplace 安装：

```bash
codex plugin remove codex-quota-monitor@codex-quota-monitor-local
codex plugin add codex-quota-monitor@codex-quota-monitor-local
```

如果 `remove` 提示插件尚未安装，可以忽略该提示，继续运行 `add`。

### 6.3 重建菜单栏并新建任务

```bash
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --stop
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --rebuild
```

然后完全退出并重新打开 Codex 桌面应用，再新建任务，确保 Codex 加载刚安装的插件版本。

## 7. 数据口径

### 5 小时额度

直接读取官方额度接口返回的 300 分钟窗口，并独立显示剩余百分比、已用百分比、重置时间和倒计时。菜单栏弹窗中，5 小时额度与周额度采用相同布局：标题在左上、放大的剩余百分比在右上、进度条位于中间、已用百分比在左下、倒计时在右下，刷新时间位于区块底部；两个额度区块之间留有间距并使用一条细分隔线。该数据不根据 Tokens 推算，也不会与周额度混合；如果官方接口没有返回 300 分钟窗口，则显示“暂无数据”。菜单栏状态项 `C 百分比` 仍表示周额度剩余百分比。

### 今日 Tokens

从这台 Mac 的本机 Codex 活动会话与归档会话 Token 数值事件实时累计，不包含其他电脑、网页端或尚未同步的云端任务。插件会对跨目录的同一事件去重，并把当天每个会话已观察到的最大数值累计和累计计数检查点保存在 `~/.codex/codex-quota-monitor/daily-local-token-cache.json`。因此 Codex 升级或重启导致会话文件被迁移、截断、归档或暂时不可见时，今日数值不会回退，恢复后的新增用量也会继续累加；缓存只包含本地日期、会话文件名、Token 数值和更新时间，不包含对话内容或登录信息。

### 今日周额度消耗

插件在本机持续观察官方周额度 `usedPercent`：百分比上涨时计入今日累计，滚动窗口释放旧用量导致的下降不扣减。菜单栏优先监听 `account/rateLimits/updated` 实时通知，并通过手动刷新和每 5 分钟自动刷新补查。

显示在周额度标题内，不再单独占用一行：

```text
周额度（周额度消耗：约5%）                       95%
```

该数值来自官方周额度百分比的本机变化记录，但官方百分比仅提供整数精度，而且插件未运行期间可能漏掉变化，因此始终标记为“约”。首次启用或跨日后，以首次观察到的额度作为基线；完整统计从启用后的下一天开始更可靠。缓存位于 `~/.codex/codex-quota-monitor/daily-weekly-quota-cache.json`，只保存日期、数字百分比和本地时间戳，不保存登录信息。

### 昨日或上周五

读取官方每日用量数据。若昨日是周六或周日，则自动回退到上周五。官方尚未返回指定日期时显示“暂无数据”，不会显示成 0。

如果官方接口暂时不可用，但本机已有上次成功获取的数据：

- “昨日/上周五”数值、本周“官方历史”和本月“官方历史”会变成黄色
- `ⓘ` 和“数据缓存时间 MM-dd HH:mm:ss”只显示在“昨日/上周五”这一行
- 点击 `ⓘ` 可查看缓存来源说明
- 今日实时数据仍保持正常颜色
- 官方接口恢复后，黄色、`ⓘ` 和缓存时间会自动消失

首次运行且没有缓存时，所有缺失的官方数据均显示“暂无数据”，不会显示为 0。官方 Tokens 缓存位于 `~/.codex/codex-quota-monitor/official-usage-cache.json`，只保存每日 Token 数字和成功获取时间，不保存登录令牌。

### 本周和本月

```text
本周：150.1万（官方历史） + 50.1万（今日实时）
本月：350.1万（官方历史） + 50.1万（今日实时）
```

官方当天数据不会再次加入，以免和今日实时数据重复计算。

## 8. 常见问题

### `codex: command not found`

Codex CLI 尚未安装，或者不在终端的 `PATH` 中。先安装或更新 Codex，再运行 `codex --version` 验证。

### `codex-use: command not found`

重新执行“安装 `codex-use` 快捷命令”一节，并用 `command -v codex-use` 检查链接。

### marketplace 中找不到插件

```bash
codex plugin marketplace list
codex plugin list
```

确认 marketplace 名称是 `codex-quota-monitor-local`，仓库路径是 `$HOME/Workspace/codex-quota-monitor`。如果未注册，重新运行：

```bash
codex plugin marketplace add "$HOME/Workspace/codex-quota-monitor"
```

如果列表中已有 `codex-quota-monitor-local`，但 ROOT 指向旧目录，执行：

```bash
codex plugin remove codex-quota-monitor@codex-quota-monitor-local
codex plugin marketplace remove codex-quota-monitor-local
codex plugin marketplace add "$HOME/Workspace/codex-quota-monitor"
codex plugin add codex-quota-monitor@codex-quota-monitor-local
```

### 菜单栏没有出现

先运行 `codex-use restart`。如果仍未出现，再执行“强制重建并重启”。

### 显示“读取失败”

先运行 `codex login status`，确认显示 `Logged in using ChatGPT`，然后点击“刷新”。也可以运行终端额度命令查看详细错误。

### 昨日显示“暂无数据”

这表示官方接口没有返回该日期的数据，不代表实际使用量为 0。

### 官方历史数据显示为黄色

官方接口当前不可用，插件正在显示本机上次成功获取的官方数据。点击“昨日/上周五”行后的 `ⓘ` 可查看缓存时间。

### 今日数值与官方数据不同

今日是本机实时口径，官方数据是账户历史口径，两者范围和更新时间不同。周/月统计会明确拆分显示。

### 更新后界面还是旧版

重新安装插件、强制重建菜单栏，然后新建 Codex 任务：

```bash
codex plugin remove codex-quota-monitor@codex-quota-monitor-local
codex plugin add codex-quota-monitor@codex-quota-monitor-local
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --stop
python3 "$HOME/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py" --rebuild
```

完全退出并重新打开 Codex 桌面应用，然后新建任务。

### 仍然无法安装或启动

运行下面的诊断命令，并在提交 [GitHub Issue](https://github.com/hsiaowei/codex-quota-monitor/issues) 时附上输出。不要上传登录令牌或其他私密文件。

```bash
sw_vers -productVersion
codex --version
codex login status
python3 --version
xcrun clang --version
codex plugin marketplace list
codex plugin list
command -v codex-use
codex-use status
```

## 9. 卸载

先停止菜单栏：

```bash
codex-use stop
```

移除插件和本地 marketplace：

```bash
codex plugin remove codex-quota-monitor@codex-quota-monitor-local
codex plugin marketplace remove codex-quota-monitor-local
```

移除快捷命令：

```bash
readlink /usr/local/bin/codex-use
```

只有输出确实是 `$HOME/Workspace/codex-quota-monitor/scripts/codex-use.sh` 时，才执行：

```bash
sudo unlink /usr/local/bin/codex-use
```

如果安装在 `$HOME/.local/bin`，请改为检查并移除 `$HOME/.local/bin/codex-use`。

这些命令不会删除 `$HOME/Workspace/codex-quota-monitor` 源码目录，也不会删除 `~/.codex/codex-quota-monitor/official-usage-cache.json`。如需删除，可在 Finder 中确认路径后手动移到废纸篓。

## 10. 命令速查

| 操作 | 命令 |
|---|---|
| 注册 marketplace | `codex plugin marketplace add "$HOME/Workspace/codex-quota-monitor"` |
| 安装插件 | `codex plugin add codex-quota-monitor@codex-quota-monitor-local` |
| 启动菜单栏 | `codex-use start` |
| 停止菜单栏 | `codex-use stop` |
| 重启菜单栏 | `codex-use restart` |
| 查看状态 | `codex-use status` |
| 查看额度 | `python3 "$HOME/Workspace/codex-quota-monitor/scripts/codex_quota.py"` |
| 更新源码 | `git -C "$HOME/Workspace/codex-quota-monitor" pull --ff-only` |
| 重新安装 | 先 `codex plugin remove codex-quota-monitor@codex-quota-monitor-local`，再运行安装命令 |

注意：`codex-use stop` 会关闭所有名称为 `CodexQuotaMenu` 的进程，通常只会有一个实例。
