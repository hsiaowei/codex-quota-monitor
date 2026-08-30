#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
plugin_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
app_dir="$plugin_root/dist/CodexQuotaMenu.app"
contents_dir="$app_dir/Contents"
binary_dir="$contents_dir/MacOS"
resources_dir="$contents_dir/Resources"
build_dir="$plugin_root/.build"
module_cache=$(mktemp -d "${TMPDIR:-/tmp}/codex-quota-module-cache.XXXXXX")
trap 'rm -rf "$module_cache"' EXIT

mkdir -p "$binary_dir" "$resources_dir" "$build_dir"
xcrun clang \
  -O \
  -fobjc-arc \
  -fmodules \
  -fmodules-cache-path="$module_cache" \
  -framework Cocoa \
  "$plugin_root/macos/CodexQuotaMenu.m" \
  -o "$binary_dir/CodexQuotaMenu"
cp "$plugin_root/macos/Info.plist" "$contents_dir/Info.plist"
cp "$plugin_root/scripts/quota_keepalive.py" "$resources_dir/quota_keepalive.py"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - "$app_dir" >/dev/null
fi

echo "Built $app_dir"
