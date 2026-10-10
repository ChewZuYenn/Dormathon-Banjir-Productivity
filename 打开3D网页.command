#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/xuanyuwu/.workbuddy-ai/binaries/python/versions/3.13.12/bin/python3"
print "网页地址：http://127.0.0.1:8788"
print "保持此窗口开启；按 Ctrl+C 关闭网页服务。"
print "如果提示端口已占用，先在浏览器打开上述地址，不要重复启动。"
exec "$PYTHON" -m http.server 8788 --bind 127.0.0.1 --directory "$HERE"
