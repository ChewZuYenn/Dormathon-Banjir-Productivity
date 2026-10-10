#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/xuanyuwu/.workbuddy-ai/binaries/python/versions/3.13.12/bin/python3"
print "Page URL: http://127.0.0.1:8788"
print "Keep this window open; press Ctrl+C to stop the web server."
print "If the port is already in use, open the URL above instead of starting again."
exec "$PYTHON" -m http.server 8788 --bind 127.0.0.1 --directory "$HERE"
