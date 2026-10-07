"""Voice search: speech-to-text with faster-whisper (MIT), run on our own server.

The browser records a short clip and posts it here; the transcript goes back
into the normal NL search box, so /api/parse-query does the rest.

Built for a small box (2 GB / 1 vCPU shared with the crawler): the model loads
on first use, unloads after VOICE_IDLE_UNLOAD_SECONDS idle, and only one clip
is transcribed at a time.
"""
import asyncio
import gc
import io
import logging
import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from app.cache import limiter

logger = logging.getLogger("zameenrentals")
router = APIRouter()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PLAYWRIGHT_SERVER = os.getenv("ZAMEENRENTALS_PLAYWRIGHT") == "1"
_VOICE_RATE_LIMIT = "10000/minute" if _PLAYWRIGHT_SERVER else "6/minute"
_PLAYWRIGHT_TRANSCRIPT = "2 bed flat in Clifton under 50k"

MODEL_NAME = os.getenv("VOICE_MODEL", "small")
MODEL_DIR = Path(os.getenv("VOICE_MODEL_DIR", str(_PROJECT_ROOT / "data" / "models" / "whisper")))
IDLE_UNLOAD_SECONDS = int(os.getenv("VOICE_IDLE_UNLOAD_SECONDS", "600"))
MAX_BODY_BYTES = 1_000_000
MAX_CLIP_SECONDS = 15
MIN_CLIP_SECONDS = 0.3
BUSY_WAIT_SECONDS = 10
_SAMPLE_RATE = 16000

# Seed vocabulary so area names, units and digits come out the way the parser expects.
_PROMPT_BASE = {
    "en": "2 bed flat under 50k, 10 marla house, upper portion. ",
    "ur": "2 بیڈ فلیٹ 50 ہزار تک، 10 مرلہ گھر۔ ",
}
_PROMPT_AREAS = {
    "karachi": {"en": "DHA, Clifton, Gulshan-e-Iqbal, Gulistan-e-Johar, North Nazimabad, PECHS, Bahria Town.",
                "ur": "ڈی ایچ اے، کلفٹن، گلشن اقبال، گلستان جوہر، نارتھ ناظم آباد، بحریہ ٹاؤن۔"},
    "lahore": {"en": "DHA, Gulberg, Johar Town, Model Town, Bahria Town, Wapda Town.",
               "ur": "ڈی ایچ اے، گلبرگ، جوہر ٹاؤن، ماڈل ٹاؤن، بحریہ ٹاؤن، واپڈا ٹاؤن۔"},
    "islamabad": {"en": "F-10, G-11, E-11, I-8, Bahria Town, DHA.",
                  "ur": "ایف 10، جی 11، ای 11، آئی 8، بحریہ ٹاؤن، ڈی ایچ اے۔"},
}


def build_prompt(language: str, city: str) -> str:
    areas = _PROMPT_AREAS.get(city, _PROMPT_AREAS["lahore"])
    return _PROMPT_BASE[language] + areas[language]


_model = None
_model_lock = threading.Lock()
_unload_timer = None
_semaphore = asyncio.Semaphore(1)


def is_enabled() -> bool:
    return _PLAYWRIGHT_SERVER or os.getenv("VOICE_SEARCH_ENABLED") == "1"


def pick_language(all_probs) -> str:
    """Choose between Urdu and English only.

    Whisper often labels spoken Urdu as Hindi, which comes out in Devanagari
    that the parser can't read, so Hindi counts toward Urdu.
    """
    probs = dict(all_probs)
    urdu = probs.get("ur", 0.0) + probs.get("hi", 0.0)
    return "ur" if urdu > probs.get("en", 0.0) else "en"


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model %s from %s", MODEL_NAME, MODEL_DIR)
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                              cpu_threads=os.cpu_count() or 1, download_root=str(MODEL_DIR))
    return _model


def _unload_if_idle():
    global _model
    if not _model_lock.acquire(blocking=False):
        _schedule_unload()  # mid-transcription; try again later
        return
    try:
        if _model is not None:
            logger.info("Unloading idle Whisper model")
            _model = None
            gc.collect()
    finally:
        _model_lock.release()


def _schedule_unload():
    global _unload_timer
    if _unload_timer is not None:
        _unload_timer.cancel()
    _unload_timer = threading.Timer(IDLE_UNLOAD_SECONDS, _unload_if_idle)
    _unload_timer.daemon = True
    _unload_timer.start()


def _transcribe_sync(audio_bytes: bytes, city: str) -> dict:
    from faster_whisper import decode_audio
    try:
        audio = decode_audio(io.BytesIO(audio_bytes), sampling_rate=_SAMPLE_RATE)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read the recording.")
    duration = len(audio) / _SAMPLE_RATE
    if duration > MAX_CLIP_SECONDS:
        raise HTTPException(status_code=422, detail=f"Recording is too long (max {MAX_CLIP_SECONDS}s).")
    if duration < MIN_CLIP_SECONDS:
        raise HTTPException(status_code=422, detail="Recording is too short.")
    with _model_lock:
        model = _get_model()
        _, _, all_probs = model.detect_language(audio)
        language = pick_language(all_probs)
        segments, _ = model.transcribe(
            audio, language=language, beam_size=1, vad_filter=True,
            condition_on_previous_text=False, without_timestamps=True,
            initial_prompt=build_prompt(language, city),
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    _schedule_unload()
    return {"text": text, "language": language, "duration": round(duration, 2)}


async def transcribe(audio_bytes: bytes, city: str = "lahore") -> dict:
    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=BUSY_WAIT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Voice search is busy. Please try again.")
    try:
        return await asyncio.to_thread(_transcribe_sync, audio_bytes, city)
    finally:
        _semaphore.release()


@router.get("/api/voice/status")
async def voice_status():
    return {"enabled": is_enabled(), "max_seconds": MAX_CLIP_SECONDS}


@router.post("/api/voice/transcribe")
@limiter.limit(_VOICE_RATE_LIMIT)
async def voice_transcribe(request: Request, city: str = Query("lahore")):
    if not is_enabled():
        raise HTTPException(status_code=404, detail="Voice search is not enabled.")
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if not (content_type.startswith("audio/") or content_type in ("video/webm", "video/mp4", "application/octet-stream")):
        raise HTTPException(status_code=415, detail="Send the recording as audio.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large.")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large.")
    if not body:
        raise HTTPException(status_code=422, detail="Recording is empty.")
    if _PLAYWRIGHT_SERVER:
        return {"text": _PLAYWRIGHT_TRANSCRIPT, "language": "en", "duration": 1.0}
    try:
        return await transcribe(body, city)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Voice transcription error")
        raise HTTPException(status_code=500, detail="Could not transcribe. Please try again.")
