from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_text_statistics():
    path = Path(__file__).parents[1] / "slices" / "text_counter" / "backend.py"
    spec = importlib.util.spec_from_file_location("text_counter_backend", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.analyze_text("one two\nthree").words == 3
    assert module.analyze_text("one two\nthree").characters == 13
    assert module.analyze_text("one two\nthree").lines == 2
