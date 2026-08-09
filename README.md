# DoPie

<img src="application/base/assets/dopie.png" alt="DoPie logo" width="160">

DoPie is a Python-based UI shell for Python developers to write scripts without building a frontend from scratch.

DoPie is a source-run desktop platform for installing and running focused automation modules called Slices. It uses PySide6 on Linux and Windows and deliberately does not produce an EXE, AppImage, installer, or other compiled application package.

The Pie owns the Library, Favorites, Slice Manager, trusted Sources, private credentials, updates, preferences, progress, and presentation. Each Slice owns one operation and its domain behavior.

## Development

```bash
mise install
mise exec -- python -m pip install -e 'application/base[dev]'
mise run test
./start-dopie.sh
```

## Portable launch

Run `start-dopie.sh` on Linux or `Start DoPie.vbs` on Windows. On first use, the launcher shows a terminal while it downloads the pinned MsPy runtime, verifies its SHA-256 digest, and creates a hash-locked DoPie environment. The terminal closes before DoPie opens, and later launches remain terminal-free.

DoPie keeps all persistent state inside its own folder. That state includes Sources, installed Slice versions, cached catalogues, Slice environments and assets, preferences, updates, and encrypted private credentials.

## Transfer a preconfigured copy

Configure the Sources on your copy, open **Slice Manager → Sources**, and select **Export Portable Copy**. Choose Linux, Windows, or both launch scripts. A copy containing private Sources asks you to choose a transfer password; public-only copies do not need one. Installed Slices and the runtime are never included; the receiving computer obtains Slices from the configured Sources and downloads and verifies its own runtime on first launch.

Extract the resulting ZIP and transfer its `DoPie` folder. On that copy's first launch, DoPie imports `provisioning/DoPie.dopie-profile` automatically. Private Sources request the transfer password once, then DoPie creates a new encrypted key inside that portable folder, records the imported profile, and deletes the one-time provisioning file. An incorrect password imports nothing and leaves the profile available for another attempt.

The Linux taskbar icon temporarily requires `dopie.desktop` in the current user's application directory. DoPie removes a stale entry on startup, recreates it while running, and removes it during normal shutdown. Update, profile, and Slice staging directories remain inside the DoPie folder.

See [the Slice contract](application/base/docs/SLICES.md), and [the Source format](application/base/docs/SOURCES.md).
