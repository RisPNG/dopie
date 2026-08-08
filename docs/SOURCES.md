# Slice Sources

A Source is a GitHub or Forgejo repository containing an `index.json` catalogue. DoPie resolves its configured branch to an immutable commit before reading the catalogue. Network work runs outside the interface thread, and the last valid catalogue remains usable when a Source is temporarily offline.

The index follows [source-index.example.json](source-index.example.json). Each package digest is required. Compatibility metadata lets the Pie explain why a Slice cannot be installed on the current Pie API, Python, operating system, or processor architecture.

## Signed Sources

For an authenticated Source, configure a base64-encoded Ed25519 public key and publish `index.json.sig` beside the index. The signature file contains the base64 signature of the exact `index.json` bytes. DoPie rejects a catalogue when verification fails. Adding an unsigned Source requires an explicit warning confirmation.

Application update Sources use the same public-key format and publish `update.json` plus `update.json.sig`. The signed JSON contains the immutable `revision` and the SHA-256 digest of that revision's repository ZIP. This binds the signature to the code archive that DoPie stages.

## Private Sources

GitHub and Forgejo access tokens are referenced by credential ID in `data/sources.json`; the token itself exists only in `data/source-vault.dopie`. The vault uses Argon2id for password derivation and AES-256-GCM authenticated encryption. Preferences controls automatic inactivity locking. Tokens should be read-only, repository-scoped, independently revocable, and time-limited.

## Portable profiles

The Sources page can export a `.dopie-profile` containing Source definitions, the encrypted vault, portable preferences, and optionally installed Slice versions. Import replaces the receiving installation's Source configuration and included Slice IDs. Communicate the vault password separately from the profile.

This protects the access token at rest; it does not make a shared token non-transferable after an authorized recipient unlocks it. Issue a different revocable token for each recipient or deployment group when that distinction matters.
