#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
GODOT="/Users/xuanyuwu/Downloads/Godot.app/Contents/MacOS/Godot"
if [[ ! -x "$GODOT" ]]; then
    print "未找到 Godot，请在项目管理器导入此目录内的 project.godot。"
    read "?按回车关闭"
    exit 1
fi
exec "$GODOT" --editor --path "$HERE"
