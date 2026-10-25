"""Coach Thea's ElevenLabs voice proxy: key stays server-side, clips stream and get cached."""
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import voice_tts


class FakeUpstream:
    def __init__(self, status=200, chunks=(b"ID3", b"mp3-bytes")):
        self.status_code = status
        self.chunks = chunks
        self.text = "quota exceeded"
        self.closed = False

    def iter_content(self, size):
        yield from self.chunks

    def close(self):
        self.closed = True


@pytest.fixture
def client(monkeypatch):
    voice_tts._cache.clear()
    app = FastAPI()
    app.include_router(voice_tts.router)
    app.dependency_overrides[voice_tts._identity] = lambda: {"user_id": "p1", "role": "player"}
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    return TestClient(app)


def test_streams_audio_and_caches_repeat_cues(client, monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return FakeUpstream()

    monkeypatch.setattr(voice_tts.requests, "post", fake_post)
    first = client.get("/api/v1/tts", params={"text": "Nice rep,   keep the elbow high"})
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/mpeg"
    assert first.content == b"ID3mp3-bytes"
    assert first.headers["x-tempo-tts-cache"] == "miss"

    url, kw = calls[0]
    assert voice_tts.DEFAULT_VOICE_ID in url
    assert kw["headers"]["xi-api-key"] == "test-key"
    assert kw["json"] == {"text": "Nice rep, keep the elbow high", "model_id": "eleven_flash_v2_5"}

    again = client.get("/api/v1/tts", params={"text": "Nice rep, keep the elbow high"})
    assert again.content == b"ID3mp3-bytes" and again.headers["x-tempo-tts-cache"] == "hit"
    assert len(calls) == 1


def test_without_key_app_is_told_to_fall_back(client, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(voice_tts.requests, "post", lambda *a, **k: pytest.fail("must not call ElevenLabs"))
    assert client.get("/api/v1/tts", params={"text": "hello"}).status_code == 503


def test_upstream_errors_become_502_and_are_not_cached(client, monkeypatch):
    bad = FakeUpstream(status=401)
    monkeypatch.setattr(voice_tts.requests, "post", lambda *a, **k: bad)
    assert client.get("/api/v1/tts", params={"text": "hello"}).status_code == 502
    assert bad.closed and not voice_tts._cache

    def unreachable(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(voice_tts.requests, "post", unreachable)
    assert client.get("/api/v1/tts", params={"text": "hello"}).status_code == 502


def test_rejects_overlong_text(client):
    assert client.get("/api/v1/tts", params={"text": "x" * (voice_tts.MAX_TEXT_CHARS + 1)}).status_code == 422


def test_requires_a_player_credential(monkeypatch):
    app = FastAPI()
    app.include_router(voice_tts.router)
    monkeypatch.setenv("TEMPO_AUTH_TOKENS", '{"0": {"user_id": "someone", "expires_at": "2999-01-01T00:00:00+00:00"}}')
    assert TestClient(app).get("/api/v1/tts", params={"text": "hello"}).status_code == 401
