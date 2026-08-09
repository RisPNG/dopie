from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from dopie.models import SourceDefinition


class RemoteRepositoryClient:
    def __init__(self, source: SourceDefinition, token: str | None = None):
        self.source = source
        self.token = token

    def resolve_revision(self) -> str:
        repository = "/".join(quote(part, safe="") for part in self.source.repository.split("/"))
        reference = quote(self.source.reference, safe="")
        if self.source.provider == "github":
            url = f"https://api.github.com/repos/{repository}/commits/{reference}"
        elif self.source.provider == "forgejo":
            base_url = (self.source.base_url or "").rstrip("/")
            url = f"{base_url}/api/v1/repos/{repository}/git/commits/{reference}"
        else:
            raise ValueError(f"Unsupported Source provider: {self.source.provider}")
        headers = {"Accept": "application/json", "User-Agent": "DoPie"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            data = json.load(response)
        return str(data["sha"])

    def read_repository_file(self, path: str, revision: str | None = None) -> bytes:
        repository = "/".join(quote(part, safe="") for part in self.source.repository.split("/"))
        encoded_path = quote(path, safe="/")
        reference = quote(revision or self.source.reference, safe="")
        if self.source.provider == "github":
            url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={reference}"
        elif self.source.provider == "forgejo":
            base_url = (self.source.base_url or "").rstrip("/")
            url = f"{base_url}/api/v1/repos/{repository}/contents/{encoded_path}?ref={reference}"
        else:
            raise ValueError(f"Unsupported Source provider: {self.source.provider}")
        headers = {"Accept": "application/json", "User-Agent": "DoPie"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            data: dict[str, Any] = json.load(response)
        return base64.b64decode(data["content"])

    def download_repository_archive(self, revision: str) -> bytes:
        repository = "/".join(quote(part, safe="") for part in self.source.repository.split("/"))
        revision = quote(revision, safe="")
        if self.source.provider == "github":
            url = f"https://api.github.com/repos/{repository}/zipball/{revision}"
        elif self.source.provider == "forgejo":
            base_url = (self.source.base_url or "").rstrip("/")
            url = f"{base_url}/api/v1/repos/{repository}/archive/{revision}.zip"
        else:
            raise ValueError(f"Unsupported Source provider: {self.source.provider}")
        headers = {"Accept": "application/octet-stream", "User-Agent": "DoPie"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=120) as response:
            return response.read()

    def download_artifact(self, url: str) -> bytes:
        headers = {"Accept": "application/octet-stream", "User-Agent": "DoPie"}
        repository_host = urlparse(self.source.repository_url).hostname
        allowed_hosts = {repository_host, "api.github.com"} if self.source.provider == "github" else {repository_host}
        if self.token and urlparse(url).hostname in allowed_hosts:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=120) as response:
            return response.read()
