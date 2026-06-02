#!/usr/bin/env bash
# ============================================================================
#  grab_vnc_screenshot.sh —— 将服务器 VNC 桌面截图取回本机
# ============================================================================
#
#  背景：SCUT 服务器上可用的截图工具仅有 gnome-screenshot（无 ImageMagick /
#  scrot / gm），本机 macOS 也常无 ImageMagick 用于 xwd→png 中转。因此采用：
#  通过 SSH 调用 gnome-screenshot 截取 VNC 桌面，再以 scp 取回本机。
#
#  用法：
#     ./grab_vnc_screenshot.sh <user@host> <DISPLAY> [输出目录]
#
#  示例：
#     ./grab_vnc_screenshot.sh <学号>@<服务器> :1 ~/Documents/shots
#
#  - <DISPLAY> 为 VNC 桌面号（形如 :1；对应 X socket /tmp/.X11-unix/X1）。
#  - 使用标准 SSH（端口 22），与桥接的隧道端口无关。
#  - gnome-screenshot 可能输出 "Unable to use GNOME Shell's builtin ... fallback
#    X11" 警告，可忽略。
# ============================================================================
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "用法: $0 <user@host> <DISPLAY 如 :1> [输出目录]" >&2
  exit 1
fi

TARGET="$1"            # user@host
DISPLAY_NUM="$2"       # 例如 :1
OUTDIR="${3:-.}"
mkdir -p "$OUTDIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
REMOTE_TMP="/tmp/scut_shot_${STAMP}.png"
LOCAL_OUT="${OUTDIR%/}/vnc-${STAMP}.png"

echo "[1/2] 在 ${TARGET} 的 DISPLAY=${DISPLAY_NUM} 上截图 ..."
ssh -p 22 "$TARGET" "DISPLAY=${DISPLAY_NUM} gnome-screenshot -f '${REMOTE_TMP}'"

echo "[2/2] 拉回本机 -> ${LOCAL_OUT}"
scp -P 22 "${TARGET}:${REMOTE_TMP}" "$LOCAL_OUT"
ssh -p 22 "$TARGET" "rm -f '${REMOTE_TMP}'" || true

echo "完成: ${LOCAL_OUT}"
