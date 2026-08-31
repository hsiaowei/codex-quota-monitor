#!/bin/sh

set -eu

script_path=$0
while [ -L "$script_path" ]; do
    script_dir=$(CDPATH= cd -P -- "$(dirname -- "$script_path")" && pwd)
    link_target=$(readlink "$script_path")
    case "$link_target" in
        /*) script_path=$link_target ;;
        *) script_path=$script_dir/$link_target ;;
    esac
done

script_dir=$(CDPATH= cd -P -- "$(dirname -- "$script_path")" && pwd)
launcher=$script_dir/launch_menu_bar.py
plugin_root=$(CDPATH= cd -P -- "$script_dir/.." && pwd)
manifest=$plugin_root/.codex-plugin/plugin.json
info_plist=$plugin_root/macos/Info.plist

if [ ! -f "$launcher" ]; then
    printf '%s\n' "错误：找不到 Codex 额度菜单栏启动器：$launcher" >&2
    exit 2
fi

usage() {
    printf '%s\n' \
        "用法：codex-use start|stop|restart|status|version" \
        "" \
        "  start    启动 Codex 额度菜单栏" \
        "  stop     停止 Codex 额度菜单栏" \
        "  restart  重启 Codex 额度菜单栏" \
        "  status   查看是否正在运行" \
        "  version  显示插件和菜单栏应用版本"
}

show_version() {
    plugin_version=$(python3 -c \
        'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' \
        "$manifest" 2>/dev/null) || plugin_version=未知
    plugin_display_version=${plugin_version%%+*}
    app_version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info_plist" 2>/dev/null) || app_version=未知
    app_build=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$info_plist" 2>/dev/null) || app_build=未知
    printf '%s\n' \
        "codex-quota-monitor v$plugin_display_version" \
        "CodexQuotaMenu v$app_version (build $app_build)"
}

case "${1:-}" in
    start)
        exec python3 "$launcher"
        ;;
    stop)
        exec python3 "$launcher" --stop
        ;;
    restart)
        python3 "$launcher" --stop
        exec python3 "$launcher"
        ;;
    status)
        if pgrep -x CodexQuotaMenu >/dev/null 2>&1; then
            printf '%s\n' "Codex 额度菜单栏正在运行。"
        else
            printf '%s\n' "Codex 额度菜单栏当前没有运行。"
            exit 1
        fi
        ;;
    version|-v|--version)
        show_version
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
