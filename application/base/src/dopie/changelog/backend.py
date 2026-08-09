from __future__ import annotations

from pathlib import Path

from packaging.version import InvalidVersion, Version


class ChangelogReader:
    def __init__(self, root: Path):
        self.root = root

    def release_notes_since(self, previous: str | None, current: str) -> str:
        current_version = Version(current)
        previous_version = Version(previous) if previous else None
        releases: list[tuple[Version, Path]] = []
        for path in self.root.glob("*.md"):
            try:
                version = Version(path.stem)
            except InvalidVersion:
                continue
            if version <= current_version and (previous_version is None or version > previous_version):
                releases.append((version, path))
        if not releases:
            path = self.root / f"{current}.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
            return f"# DoPie {current}\n\nThis version does not include release notes."
        return "\n\n---\n\n".join(path.read_text(encoding="utf-8") for _, path in sorted(releases, reverse=True))
