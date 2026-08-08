from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_launchers_use_the_shared_verified_runtime_manifest():
    root = Path(__file__).parents[1]
    runtime = json.loads((root / "bootstrap" / "runtime.json").read_text(encoding="utf-8"))
    shell = (root / "start-dopie.sh").read_text(encoding="utf-8")
    powershell = (root / "Start DoPie.ps1").read_text(encoding="utf-8")

    assert runtime["linux"]["sha256"] not in shell
    assert runtime["windows"]["sha256"] not in powershell
    assert "bootstrap/runtime.json" in shell
    assert "bootstrap\\runtime.json" in powershell
    subprocess.run(["sh", "-n", str(root / "start-dopie.sh")], check=True)
