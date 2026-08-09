# DoPie

<img src="assets/dopie.png" alt="DoPie logo" width="160">

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

DoPie keeps all persistent state inside its own folder. That state includes Sources, installed Slice versions, cached catalogues, Slice environments and assets, preferences, updates, and encrypted private credentials.

## Transfer a preconfigured copy

Configure the Sources on your copy, open **Slice Manager → Sources**, and select **Export Portable Copy**. Choose whether to include installed Slices and the already-downloaded runtime. A copy containing private Sources asks you to choose a transfer password; public-only copies do not need one.

Extract the resulting ZIP and transfer its `DoPie` folder. On that copy's first launch, DoPie imports the bundled profile automatically. Private Sources request the transfer password once, then DoPie creates a new encrypted key inside that portable folder and records the imported profile there. Later launches do not ask again. Replacing `DoPie.dopie-profile` with a different profile triggers authorization for the new profile.

The Linux taskbar icon temporarily requires `dopie.desktop` in the current user's application directory. DoPie removes a stale entry on startup, recreates it while running, and removes it during normal shutdown. Update, profile, and Slice staging directories remain inside the DoPie folder.

See [the Slice contract](docs/SLICES.md), and [the Source format](docs/SOURCES.md).
