# codex-quota-monitor 操作手册

> 适用范围：本手册按用户 `hsiaowei` 当前这台 Mac 的实际安装路径编写。插件已安装在个人 marketplace `personal` 中。

## 1. 插件用途

`codex-quota-monitor` 是一个 macOS 菜单栏额度监控插件，用于查看：

- Codex 周额度剩余百分比、刷新时间和刷新倒计时
- 今日 Tokens（这台 Mac 的本机实时数据）
- 昨日官方 Tokens；如果昨日是周六或周日，则显示上周五
- 本周 Tokens：官方历史数据 + 今日实时数据
- 本月 Tokens：官方历史数据 + 今日实时数据
- ChatGPT 套餐、credits 余额和额度重置券

所有 Token 数值以“万”为单位，保留一位小数并四舍五入。

## 2. 日常使用

### 2.1 在 Codex 中打开

新建一个 Codex 任务，然后输入：

> 打开 Codex 额度菜单栏

顶部菜单栏出现 `C 剩余百分比` 后，点击它即可展开额度窗口。再次点击，或点击窗口外部，可收起窗口。

### 2.2 手动刷新

打开额度窗口，点击右上角的“刷新”按钮。

程序还会每 5 分钟自动刷新一次。周额度倒计时每 30 秒更新一次。

### 2.3 退出

打开额度窗口，点击右上角的“退出”按钮。

## 3. 终端命令

插件源目录固定为：

```text
/Users/hsiaowei/Workspace/codex-quota-monitor
```

### 3.1 启动菜单栏

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py
```

正常提示：

```text
已打开 Codex 额度菜单栏。点击顶部的“C …%”可以展开或收起额度面板。
```

### 3.2 停止菜单栏

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --stop
```

### 3.3 重启菜单栏

当前启动器没有单独的 `--restart` 参数。重启时依次执行下面两条命令：

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --stop
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py
```

第一条命令关闭现有程序，第二条命令重新打开程序。

### 3.4 强制重建并重启

如果修改过插件、界面没有更新，或菜单栏程序无法正常打开，执行：

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --stop
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --rebuild
```

`--rebuild` 会重新编译菜单栏应用，然后自动打开。

强制重建要求系统已安装 Xcode Command Line Tools。可用下面的命令检查：

```bash
xcrun clang --version
```

能显示版本信息即可；普通启动和普通重启不需要重新编译。

### 3.5 在终端查看额度

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/codex_quota.py
```

### 3.6 查看机器可读的 JSON

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/codex_quota.py --json
```

默认会遮住部分邮箱地址。如果明确需要显示完整邮箱，可运行：

```bash
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/codex_quota.py --show-email
```

### 3.7 确认程序是否正在运行

```bash
pgrep -x CodexQuotaMenu
```

显示进程编号表示程序正在运行；没有结果表示程序未运行。

## 4. 重新安装插件

如果 Codex 中找不到插件，或更新后新任务仍加载旧版本，执行：

```bash
codex plugin add codex-quota-monitor@personal
```

这条命令要求个人 marketplace `personal` 已存在；当前这台 Mac 已经配置完成。

安装完成后，新建一个 Codex 任务，再输入：

> 打开 Codex 额度菜单栏

## 5. 数据口径

### 今日 Tokens

从这台 Mac 的本机 Codex 会话 Token 数值事件实时累计，不包含其他电脑、网页端或尚未同步的云端任务。

### 昨日或上周五

读取官方每日用量数据。若昨日是周六或周日，则自动回退到上周五。官方尚未返回指定日期时显示“暂无数据”，不会显示成 0。

### 本周和本月

显示为：

```text
本周：150.1万（官方历史） + 50.1万（今日实时）
本月：350.1万（官方历史） + 50.1万（今日实时）
```

官方当天数据不会再次加入，以免和今日实时数据重复计算。

## 6. 常见问题

### 菜单栏没有出现

先执行重启命令。如果仍未出现，再执行“强制重建并重启”命令。

### 显示“读取失败”

确认 Codex 已使用 ChatGPT 账号登录，然后点击“刷新”。也可以在终端运行额度查看命令，读取详细错误信息。

### 昨日显示“暂无数据”

这表示官方接口尚未返回该日期的数据，不代表实际使用量为 0。

### 今日数值与官方数据不同

今日是本机实时口径，官方数据是账户历史口径，两者范围和更新时间不同。周/月统计会明确拆分显示，不会把两种来源混成一个不透明的数字。

### 更新插件后界面还是旧版

依次执行：

```bash
codex plugin add codex-quota-monitor@personal
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --stop
python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --rebuild
```

然后新建一个 Codex 任务。

## 7. 最常用命令速查

| 操作 | 命令 |
|---|---|
| 启动 | `python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py` |
| 停止 | `python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/launch_menu_bar.py --stop` |
| 重启 | 先运行停止命令，再运行启动命令 |
| 强制重建并重启 | 先运行停止命令，再运行带 `--rebuild` 的启动命令 |
| 查看额度 | `python3 /Users/hsiaowei/Workspace/codex-quota-monitor/scripts/codex_quota.py` |
| 重新安装 | `codex plugin add codex-quota-monitor@personal` |

注意：`--stop` 会关闭所有名称为 `CodexQuotaMenu` 的进程。通常只会有一个实例。
