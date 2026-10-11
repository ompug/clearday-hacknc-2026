"""Announcement text, ElevenLabs call (fake transport), cache, fallback and session rule."""

from __future__ import annotations

import httpx
import pytest

from api import voice
from api.config import get_settings
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_api_contract import login


@pytest.fixture
def tts(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    s = get_settings()
    monkeypatch.setattr(s, "elevenlabs_voice_id", "voice123")
    monkeypatch.setattr(s, "elevenlabs_model_id", "model1")
    monkeypatch.setattr(s, "elevenlabs_api_key", type(s.elevenlabs_api_key)("sk-test-secret"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"ID3fake-mp3")

    return calls, httpx.MockTransport(handler)


STATUS = {"weather": "clear", "open_bills": 2, "due_soon_bills": 1, "shares_paid": 3, "shares_total": 6}


def test_text_has_no_amounts_or_names_even_with_salted_data():
    salted = {**STATUS, "label": "Rent Priya $1,234.56", "names": ["Priya", "Maya"], "amount_cents": 123456}
    for status in (salted, {**STATUS, "open_bills": 0}, {**STATUS, "weather": "tight"}):
        text = voice.announcement_text(status)
        assert "$" not in text
        for bad in ("Priya", "Maya", "Rent", "123456", "1,234"):
            assert bad not in text
    assert "3 of 6 shares paid" in voice.announcement_text(STATUS)
    assert "Every shared bill is covered" in voice.announcement_text({**STATUS, "open_bills": 0})


def test_cache_hit_avoids_second_call(tts):
    calls, transport = tts
    first = voice.synthesize("Hello house", transport)
    second = voice.synthesize("Hello house", transport)
    assert (first.source, second.source) == ("elevenlabs", "cache")
    assert first.audio_hash == second.audio_hash
    assert len(calls) == 1
    assert calls[0].headers["xi-api-key"] == "sk-test-secret"
    assert voice.cached_audio_path(first.audio_hash).read_bytes() == b"ID3fake-mp3"


@pytest.mark.parametrize("fail", ["status", "timeout"])
def test_elevenlabs_error_falls_back_to_text(tts, fail):
    def handler(request):
        if fail == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(500)

    result = voice.synthesize("Hello house", httpx.MockTransport(handler))
    assert (result.text, result.audio_hash, result.source) == ("Hello house", None, "text")


def test_no_key_is_text_only(tts, monkeypatch):
    monkeypatch.setattr(get_settings(), "elevenlabs_voice_id", "")
    assert voice.synthesize("Hello house", tts[1]).audio_hash is None
    assert not tts[0]


def test_routes_need_a_session(client):
    assert client.get("/api/voice/announcement").status_code == 401
    assert client.get(f"/api/voice/audio/{'a' * 64}").status_code == 401


def test_route_returns_text_and_audio(client, tts, monkeypatch):
    calls, transport = tts
    real = voice.synthesize
    monkeypatch.setattr(voice, "synthesize", lambda text, transport_=None: real(text, transport))
    login(client)
    body = client.get("/api/voice/announcement").json()
    assert body["source"] == "elevenlabs"
    assert "1 shared bill still open" in body["text"]
    audio = client.get(body["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    assert client.get("/api/voice/audio/../../etc/passwd").status_code in (404, 422)
    assert client.get(f"/api/voice/audio/{'b' * 64}").status_code == 404
