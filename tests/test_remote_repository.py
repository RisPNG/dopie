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
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
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
