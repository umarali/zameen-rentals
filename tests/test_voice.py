"""Voice search: /api/voice/* endpoints and the faster-whisper wrapper."""
import asyncio
import io
import os
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import app
from app import voice
from app.cache import limiter

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def reset_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("VOICE_SEARCH_ENABLED", "1")


def _wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


class TestPickLanguage:
    def test_hindi_counts_as_urdu(self):
        assert voice.pick_language([("hi", 0.5), ("en", 0.3), ("ur", 0.1)]) == "ur"

    def test_english_wins_when_dominant(self):
        assert voice.pick_language([("en", 0.7), ("hi", 0.2), ("ur", 0.05)]) == "en"

    def test_other_languages_fall_back_to_english_or_urdu(self):
        assert voice.pick_language([("pa", 0.6), ("ur", 0.2), ("en", 0.1)]) == "ur"


class TestBuildPrompt:
    def test_city_areas_in_prompt(self):
        assert "Gulshan-e-Iqbal" in voice.build_prompt("en", "karachi")
        assert "گلبرگ" in voice.build_prompt("ur", "lahore")

    def test_unknown_city_uses_default(self):
        assert voice.build_prompt("en", "quetta") == voice.build_prompt("en", "lahore")


class TestStatus:
    def test_disabled_by_default(self, client, monkeypatch):
        monkeypatch.delenv("VOICE_SEARCH_ENABLED", raising=False)
        assert client.get("/api/voice/status").json()["enabled"] is False

    def test_enabled_by_env(self, client, enabled):
        data = client.get("/api/voice/status").json()
        assert data == {"enabled": True, "max_seconds": voice.MAX_CLIP_SECONDS}


class TestTranscribeEndpoint:
    def test_404_when_disabled(self, client, monkeypatch):
        monkeypatch.delenv("VOICE_SEARCH_ENABLED", raising=False)
        res = client.post("/api/voice/transcribe", content=b"x", headers={"Content-Type": "audio/webm"})
        assert res.status_code == 404

    def test_rejects_non_audio(self, client, enabled):
        res = client.post("/api/voice/transcribe", content=b"x", headers={"Content-Type": "text/plain"})
        assert res.status_code == 415

    def test_rejects_oversized_body(self, client, enabled):
        body = b"\x00" * (voice.MAX_BODY_BYTES + 1)
        res = client.post("/api/voice/transcribe", content=body, headers={"Content-Type": "audio/webm"})
        assert res.status_code == 413

    def test_rejects_empty_body(self, client, enabled):
        res = client.post("/api/voice/transcribe", content=b"", headers={"Content-Type": "audio/webm"})
        assert res.status_code == 422

    def test_returns_transcript_and_passes_city(self, client, enabled, monkeypatch):
        seen = {}

        async def fake_transcribe(audio, city):
            seen.update(audio=audio, city=city)
            return {"text": "2 bed flat in DHA", "language": "en", "duration": 1.2}

        monkeypatch.setattr(voice, "transcribe", fake_transcribe)
        res = client.post("/api/voice/transcribe?city=karachi", content=b"abc",
                          headers={"Content-Type": "audio/webm;codecs=opus"})
        assert res.status_code == 200
        assert res.json()["text"] == "2 bed flat in DHA"
        assert seen == {"audio": b"abc", "city": "karachi"}

    def test_safari_mp4_content_type_accepted(self, client, enabled, monkeypatch):
        async def fake_transcribe(audio, city):
            return {"text": "", "language": "en", "duration": 1.0}

        monkeypatch.setattr(voice, "transcribe", fake_transcribe)
        res = client.post("/api/voice/transcribe", content=b"abc", headers={"Content-Type": "audio/mp4"})
        assert res.status_code == 200

    def test_rate_limited(self, client, enabled, monkeypatch):
        async def fake_transcribe(audio, city):
            return {"text": "", "language": "en", "duration": 1.0}

        monkeypatch.setattr(voice, "transcribe", fake_transcribe)
        codes = [client.post("/api/voice/transcribe", content=b"abc",
                             headers={"Content-Type": "audio/webm"}).status_code for _ in range(8)]
        assert codes[:6] == [200] * 6
        assert 429 in codes[6:]


class TestTranscribeGuards:
    def test_busy_returns_503(self, monkeypatch):
        monkeypatch.setattr(voice, "BUSY_WAIT_SECONDS", 0.05)

        async def run():
            monkeypatch.setattr(voice, "_semaphore", asyncio.Semaphore(1))
            await voice._semaphore.acquire()
            with pytest.raises(HTTPException) as exc:
                await voice.transcribe(b"abc")
            assert exc.value.status_code == 503

        asyncio.run(run())

    def test_unreadable_audio(self):
        with pytest.raises(HTTPException) as exc:
            voice._transcribe_sync(b"not audio at all", "lahore")
        assert exc.value.status_code == 422

    def test_too_long_rejected_before_model_loads(self, monkeypatch):
        monkeypatch.setattr(voice, "_get_model", lambda: pytest.fail("model should not load"))
        with pytest.raises(HTTPException) as exc:
            voice._transcribe_sync(_wav(voice.MAX_CLIP_SECONDS + 1), "lahore")
        assert exc.value.status_code == 422

    def test_too_short_rejected_before_model_loads(self, monkeypatch):
        monkeypatch.setattr(voice, "_get_model", lambda: pytest.fail("model should not load"))
        with pytest.raises(HTTPException) as exc:
            voice._transcribe_sync(_wav(0.1), "lahore")
        assert exc.value.status_code == 422


class TestIdleUnload:
    def test_unloads_model(self, monkeypatch):
        monkeypatch.setattr(voice, "_model", object())
        voice._unload_if_idle()
        assert voice._model is None

    def test_reschedules_while_transcribing(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(voice, "_model", sentinel)
        rescheduled = []
        monkeypatch.setattr(voice, "_schedule_unload", lambda: rescheduled.append(True))
        with voice._model_lock:
            voice._unload_if_idle()
        assert voice._model is sentinel
        assert rescheduled == [True]


# Loads the real Whisper model (~460 MB download on first run, a few seconds per clip).
@pytest.mark.skipif(os.getenv("VOICE_MODEL_TESTS") != "1", reason="set VOICE_MODEL_TESTS=1 to run the real model")
class TestRealModel:
    def test_english_clip(self):
        result = asyncio.run(voice.transcribe((FIXTURES / "voice_en_2bed_dha.wav").read_bytes(), "karachi"))
        assert result["language"] == "en"
        assert "DHA" in result["text"] and "2" in result["text"]

    def test_urdu_clip_comes_out_in_urdu_script(self):
        # Spoken Hindustani that Whisper labels as Hindi; we want Urdu script, not Devanagari.
        result = asyncio.run(voice.transcribe((FIXTURES / "voice_ur_gulberg_10marla.wav").read_bytes(), "lahore"))
        assert result["language"] == "ur"
        assert "گلبرگ" in result["text"] and "10" in result["text"]


class TestReviewResourceBounds:
    def test_chunked_upload_stops_reading_at_limit(self, monkeypatch):
        from starlette.requests import Request
        monkeypatch.setattr(voice, "MAX_BODY_BYTES", 5)
        consumed = []
        async def receive():
            consumed.append(1)
            assert len(consumed) <= 2, "must reject without reading the remaining upload"
            return {"type": "http.request", "body": b"1234", "more_body": True}
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
        async def run():
            with pytest.raises(HTTPException) as exc:
                await voice._process_recording(request, "lahore")
            assert exc.value.status_code == 413
        asyncio.run(run())
        assert len(consumed) == 2

    def test_slow_upload_times_out(self, monkeypatch):
        from starlette.requests import Request
        monkeypatch.setattr(voice, "UPLOAD_TIMEOUT_SECONDS", 0.01)
        async def receive():
            await asyncio.sleep(1)
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
        async def run():
            with pytest.raises(HTTPException) as exc:
                await voice._process_recording(request, "lahore")
            assert exc.value.status_code == 408
        asyncio.run(run())

    def test_only_two_requests_are_admitted_before_reading_body(self, monkeypatch, enabled):
        import threading
        from starlette.requests import Request
        slots = threading.BoundedSemaphore(2)
        monkeypatch.setattr(voice, "_request_slots", slots)
        entered = []
        async def run():
            release = asyncio.Event()
            async def process(request, city):
                entered.append(True)
                await release.wait()
                return {"text": "ok"}
            monkeypatch.setattr(voice, "_process_recording", process)
            request = Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"content-type", b"audio/webm")]})
            endpoint = voice.voice_transcribe.__wrapped__
            first = asyncio.create_task(endpoint(request, "lahore"))
            second = asyncio.create_task(endpoint(request, "lahore"))
            try:
                for _ in range(10):
                    if len(entered) == 2:
                        break
                    await asyncio.sleep(0)
                assert len(entered) == 2
                with pytest.raises(HTTPException) as exc:
                    await endpoint(request, "lahore")
                assert exc.value.status_code == 503
            finally:
                release.set()
                await asyncio.gather(first, second)
            assert slots.acquire(blocking=False)
            assert slots.acquire(blocking=False)
            slots.release(); slots.release()
        asyncio.run(run())

    def test_cancellation_keeps_transcription_permit_until_thread_finishes(self, monkeypatch):
        import threading
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def blocking(*args):
            entered.set()
            assert release.wait(2)
            finished.set()
            return {"text": "ok"}
        monkeypatch.setattr(voice, "_transcribe_sync", blocking)
        monkeypatch.setattr(voice, "BUSY_WAIT_SECONDS", 0.02)
        async def run():
            monkeypatch.setattr(voice, "_semaphore", asyncio.Semaphore(1))
            first = asyncio.create_task(voice.transcribe(b"audio"))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                with pytest.raises(HTTPException) as exc:
                    await voice.transcribe(b"second")
                assert exc.value.status_code == 503
                assert not finished.is_set()
            finally:
                release.set()
                assert await asyncio.to_thread(finished.wait, 1)
            assert await voice.transcribe(b"third") == {"text": "ok"}
        asyncio.run(run())

    def test_decoder_stops_before_reading_whole_long_clip(self, monkeypatch):
        import av
        decoded = []
        class Container:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def decode(self, **kwargs):
                for i in range(100):
                    assert i <= voice.MAX_CLIP_SECONDS, "decoded beyond duration guard"
                    frame = av.AudioFrame(format="s16", layout="mono", samples=16000)
                    frame.sample_rate = 16000
                    decoded.append(i)
                    yield frame
        monkeypatch.setattr(av, "open", lambda *a, **k: Container())
        with pytest.raises(HTTPException) as exc:
            voice._decode_bounded(b"compressed audio")
        assert exc.value.status_code == 422
        assert len(decoded) == voice.MAX_CLIP_SECONDS + 1

    def test_decode_valid_wav_without_loading_model(self, monkeypatch):
        monkeypatch.setattr(voice, "_get_model", lambda: pytest.fail("decoder must not load model"))
        audio = voice._decode_bounded(_wav(1))
        assert len(audio) == 16000
        assert audio.dtype.name == "float32"

    def test_model_error_still_schedules_unload(self, monkeypatch):
        from types import SimpleNamespace
        scheduled = []
        def fail(*args): raise RuntimeError("inference failed")
        monkeypatch.setattr(voice, "_get_model", lambda: SimpleNamespace(detect_language=fail))
        monkeypatch.setattr(voice, "_schedule_unload", lambda: scheduled.append(True))
        with pytest.raises(RuntimeError, match="inference failed"):
            voice._transcribe_sync(_wav(1), "lahore")
        assert scheduled == [True]

    def test_disabled_endpoint_does_not_read_upload_or_import_model(self, client, monkeypatch):
        import builtins
        monkeypatch.delenv("VOICE_SEARCH_ENABLED", raising=False)
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            assert name not in {"faster_whisper", "av"}, "disabled voice imported decoder/model"
            return original(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", guarded)
        async def fail(*args): pytest.fail("disabled voice read upload")
        monkeypatch.setattr(voice, "_process_recording", fail)
        assert client.post("/api/voice/transcribe", content=b"x", headers={"Content-Type": "audio/webm"}).status_code == 404
