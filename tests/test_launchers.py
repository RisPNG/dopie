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
    assert 'runtime/linux/.setup-complete' in shell
    assert 'setsid -f "$PYTHON"' in shell
    assert 'nohup "$PYTHON"' in shell
    assert "</dev/null >/dev/null 2>&1" in shell
    assert '"--no-cache-dir"' in (root / "bootstrap" / "bootstrap.py").read_text(encoding="utf-8")
    assert [path.name for path in root.glob("*.sh")] == ["start-dopie.sh"]
    assert [path.name for path in root.glob("*.vbs")] == ["Start DoPie.vbs"]
    subprocess.run(["sh", "-n", str(root / "start-dopie.sh")], check=True)
