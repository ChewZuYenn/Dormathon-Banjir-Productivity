#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
GODOT="/Users/xuanyuwu/Downloads/Godot.app/Contents/MacOS/Godot"
if [[ ! -x "$GODOT" ]]; then
    print "Godot not found; import project.godot from this folder in the Godot project manager."
    read "?Press Enter to close"
    exit 1
fi
exec "$GODOT" --editor --path "$HERE"
