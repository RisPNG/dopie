# DoPie

DoPie is a Python-based UI shell for Python developers to write scripts without building a frontend from scratch.

DoPie is a source-run desktop platform for installing and running focused automation modules called Slices. It uses PySide6 on Linux and Windows and deliberately does not produce an EXE, AppImage, installer, or other compiled application package.

The Pie owns the Library, Favorites, Slice Manager, trusted Sources, private credentials, updates, preferences, progress, and presentation. Each Slice owns one operation and its domain behavior.

## Development

```bash
mise install
mise exec -- python -m pip install -e '.[dev]'
mise exec -- pytest
mise exec -- dopie
```

## Portable launch

Run `start-dopie.sh` on Linux or `Start DoPie.vbs` on Windows. On first use, the launcher downloads the pinned MsPy runtime, verifies its SHA-256 digest, creates a hash-locked DoPie environment, and runs the checked-out Python source.

DoPie keeps portable state beside the application because `portable.toml` is present. That state includes Sources, installed Slice versions, cached catalogues, Slice environments and assets, preferences, updates, and the encrypted credential vault.

See [the Slice contract](docs/SLICES.md) and [the Source format](docs/SOURCES.md).
