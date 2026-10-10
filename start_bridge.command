#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/xuanyuwu/.workbuddy-ai/binaries/python/envs/default/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    print "未找到已准备的隔离 Python，请按 Godot打开与接入说明.txt 配置环境。"
    read "?按回车关闭"
    exit 1
fi
exec "$PYTHON" "$HERE/server.py" --port 8765
