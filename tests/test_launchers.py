from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_launchers_use_the_shared_verified_runtime_manifest():
    root = Path(__file__).parents[1]
    runtime = json.loads((root / "bootstrap" / "runtime.json").read_text(encoding="utf-8"))
    shell = (root / "start-dopie.sh").read_text(encoding="utf-8")
    windows = (root / "bootstrap" / "Start DoPie.ps1").read_text(encoding="utf-8")
    visual_basic = (root / "Start DoPie.vbs").read_text(encoding="utf-8")

    assert runtime["linux"]["sha256"] not in shell
    assert runtime["windows"]["sha256"] not in windows
    assert "bootstrap/runtime.json" in shell
    assert "bootstrap\\runtime.json" in windows
    assert not (root / "Start DoPie.ps1").exists()
    assert not (root / "Start DoPie.cmd").exists()
    assert "bootstrap" in visual_basic
    assert "Start DoPie.ps1" in visual_basic
    assert 'command & " -PrepareOnly", 1, True' in visual_basic
    assert ".setup-complete" in visual_basic
    assert "shell.Run command, 0, False" in visual_basic
    assert "param([switch]$PrepareOnly)" in windows
    assert "--prepare-only" in windows
    assert "DOPIE_SETUP_TERMINAL" in shell
    assert "xdg-terminal-exec" in shell
    assert 'bootstrap/bootstrap.py" --prepare-only' in shell
    assert 'RUNTIME="${XDG_CACHE_HOME:-$HOME/.cache}/dopie/runtime"' in shell
    assert 'SETUP_MARKER="$RUNTIME/.setup-complete"' in shell
    assert 'setsid -f "$PYTHON"' in shell
    assert 'nohup "$PYTHON"' in shell
    assert "</dev/null >/dev/null 2>&1" in shell
    bootstrap = (root / "bootstrap" / "bootstrap.py").read_text(encoding="utf-8")
    assert '"--no-cache-dir"' in bootstrap
    assert '"--target"' in bootstrap
    assert "import venv" not in bootstrap
    assert shell.index("umask 002") < shell.index("mkdir")
    assert 'mktemp -d "$RUNTIME/.setup-XXXXXX"' in shell
    assert "$ROOT/runtime" not in shell
    assert "mv -T" in shell
    assert "runtime/linux/MsPy.zip" not in shell
    assert "[guid]::NewGuid()" in windows
    assert 'Join-Path $env:LOCALAPPDATA "DoPie\\runtime"' in windows
    assert 'Write-Host "Downloading and verifying the DoPie runtime..."' in windows
    assert 'Write-Host "Preparing the DoPie application environment..."' in windows
    assert 'Read-Host "DoPie setup failed. Press Enter to close"' in windows
    assert '"%LOCALAPPDATA%"), "DoPie"), "runtime"), ".setup-complete"' in visual_basic
    assert "[System.IO.Directory]::Move" in windows
    assert "runtime\\windows\\MsPy.zip" not in windows
    assert [path.name for path in root.glob("*.sh")] == ["start-dopie.sh"]
    assert [path.name for path in root.glob("*.vbs")] == ["Start DoPie.vbs"]
    subprocess.run(["sh", "-n", str(root / "start-dopie.sh")], check=True)
