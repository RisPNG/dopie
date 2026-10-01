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

Run `start-dopie.sh` on Linux or `Start DoPie.vbs` on Windows. On first use on each computer, the launcher shows a terminal while it downloads the pinned MsPy runtime, verifies its SHA-256 digest, and installs DoPie's hash-locked packages into that computer's cache: `%LOCALAPPDATA%\DoPie` on Windows and `~/.cache/dopie` on Linux. The terminal closes before DoPie opens, and later launches remain terminal-free.

DoPie keeps all persistent state inside its own folder. That state includes Sources, installed Slice versions, cached catalogues, Slice assets, preferences, updates, and encrypted private credentials. The runtime and the Python packages that DoPie and its Slices need are kept in each computer's cache instead, and are downloaded again on a new computer.

## Transfer a preconfigured copy

Configure the Sources on your copy, open **Slice Manager → Sources**, and select **Export Portable Copy**. Choose Linux, Windows, or both launch scripts. A copy containing private Sources offers an optional transfer password. Leave it blank to include the credentials without password protection; public-only copies do not need one. Installed Slices and the runtime are never included; the receiving computer obtains Slices from the configured Sources and downloads and verifies its own runtime on first launch.

Extract the resulting ZIP and transfer its `DoPie` folder. On that copy's first launch, DoPie imports `provisioning/DoPie.dopie-profile` automatically. Password-protected profiles request the transfer password once; profiles exported without a password import automatically. DoPie creates a new encrypted vault with a fresh key inside that portable folder, records the imported profile, and deletes the one-time provisioning file. An incorrect password imports nothing and leaves the profile available for another attempt.

The Linux taskbar icon temporarily requires `dopie.desktop` in the current user's application directory. DoPie removes a stale entry on startup, recreates it while running, and removes it during normal shutdown. Update, profile, and Slice staging directories remain inside the DoPie folder.

## Run DoPie from a shared folder

Several people can run one DoPie folder from a network share, on Windows and on Linux. Create it from a DoPie 1.2.1 or later download, or with **Export Portable Copy** from a copy whose launch scripts are 1.2.1 or later, choosing Both launch scripts when Windows and Linux users share the folder. In-app updates replace only the application, so a copy updated in-app from an earlier version still carries launch scripts that cannot run from a shared folder. Extract it into a folder where every user can read, create, rename, and delete files, and start DoPie from it once yourself: that first start imports the portable profile's Sources and access tokens, asking for its transfer password when it has one. Everyone then starts `Start DoPie.vbs` or `start-dopie.sh` from the share; nothing but the runtime and packages in each computer's cache is stored on their computers. People may reach the folder through different drive letters, UNC paths, or mount points.

Each person gets their own preferences, favourites, recent items, Library options, update checks on launch, and installed Slices in `data/users/<login>`, named after their login name without its domain and ignoring case; people who log in with the same name share one profile. The first person to start DoPie 1.2.0 or later on an upgraded single-user copy keeps that copy's installed Slices and preferences. Sources, their access tokens, the update repository, and catalogues are shared: a change by one person applies to everyone, and anyone can apply a DoPie update for everyone. Anyone who can read the folder can decrypt the access tokens, so restrict the folder and use read-only, repository-scoped, revocable tokens.

The first start on each computer, and the first start after an update that changes DoPie's dependencies or of another DoPie folder that needs different ones, downloads the runtime and DoPie's packages into that computer's cache, which takes a few minutes and about 1 GB; only the first of these shows the setup window; a Slice downloads its dependencies the first time it runs on a computer. Old folders under the cache's `environments` and `slice-environments` folders can be deleted. Because the deepest files live in the cache, the path to the DoPie folder can be up to about 140 characters on Windows without long path support.

On Linux, mount the share through the kernel with CIFS or NFS rather than opening a file manager `smb://` location. On a share with POSIX permissions, give the folder a team group so that everyone can keep writing to it: `chgrp -R team DoPie`, `chmod -R g+rwX,o-rwx DoPie`, and `find DoPie -type d -exec chmod g+s {} +`. `start-dopie.sh` keeps new files group-writable.

The share must support byte-range file locking; Linux clients using CIFS need kernel 5.5 or later for these locks to reach the server. DoPie coordinates configuration changes, legacy profile adoption, provisioning, and update activation through shared locks. Initial runtime setup leaves a pending update for the first application launch, so startup failures can still restore the previous version.

See [the Slice contract](application/base/docs/SLICES.md), and [the Source format](application/base/docs/SOURCES.md).
