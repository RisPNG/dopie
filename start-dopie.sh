#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MANIFEST="$ROOT/bootstrap/runtime.json"
LINUX=$(sed -n '/"linux"[[:space:]]*:/,/^[[:space:]]*}/p' "$MANIFEST")
URL=$(printf '%s\n' "$LINUX" | sed -n 's/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
SHA256=$(printf '%s\n' "$LINUX" | sed -n 's/.*"sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
PYTHON_RELATIVE=$(printf '%s\n' "$LINUX" | sed -n 's/.*"python"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
PYTHON="$ROOT/runtime/linux/$PYTHON_RELATIVE"
ARCHIVE="$ROOT/runtime/linux/MsPy.zip"
if [ ! -x "$PYTHON" ]; then
    mkdir -p "$ROOT/runtime/linux"
    curl -fL "$URL" -o "$ARCHIVE"
    printf '%s  %s\n' "$SHA256" "$ARCHIVE" | sha256sum -c -
    unzip -q "$ARCHIVE" -d "$ROOT/runtime/linux"
    rm "$ARCHIVE"
fi
exec "$PYTHON" "$ROOT/bootstrap/bootstrap.py"
