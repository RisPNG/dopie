# Slice contract

Every Slice occupies one folder and contains exactly one `slice.toml`. Catalogue discovery reads that manifest without importing executable Slice code. Installed versions live under `data/slices/<id>/versions/<version>` and `current.json` selects the active version.

```text
slices/
└── text_counter/
    ├── slice.toml
    ├── backend.py
    ├── requirements.lock
    └── assets/
```

## Standard interface

Downloaded Slices must use the standard interface. The Pie generates the form and runs the backend in that Slice's isolated Python environment.

```toml
id = "text-counter"
name = "Text Counter"
version = "1.0.0"
description = "Count words, characters, and lines."
interface = "standard"
operation = "backend:run"
category = "Text"
author = "DoPie"
license = "MIT"
api-version = 1
python = ">=3.11"
platforms = ["linux", "win32"]
architectures = ["x86_64", "AMD64"]

[[inputs]]
id = "text"
label = "Text"
type = "multiline"
required = true

[[assets]]
id = "model.bin"
url = "https://example.test/model.bin"
sha256 = "sha256:replace-with-asset-digest"
```

Supported input types are `text`, `multiline`, `password`, `integer`, `choice`, `boolean`, `file`, `files`, and `directory`. `_assets` is reserved by the Pie.

`file` and `directory` deliver a single path string. `files` provides a multiple-file picker and an editable list of paths, one per line, and delivers a list of nonblank path strings. A required `files` input must contain at least one path. `file` and `files` accept an optional Qt file-dialog `filter`:

```toml
[[inputs]]
id = "pdf_files"
label = "PDF files"
type = "files"
filter = "PDF files (*.pdf);;All files (*)"
placeholder = "Select PDF files or paste their paths, one per line"
```

Earlier DoPie versions display unknown input types as text fields. A Slice that supports those versions can accept a path string as well as the `files` list; multiple paths can be supplied through a separate `multiline` input on those versions.

The operation receives `inputs`, `progress`, and `log`:

```python
def run(inputs, progress, log):
    progress(50, "Working")
    log("Processed input")
    return {"result": inputs["text"]}
```

Downloaded assets are cached under the Slice ID and version, verified before use, and exposed as file paths in `inputs["_assets"]`. A `requirements.lock` is optional; when present it must contain hashes accepted by `pip --require-hashes`.

## Bundled custom interface

A bundled Slice may use `interface = "custom"` and an `entrypoint = "frontend:SliceWidget"`. Its entrypoint must inherit `QWidget`. Custom interfaces are restricted to code shipped with DoPie because they execute inside the Pie process.

Frontend and backend files remain separate within a Slice folder. Slice code must not control the Pie window, navigation, Sources, preferences, or installation state.

## Installation integrity

The Source index publishes the package URL and SHA-256 digest. DoPie verifies the archive, requires exactly one manifest, validates its ID and version against the catalogue, rejects unsafe ZIP paths, and activates the new version atomically while retaining previous versions for rollback.
