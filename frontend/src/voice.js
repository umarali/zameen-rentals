/** Voice search: record a short clip, transcribe it on our server
 *  (/api/voice/transcribe, faster-whisper), and hand the text to the NL search. */

import { $, esc } from './utils.js';
import { S } from './state.js';
import { track } from './analytics.js';

const MAX_MS = 12000;        // server rejects clips over 15s
const SILENCE_MS = 1500;     // stop this long after the user stops talking
const SPEECH_LEVEL = 0.03;   // RMS above this counts as speech
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];

const MIC_SVG = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"/></svg>';
const STOP_SVG = '<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
const SPINNER_SVG = '<svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>';

const BTN_BASE = 'w-8 h-8 mr-1 rounded-full flex items-center justify-center shrink-0 transition-colors disabled:opacity-50';
const BTN_IDLE = 'text-gray-400 hover:text-brand-600 hover:bg-brand-50';
const BTN_RECORDING = 'bg-red-500 text-white animate-pulse';

function trackVoiceSearch({ phase, durationMs, language, ok, error }) {
  track('voice_search', {
    phase,
    duration_ms: durationMs ?? null,
    language: language || null,
    ok: ok ?? null,
    error: error || null,
  });
}

function showStatus(html) {
  const el = $('#nlParsed');
  if (!el) return;
  el.classList.remove('hidden');
  el.classList.add('flex', 'voice-status');
  el.setAttribute('role', 'status');
  el.innerHTML = html;
}

function hideStatus() {
  const el = $('#nlParsed');
  if (!el) return;
  el.classList.add('hidden');
  el.classList.remove('flex');
}

function micErrorMessage(err) {
  if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') return 'Microphone access is blocked. Allow it in your browser settings to search by voice.';
  if (err?.name === 'NotFoundError') return 'No microphone found.';
  return 'Could not start the microphone.';
}

/** Stop the recorder once the user has spoken and then gone quiet. */
function watchSilence(stream, onSilence) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return () => {};
  const ctx = new Ctx();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  let heardSpeech = false, quietSince = 0;
  const timer = setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    const rms = Math.sqrt(sum / buf.length);
    const now = performance.now();
    if (rms > SPEECH_LEVEL) { heardSpeech = true; quietSince = 0; }
    else if (heardSpeech) {
      quietSince ||= now;
      if (now - quietSince > SILENCE_MS) onSilence();
    }
  }, 100);
  return () => { clearInterval(timer); ctx.close().catch(() => {}); };
}

/**
 * Add a mic button before `anchor` (default: the NL search button). It shows
 * only when the server has voice search on and the browser can record.
 * `onTranscript(text)` gets the recognised text.
 */
export async function initVoiceSearch({ anchor = $('#nlSearchBtn'), onTranscript } = {}) {
  if (!anchor || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') return;
  let status = null;
  try {
    const r = await fetch('/api/voice/status');
    if (r.ok) status = await r.json();
  } catch { /* offline or old server: no mic */ }
  if (!status?.enabled) return;

  const btn = document.createElement('button');
  btn.id = 'nlMicBtn';
  btn.type = 'button';
  anchor.before(btn);

  let recorder = null, stopWatching = null, maxTimer = null, tickTimer = null, startedAt = 0;

  const setState = (state) => {
    const recording = state === 'recording';
    btn.className = `${BTN_BASE} ${recording ? BTN_RECORDING : BTN_IDLE}`;
    btn.innerHTML = recording ? STOP_SVG : MIC_SVG;
    btn.disabled = state === 'busy';
    btn.setAttribute('aria-pressed', String(recording));
    btn.setAttribute('aria-label', recording ? 'Stop recording' : 'Search by voice');
    btn.title = recording ? 'Stop recording' : 'Search by voice';
  };
  setState('idle');

  const stop = () => {
    clearTimeout(maxTimer); clearInterval(tickTimer);
    stopWatching?.(); stopWatching = null;
    if (recorder?.state === 'recording') { setState('busy'); recorder.stop(); }
  };

  const send = async (blob, durationMs) => {
    setState('busy');
    showStatus(`<span class="inline-flex items-center gap-1.5 text-gray-400">${SPINNER_SVG}Transcribing...</span>`);
    try {
      const r = await fetch('/api/voice/transcribe?city=' + encodeURIComponent(S.city), {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || 'Could not transcribe. Please try again.');
      const text = (d.text || '').trim();
      trackVoiceSearch({ phase: 'transcribed', durationMs, language: d.language, ok: Boolean(text) });
      if (!text) { showStatus("Didn't catch that. Tap the mic and try again."); return; }
      hideStatus();
      onTranscript?.(text);
    } catch (err) {
      trackVoiceSearch({ phase: 'transcribed', durationMs, ok: false, error: 'server' });
      showStatus(esc(err.message || 'Could not transcribe. Please try again.'));
    } finally {
      setState('idle');
    }
  };

  const start = async () => {
    // Disable immediately: getUserMedia can remain pending at the permission prompt.
    setState('busy');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      trackVoiceSearch({ phase: 'mic_error', error: err?.name || 'unknown' });
      showStatus(esc(micErrorMessage(err)));
      setState('idle');
      return;
    }
    try {
      const mimeType = MIME_TYPES.find(t => MediaRecorder.isTypeSupported?.(t));
      recorder = new MediaRecorder(stream, { ...(mimeType && { mimeType }), audioBitsPerSecond: 32000 });
      const activeRecorder = recorder;
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = () => {
        clearTimeout(maxTimer); clearInterval(tickTimer);
        stopWatching?.(); stopWatching = null;
        stream.getTracks().forEach(t => t.stop());
        const durationMs = Math.round(performance.now() - startedAt);
        const blob = new Blob(chunks, { type: activeRecorder.mimeType || mimeType || 'audio/webm' });
        recorder = null;
        if (durationMs < 400 || blob.size < 500) {
          setState('idle');
          showStatus("Didn't catch that. Tap the mic and try again.");
          return;
        }
        send(blob, durationMs);
      };
      recorder.onerror = () => {
        // A delayed stop event from the failed recorder must not clear a retry.
        activeRecorder.onstop = null;
        activeRecorder.onerror = null;
        stop();
        stream.getTracks().forEach(t => t.stop());
        recorder = null;
        setState('idle');
        showStatus('Recording failed. Tap the mic and try again.');
      };
      startedAt = performance.now();
      recorder.start();
      setState('recording');
      trackVoiceSearch({ phase: 'started' });
      $('#nlSuggestions')?.classList.add('hidden');
      const tick = () => {
        const secs = Math.floor((performance.now() - startedAt) / 1000);
        showStatus(`<span class="inline-flex items-center gap-1.5 text-red-600"><span class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span><span class="hidden sm:inline">Listening...</span> 0:${String(secs).padStart(2, '0')}<span class="hidden sm:inline"> · tap to stop</span></span>`);
      };
      tick();
      tickTimer = setInterval(tick, 500);
      maxTimer = setTimeout(stop, MAX_MS);
      // Recording still works if the optional audio analyser is unavailable.
      try { stopWatching = watchSilence(stream, stop); } catch { /* use manual/maximum stop */ }
    } catch (err) {
      clearTimeout(maxTimer); clearInterval(tickTimer);
      stopWatching?.(); stopWatching = null;
      if (recorder) { recorder.onstop = null; recorder.onerror = null; }
      if (recorder?.state === 'recording') recorder.stop();
      recorder = null;
      stream.getTracks().forEach(t => t.stop());
      setState('idle');
      showStatus('Could not start recording. Tap the mic and try again.');
      trackVoiceSearch({ phase: 'mic_error', error: err?.name || 'recorder' });
    }
  };

  btn.addEventListener('click', () => { recorder ? stop() : start(); });
}
