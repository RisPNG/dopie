from __future__ import annotations

from io import BytesIO

from dopie.models import SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


def test_repository_url_selects_github_api(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "dopie.sources.remote.urlopen",
        lambda request, timeout: requested.append(request.full_url) or BytesIO(b'{"sha":"revision"}'),
    )

    revision = RemoteRepositoryClient(
        SourceDefinition("source", "Source", "https://github.com/team/slices")
    ).resolve_revision()

    assert revision == "revision"
    assert requested == ["https://api.github.com/repos/team/slices/commits/main"]


def test_repository_url_selects_forgejo_api(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "dopie.sources.remote.urlopen",
        lambda request, timeout: requested.append(request.full_url) or BytesIO(b'{"sha":"revision"}'),
    )

    revision = RemoteRepositoryClient(
        SourceDefinition("source", "Source", "https://code.example.test/team/slices")
    ).resolve_revision()

    assert revision == "revision"
    assert requested == ["https://code.example.test/api/v1/repos/team/slices/git/commits/main"]


def test_private_source_token_is_not_sent_to_an_unrelated_artifact_host(monkeypatch):
    headers: list[dict[str, str]] = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            if hasattr(self, "read_once"):
                return b""
            self.read_once = True
            return b"artifact"

    def open_request(request, timeout):
        headers.append(dict(request.headers))
        return Response()

    monkeypatch.setattr("dopie.sources.remote.urlopen", open_request)
    source = SourceDefinition("private", "Private", "https://github.com/team/private")
    client = RemoteRepositoryClient(source, "secret-token")

    client.download_artifact("https://downloads.example.test/slice.zip")
    client.download_artifact("https://api.github.com/repos/team/private/zipball/main")

    assert "Authorization" not in headers[0]
    assert headers[1]["Authorization"] == "Bearer secret-token"


def test_download_reports_progress_when_content_length_is_available(monkeypatch):
    class Response:
        headers = {"Content-Length": "8"}

        def __init__(self):
            self.payload = BytesIO(b"artifact")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            return self.payload.read(size)

    monkeypatch.setattr("dopie.sources.remote.urlopen", lambda request, timeout: Response())
    progress: list[int] = []
    source = SourceDefinition("public", "Public", "https://github.com/team/public")

    payload = RemoteRepositoryClient(source).download_artifact(
        "https://api.github.com/repos/team/public/zipball/main",
        progress.append,
    )

    assert payload == b"artifact"
    assert progress == [100]


def test_github_repository_archive_uses_supported_media_type(monkeypatch):
    requests = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            return b""

    def open_request(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr("dopie.sources.remote.urlopen", open_request)
    source = SourceDefinition("public", "Public", "https://github.com/team/public")

    RemoteRepositoryClient(source).download_repository_archive("revision")

    assert requests[0].get_header("Accept") == "application/vnd.github+json"
