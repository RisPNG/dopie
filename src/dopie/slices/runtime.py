from __future__ import annotations

import importlib.util
import sys
import types

from PySide6.QtWidgets import QWidget

from dopie.models import SliceManifest


class SliceRuntime:
    def open_slice(self, manifest: SliceManifest) -> QWidget:
        if manifest.origin != "bundled":
            raise PermissionError("Downloaded Slices must use the isolated standard interface")
        if manifest.entrypoint is None:
            raise ValueError(f"{manifest.name} does not define a custom entrypoint")
        module_name, class_name = manifest.entrypoint.split(":", 1)
        module_path = manifest.path / f"{module_name.replace('.', '/')}.py"
        package_name = f"dopie_slice_{manifest.id.replace('-', '_')}"
        package = types.ModuleType(package_name)
        package.__path__ = [str(manifest.path)]
        sys.modules[package_name] = package
        spec = importlib.util.spec_from_file_location(f"{package_name}.{module_name}", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load Slice entrypoint: {manifest.entrypoint}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        widget_type = getattr(module, class_name)
        if not issubclass(widget_type, QWidget):
            raise TypeError(f"{manifest.entrypoint} must be a QWidget")
        return widget_type()
