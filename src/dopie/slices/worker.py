from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def execute_slice_operation(slice_path: Path, operation: str, inputs: dict[str, Any]) -> Any:
    module_name, function_name = operation.split(":", 1)
    package_name = f"dopie_worker_{slice_path.name.replace('-', '_')}"
    package = types.ModuleType(package_name)
    package.__path__ = [str(slice_path)]
    sys.modules[package_name] = package
    module_path = slice_path / f"{module_name.replace('.', '/')}.py"
    spec = importlib.util.spec_from_file_location(f"{package_name}.{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Slice operation: {operation}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    operation_function = getattr(module, function_name)

    def progress(value: int, message: str = "") -> None:
        print(json.dumps({"type": "progress", "value": value, "message": message}), flush=True)

    def log(message: str) -> None:
        print(json.dumps({"type": "log", "message": message}), flush=True)

    return operation_function(inputs, progress, log)


def prepare_slice_assets(asset_root: Path, definitions: list[dict[str, str]]) -> dict[str, str]:
    asset_root.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, str] = {}
    for definition in definitions:
        asset_id = definition["id"]
        if Path(asset_id).name != asset_id:
            raise ValueError(f"Invalid asset id: {asset_id}")
        destination = asset_root / asset_id
        expected = definition["sha256"].removeprefix("sha256:")
        if not destination.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
            with urlopen(Request(definition["url"], headers={"User-Agent": "DoPie"}), timeout=120) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"Checksum verification failed for asset {asset_id}")
            temporary = destination.with_suffix(destination.suffix + ".prepared")
            temporary.write_bytes(payload)
            temporary.replace(destination)
        resolved[asset_id] = str(destination)
    return resolved


def main() -> int:
    if sys.argv[1] == "--prepare-assets":
        try:
            prepared = prepare_slice_assets(Path(sys.argv[2]), json.loads(sys.stdin.read()))
        except Exception as error:
            print(json.dumps({"type": "error", "message": str(error)}), flush=True)
            return 1
        print(json.dumps({"type": "assets", "value": prepared}), flush=True)
        return 0
    slice_path = Path(sys.argv[1])
    operation = sys.argv[2]
    inputs = json.loads(sys.stdin.read())
    try:
        result = execute_slice_operation(slice_path, operation, inputs)
    except Exception as error:
        print(json.dumps({"type": "error", "message": str(error)}), flush=True)
        return 1
    print(json.dumps({"type": "result", "value": result}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
