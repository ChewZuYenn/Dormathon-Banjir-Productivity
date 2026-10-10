#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/xuanyuwu/.workbuddy-ai/binaries/python/envs/default/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    print "Prepared isolated Python not found; set it up per ../godot-open-and-integration-guide.txt."
    read "?Press Enter to close"
    exit 1
fi
exec "$PYTHON" "$HERE/server.py" --port 8765
