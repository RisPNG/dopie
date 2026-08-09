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
SETUP_MARKER="$ROOT/runtime/linux/.setup-complete"
if [ ! -f "$SETUP_MARKER" ] && [ "${DOPIE_SETUP_TERMINAL:-}" != "1" ] && [ ! -t 1 ]; then
    if command -v xdg-terminal-exec >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 xdg-terminal-exec sh "$0"
        exit 0
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 x-terminal-emulator -e sh "$0"
        exit 0
    elif command -v gnome-terminal >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 gnome-terminal -- sh "$0"
        exit 0
    elif command -v konsole >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 konsole -e sh "$0"
        exit 0
    elif command -v mate-terminal >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 mate-terminal -- sh "$0"
        exit 0
    elif command -v kitty >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 kitty sh "$0"
        exit 0
    elif command -v alacritty >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 alacritty -e sh "$0"
        exit 0
    elif command -v foot >/dev/null 2>&1; then
        DOPIE_SETUP_TERMINAL=1 foot sh "$0"
        exit 0
    fi
fi
if [ ! -x "$PYTHON" ]; then
    printf 'Downloading and verifying the DoPie runtime...\n'
    mkdir -p "$ROOT/runtime/linux"
    curl -fL "$URL" -o "$ARCHIVE"
    printf '%s  %s\n' "$SHA256" "$ARCHIVE" | sha256sum -c -
    unzip -q "$ARCHIVE" -d "$ROOT/runtime/linux"
    rm "$ARCHIVE"
fi
if [ ! -f "$SETUP_MARKER" ]; then
    printf 'Preparing the DoPie application environment...\n'
    "$PYTHON" "$ROOT/bootstrap/bootstrap.py" --prepare-only
    printf 'ready\n' > "$SETUP_MARKER"
    printf 'Setup complete. Starting DoPie...\n'
fi
if command -v setsid >/dev/null 2>&1; then
    setsid -f "$PYTHON" "$ROOT/bootstrap/bootstrap.py" </dev/null >/dev/null 2>&1
else
    nohup "$PYTHON" "$ROOT/bootstrap/bootstrap.py" </dev/null >/dev/null 2>&1 &
fi
exit 0
