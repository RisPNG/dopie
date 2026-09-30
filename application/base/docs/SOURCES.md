# Slice Sources

A Source is a GitHub or Forgejo repository URL containing an `index.json` catalogue. DoPie detects GitHub from `github.com` and treats other repository hosts as Forgejo. It resolves the configured branch to an immutable commit before reading the catalogue. Network work runs outside the interface thread, and the last valid catalogue remains usable when a Source is temporarily offline.

The index follows [source-index.example.json](source-index.example.json). Each package digest is required. Compatibility metadata lets the Pie explain why a Slice cannot be installed on the current Pie API, Python, operating system, or processor architecture.

## Catalogue and package integrity

DoPie expects `index.json` at the root of the selected branch unless a different relative Index path is configured under Advanced. The index tells DoPie which Slices exist and provides each package's SHA-256 digest. DoPie verifies that digest before installing a package. Repository identity relies on the configured HTTPS URL and the repository host's access controls.

## Private Sources

GitHub and Forgejo access tokens are referenced by credential ID in `data/sources.json`. The tokens are encrypted with AES-256-GCM in `data/source-vault.dopie`, and its randomly generated local key stays in `data/source-vault.key`. Both files remain inside the portable DoPie folder and are shared by everyone who runs DoPie from it. The DoPie update repository is the `application_update_source` entry of `data/preferences.json`, and its token uses the credential ID `application:update`. Tokens should be read-only, repository-scoped, independently revocable, and time-limited.

## Shared use

When several people run DoPie from one folder, Source, access token, and update repository changes hold a shared file lock while re-reading and replacing the current files, so independent edits keep each other's changes. Two edits of the same Source or update repository keep the last saved value. Temporary files have unique names, and leftover `.tmp` files are harmless. The `.configuration.lock` files stay in place between operations; the operating system releases their locks when a process exits. The share must support byte-range file locking. The key sits beside the vault, so folder permissions are the only protection for the access tokens.

## Portable profiles

The portable copy includes a `.dopie-profile` containing Source definitions, portable preferences, and private Source credentials. Credentials are re-encrypted for transfer using an Argon2id-derived key and AES-256-GCM. The transfer password is optional: leaving it blank uses an empty password, includes the credentials without password protection, and allows automatic import. The folder-local key is never exported. When a password is set, communicate it separately from the profile.

**Export Portable Copy** builds a clean transferable ZIP containing the selected Linux, Windows, or both launch scripts, application source, documentation, and `provisioning/DoPie.dopie-profile`. Installed Slices and the runtime are never included; the receiving computer obtains Slices from the configured Sources and downloads and verifies its own runtime on first launch. The receiving copy imports the profile on first launch, asks for the transfer password once when required, creates a new folder-local vault key, records the profile digest in `data/provisioning.json`, and deletes the one-time profile. An incorrect password changes no Source state and leaves the profile available for another attempt. Placing a new profile at the provisioning path starts a new authorization.

Importing a profile replaces the Sources, update repository, and access tokens for everyone who runs DoPie from the folder, while its portable preferences apply to the person importing it.

DoPie validates the existing preferences and prepares all replacement files before applying an import. Configuration readers wait until publication finishes, and a publication error restores the original files. Concurrent first launches apply the provisioning profile once.

Setting a transfer password protects the access token during transfer; it does not make a shared token non-transferable after an authorized recipient unlocks it. Issue a different revocable token for each recipient or deployment group when that distinction matters.
