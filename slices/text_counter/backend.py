from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextStatistics:
    words: int
    characters: int
    lines: int


def analyze_text(text: str) -> TextStatistics:
    return TextStatistics(
        words=len(text.split()),
        characters=len(text),
        lines=len(text.splitlines()) if text else 0,
    )


def run(inputs: dict[str, object], progress, log) -> dict[str, int]:
    log("Analyzing text")
    progress(50, "Counting text…")
    statistics = analyze_text(str(inputs["text"]))
    progress(100, "Complete")
    return {
        "words": statistics.words,
        "characters": statistics.characters,
        "lines": statistics.lines,
    }
