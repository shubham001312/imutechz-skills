"""Narration: text-to-speech with word timings, cached per line.

    python scripts/voice.py <project> [--provider elevenlabs|fish|edge-tts] [--force]
    python scripts/voice.py voices [--locale en-IN]          list voices (edge-tts; ElevenLabs if a key is set)
    python scripts/voice.py say "Hello {GGUF|G G U F}" --out hello.mp3 [--provider edge-tts]

Providers
  elevenlabs  default. POST /v1/text-to-speech/{voice_id}/with-timestamps
              (character alignment -> word timings). The key comes from
              ELEVENLABS_API_KEY in the environment or a gitignored .env in
              the project or skill folder. It is never printed or written.
              Default voice: fydPJq00SigRIaPxWgiS (English, India).
  fish        fish.audio cloud TTS + voice cloning (scripts/fishaudio.py). FISH_API_KEY; no fallback voice.
              Config: voice.fish.reference_id (or voice.fish.sample to clone once), target_wps (default 2.7).
  edge-tts    free fallback (Microsoft neural voices, needs internet), used
              automatically when no ElevenLabs key is present or the API call
              fails. Default en-IN-NeerjaNeural, rate -6%.

Narration markup: "{shown|spoken}" pairs. Captions show the left side, the
TTS reads the right side, e.g. "{GGUF|G G U F}", "{v0.3|version zero point
three}", "{10,631|ten thousand six hundred and thirty-one}". brief.voice.
pronunciations applies such pairs to every line automatically.

Writes build/voice/<provider>/<line>-<hash>.{mp3,wav,json} and
build/voice/clips.json, which `storyboard` uses to time every scene to its
narration and `render` uses to place every clip.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from fvcore import (FishError, ensure_project, ffmpeg_bin, load_json, load_yaml, log, main_guard, project_config,
                    run, save_json, secret, sha1, warn)
from storyboard import parse_say, scene_lines

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format={fmt}"


# ------------------------------------------------------------------ providers
def eleven_words(alignment: dict) -> list[dict]:
    """ElevenLabs character alignment -> words [{text, start, end, char}].

    Words are split on whitespace and timed by their letters and digits, so
    trailing punctuation does not stretch a word's end time.
    """
    chars = alignment["characters"]
    st, en = alignment["character_start_times_seconds"], alignment["character_end_times_seconds"]
    words, cur = [], None
    for i, ch in enumerate(chars):
        if ch.isspace():
            cur = None
            continue
        if cur is None:
            cur = {"text": "", "start": None, "end": None, "char": i}
            words.append(cur)
        cur["text"] += ch
        if ch.isalnum():
            if cur["start"] is None:
                cur["start"] = st[i]
            cur["end"] = en[i]
    return [w for w in words if w["start"] is not None]


def elevenlabs(say: str, cfg: dict, key: str, prev_text: str = "", next_text: str = "", speed: float | None = None) -> tuple[bytes, list[dict]]:
    c = cfg["elevenlabs"]
    vs = dict(c.get("voice_settings") or {})
    if speed:
        vs["speed"] = round(speed, 3)
    body = {"text": say, "model_id": c.get("model_id", "eleven_multilingual_v2"), "voice_settings": vs}
    if c.get("language_code"):
        body["language_code"] = c["language_code"]
    if c.get("use_context"):
        if prev_text:
            body["previous_text"] = prev_text
        if next_text:
            body["next_text"] = next_text
    url = ELEVEN_URL.format(voice_id=c["voice_id"], fmt=c.get("output_format", "mp3_44100_128"))
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            js = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise FishError(f"ElevenLabs HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise FishError(f"ElevenLabs unreachable: {e.reason}")
    al = js.get("alignment") or js.get("normalized_alignment")
    return base64.b64decode(js["audio_base64"]), eleven_words(al)


async def _edge(say: str, fb: dict, rate: str | None) -> tuple[bytes, list[dict]]:
    import edge_tts
    com = edge_tts.Communicate(say, fb.get("voice", "en-IN-NeerjaNeural"), rate=rate or fb.get("rate", "+0%"),
                               pitch=fb.get("pitch", "+0Hz"), volume=fb.get("volume", "+0%"), boundary="WordBoundary")
    audio, words, cursor = bytearray(), [], 0
    async for ch in com.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            t = ch["text"]
            i = say.find(t, cursor)
            if i < 0:
                i = say.lower().find(t.lower(), cursor)
            if i < 0:
                i = cursor
            cursor = i + len(t)
            words.append({"text": t, "start": ch["offset"] / 1e7, "end": (ch["offset"] + ch["duration"]) / 1e7, "char": i})
    if not audio:
        raise FishError("edge-tts returned no audio (offline?)")
    return bytes(audio), words


def edge(say: str, fb: dict, rate: str | None = None) -> tuple[bytes, list[dict]]:
    try:
        return asyncio.run(_edge(say, fb, rate))
    except FishError:
        raise
    except Exception as e:  # network errors surface as aiohttp exceptions
        raise FishError(f"edge-tts failed: {type(e).__name__}: {e}")


_KOKORO = {}


def _kokoro_raw(say: str, kc: dict):
    """Kokoro-82M (local, Apache-2.0). Returns (float32 samples @24 kHz, word list or None)."""
    try:
        from kokoro import KPipeline
        import numpy as np
    except ImportError:
        raise FishError('kokoro is not installed: .venv pip install kokoro soundfile (or pick an edge voice)')
    v = kc.get("voice", "af_heart")
    lang = v[0]
    if lang not in _KOKORO:
        _KOKORO[lang] = KPipeline(lang_code=lang)
    chunks, words, off = [], [], 0.0
    for res in _KOKORO[lang](say, voice=v, speed=kc.get("speed", 1.0)):
        audio = res.audio if hasattr(res, "audio") else res[2]
        a = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
        for tok in (getattr(res, "tokens", None) or []):
            if getattr(tok, "start_ts", None) is not None and tok.text.strip() and any(ch.isalnum() for ch in tok.text):
                words.append({"text": tok.text, "start": off + tok.start_ts, "end": off + (tok.end_ts or tok.start_ts + 0.2)})
        chunks.append(a)
        off += len(a) / 24000
    return np.concatenate(chunks).astype("float32"), (words or None)


def _to_mp3(samples) -> bytes:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        raw, mp3 = Path(td) / "k.f32", Path(td) / "k.mp3"
        raw.write_bytes(samples.tobytes())
        run([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "f32le", "-ar", "24000", "-ac", "1", "-i", str(raw), "-b:a", "160k", str(mp3)])
        return mp3.read_bytes()


def kokoro_audio(say: str, kc: dict) -> bytes:
    """mp3 bytes (used for auditions)."""
    return _to_mp3(_kokoro_raw(say, kc)[0])


def kokoro(say: str, kc: dict) -> tuple[bytes, list[dict]]:
    samples, words = _kokoro_raw(say, kc)
    if words is None:  # no token timestamps in this kokoro version: spread words by character length
        dur = len(samples) / 24000
        toks = [(m.group(0), m.start()) for m in re.finditer(r"\S+", say)]
        total = sum(len(t) + 1 for t, _ in toks) or 1
        t, words = 0.08, []
        for tok, ch in toks:
            d = (dur - 0.16) * (len(tok) + 1) / total
            words.append({"text": tok, "start": round(t, 3), "end": round(t + d * 0.9, 3), "char": ch})
            t += d
        warn("kokoro: word timings estimated (install faster-whisper for exact alignment)")
    else:
        cursor = 0
        for w in words:
            i = say.find(w["text"], cursor)
            w["char"] = i if i >= 0 else cursor
            cursor = (i + len(w["text"])) if i >= 0 else cursor
    return _to_mp3(samples), words


def pick_provider(cfg: dict, project: Path | None, want: str | None = None) -> tuple[str, str]:
    """(provider, key). ElevenLabs only with a key; kokoro only when installed; otherwise the fallback."""
    v = cfg["voice"]
    prov = want or v.get("provider", "elevenlabs")
    if prov == "none":
        return "none", ""
    if prov in ("chatterbox", "qwen3"):            # local studio engines: run in their own environment (voicelab.py)
        return prov, ""
    if prov == "kokoro" and v.get("studio"):
        return "kokoro", ""
    if prov == "kokoro":
        try:
            import kokoro  # noqa: F401
            return "kokoro", ""
        except ImportError:
            warn(f"kokoro is not installed: using the fallback voice {v['fallback'].get('voice')} (edge-tts)")
            return "edge-tts", ""
    if prov == "fish":                              # cloud, no silent substitution: a missing key stops the run
        import fishaudio
        return "fish", fishaudio.need_key(project)
    key = secret("ELEVENLABS_API_KEY", project) if prov == "elevenlabs" else ""
    if prov == "elevenlabs" and not key:
        warn(f"ELEVENLABS_API_KEY is not set (env or .env): using the free fallback voice {v['fallback'].get('voice')} (edge-tts) as a stand-in")
        prov = "edge-tts"
    return prov, key


# ------------------------------------------------------------------ audio helpers
def decode_wav(src: Path, dst: Path) -> float:
    """mp3 -> 48 kHz mono float WAV; returns the duration in seconds."""
    run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "48000", "-c:a", "pcm_f32le", str(dst)])
    data = dst.read_bytes()
    i = data.find(b"data")
    n = int.from_bytes(data[i + 4:i + 8], "little")
    return n / 4 / 48000


def voice_settings_summary(cfg: dict, provider: str) -> dict:
    v = cfg["voice"]
    if provider == "elevenlabs":
        e = v["elevenlabs"]
        return {"provider": "elevenlabs", "voice_id": e["voice_id"], "voice_url": e.get("voice_url"), "model_id": e.get("model_id"),
                "language": v.get("language"), "voice_settings": e.get("voice_settings")}
    if provider == "fish":
        fc = v.get("fish") or {}
        return {"provider": "fish", "reference_id": fc.get("reference_id"), "model": fc.get("model", "s2.1-pro"), "format": fc.get("format", "mp3"),
                "speed": fc.get("speed", 1.0), "target_wps": fc.get("target_wps", 2.7), "tolerance": fc.get("tolerance", 0.2),
                "temperature": fc.get("temperature", 0.6), "emotion": fc.get("emotion", True), "tags": fc.get("tags"), "base_tag": fc.get("base_tag"),
                "language": v.get("language")}
    if provider == "edge-tts":
        f = v["fallback"]
        return {"provider": "edge-tts", "voice": f.get("voice"), "rate": f.get("rate"), "pitch": f.get("pitch"), "language": v.get("language"),
                "stand_in_for": {"provider": "elevenlabs", "voice_id": v["elevenlabs"]["voice_id"]} if v.get("provider") == "elevenlabs" else None}
    if provider == "kokoro":
        return {"provider": "kokoro", **(v.get("kokoro") or {}), "language": v.get("language")}
    return {"provider": provider}


def tighten(wav: Path, words: list[dict], max_gap: float) -> tuple[list[dict], float]:
    """Remove dead air: find silent runs in the AUDIO (engines often hide a comma's pause inside the previous
    word's timing), keep at most max_gap of each, drop leading and trailing silence, remap the word times.
    The idea behind auto-editor, applied per line so word timings stay exact. Returns (words, new duration)."""
    import struct
    import numpy as np
    data = wav.read_bytes()
    i = data.find(b"data")
    x = np.frombuffer(data[i + 8:i + 8 + int.from_bytes(data[i + 4:i + 8], "little")], dtype=np.float32).copy()
    sr, hop = 48000, 480
    n = len(x) // hop
    if n < 10:
        return words, len(x) / sr
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    silent = rms < np.percentile(rms, 95) * 0.04   # about -28 dB under the speech level
    keep, cuts, k = [], [], 0                       # cuts = (start_s, removed_s)
    while k < n:
        if silent[k]:
            j = k
            while j < n and silent[j]:
                j += 1
            L = (j - k) * hop / sr
            edge = k == 0 or j == n
            allow = 0.02 if edge else max_gap
            if L > allow + 0.02:
                c0 = k + int((L - (L - allow)) / 2 * sr / hop) if not edge else (k if k == 0 else k + int(allow * sr / hop))
                c1 = c0 + int((L - allow) * sr / hop)
                cuts.append((c0 * hop, c1 * hop))
            k = j
        else:
            k += 1
    if not cuts:
        return words, len(x) / sr
    fade, last, out = 240, 0, []
    for c0, c1 in cuts:
        seg = x[last:c0].copy()
        m = min(fade, len(seg))
        if m:
            seg[-m:] *= np.linspace(1, 0, m)
        if out and len(seg) >= fade:
            seg[:fade] *= np.linspace(0, 1, fade)
        out.append(seg)
        last = c1
    tail = x[last:].copy()
    m = min(fade, len(tail))
    if m:
        tail[:m] *= np.linspace(0, 1, m)
    out.append(tail)

    def remap(t: float) -> float:
        s = t * sr
        removed = 0
        for c0, c1 in cuts:
            if s >= c1:
                removed += c1 - c0
            elif s > c0:
                return (c0 - removed) / sr
        return (s - removed) / sr
    words = [{**w, "start": round(remap(w["start"]), 3), "end": round(remap(w["end"]), 3)} for w in words]
    y = np.concatenate(out).astype("<f4")
    pcm = y.tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, sr, sr * 4, 4, 32) + b"data" + struct.pack("<I", len(pcm))
    wav.write_bytes(hdr + pcm)
    return words, len(y) / sr


# Per-scene emotion: `mood:` on a scene sets the delivery of its lines (speed multiplier, edge pitch, ElevenLabs style).
# Punctuation also shapes prosody on every engine: "..." pauses, "?" lifts, "!" lifts and hits, short sentences punch.
MOODS = {"neutral": (1.0, 0, 0.0), "curious": (0.98, 2, 0.05), "tense": (0.94, -3, 0.15), "urgent": (1.1, 2, 0.2),
         "excited": (1.1, 5, 0.25), "warm": (0.95, 0, 0.1), "serious": (0.92, -5, 0.1), "reflective": (0.88, -3, 0.05), "triumphant": (1.02, 4, 0.3)}


def _mood_cfg(cfg: dict, mood: str | None) -> dict:
    if not mood or mood not in MOODS:
        if mood:
            warn(f"unknown mood '{mood}': one of {sorted(MOODS)}")
        return cfg
    import copy
    sp, pitch, style = MOODS[mood]
    c = copy.deepcopy(cfg)
    v = c["voice"]
    if v.get("kokoro"):
        v["kokoro"]["speed"] = round(v["kokoro"].get("speed", 1.0) * sp, 3)
    fb = v.get("fallback") or {}
    rate = int(re.sub(r"[^\d-]", "", str(fb.get("rate", "+0%"))) or 0)
    base_p = int(re.sub(r"[^\d-]", "", str(fb.get("pitch", "+0Hz"))) or 0)
    fb["rate"] = f"{round((1 + rate / 100) * sp * 100 - 100):+d}%"
    fb["pitch"] = f"{base_p + pitch:+d}Hz"
    vs = (v.get("elevenlabs") or {}).get("voice_settings")
    if vs:
        vs["speed"] = round(min(1.2, max(0.7, vs.get("speed", 1.0) * sp)), 3)
        vs["style"] = round(min(1.0, vs.get("style", 0) + style), 3)
    return c


def _fish_take(say: str, tag: str | None, cfg: dict, key: str, mp3: Path, wav: Path, max_gap) -> tuple[list[dict], float]:
    """One fish line: tagged request, estimated word times, tighten, and at most one regeneration at a corrected speed."""
    import fishaudio
    fc = fishaudio.fish_cfg(cfg["voice"])
    text = fishaudio.tag_text(say, tag, fc)
    speed = float(fc.get("speed", 1.0))
    n = len(say.split())
    for attempt in range(2):
        mp3.write_bytes(fishaudio.tts(text, fc, key, speed))
        dur = decode_wav(mp3, wav)
        words = fishaudio.word_times(say, wav)
        if max_gap and words:
            try:
                words, dur = tighten(wav, words, float(max_gap))
            except ImportError:
                warn("numpy is missing: pauses inside lines were not tightened")
        ns = fishaudio.next_speed(speed, n, (words[-1]["end"] - words[0]["start"]) if words else 0, fc) if attempt == 0 else None
        if ns is None:
            break
        speed = ns
    return words, dur


def synth_line(say: str, provider: str, key: str, cfg: dict, outdir: Path, line_id: str, ctx=("", ""), force=False, tag: str | None = None) -> dict:
    """Synthesize one line (cached by text + settings). Returns the clip record."""
    setting = {"say": say, **voice_settings_summary(cfg, provider)}
    if provider == "fish":
        setting["tag"] = tag
    if provider == "elevenlabs" and cfg["voice"]["elevenlabs"].get("use_context"):
        setting["ctx"] = list(ctx)
    max_gap = (cfg.get("pacing") or {}).get("max_word_gap")
    if max_gap:
        setting["max_gap"] = max_gap
    h = sha1(setting)
    stem = outdir / f"{line_id}-{h}"
    mp3, wav, js = stem.with_suffix(".mp3"), stem.with_suffix(".wav"), stem.with_suffix(".json")
    if force or not js.exists():
        if provider == "fish":
            words, dur = _fish_take(say, tag, cfg, key, mp3, wav, max_gap)
            if not words:
                raise FishError(f"{line_id}: the TTS returned no word timings")
            js.write_text(json.dumps({"setting": setting, "duration": dur, "words": words}, indent=1, ensure_ascii=False), encoding="utf-8")
            audio = None
        elif provider == "elevenlabs":
            audio, words = elevenlabs(say, cfg["voice"], key, ctx[0], ctx[1])
        elif provider == "kokoro":
            audio, words = kokoro(say, cfg["voice"].get("kokoro") or {})
        else:
            audio, words = edge(say, cfg["voice"]["fallback"])
        if audio is not None:
            if not words:
                raise FishError(f"{line_id}: the TTS returned no word timings")
            mp3.write_bytes(audio)
            dur = decode_wav(mp3, wav)
            if max_gap:
                try:
                    words, dur = tighten(wav, words, float(max_gap))
                except ImportError:
                    warn("numpy is missing: pauses inside lines were not tightened")
            js.write_text(json.dumps({"setting": setting, "duration": dur, "words": words}, indent=1, ensure_ascii=False), encoding="utf-8")
    meta = json.loads(js.read_text(encoding="utf-8"))
    w = meta["words"]
    return {"say": say, "provider": provider, "hash": h, "wav": str(wav), "mp3": str(mp3), "duration": round(meta["duration"], 3),
            "speech_start": round(w[0]["start"], 3), "speech_end": round(w[-1]["end"], 3), "words": w}


def synthesize(project: Path, provider: str | None = None, force: bool = False) -> dict:
    """Voice every narration line of the storyboard. Writes build/voice/clips.json."""
    project = ensure_project(project)
    cfg = project_config(project)
    sb = load_yaml(project / "storyboard.yaml")
    prov, key = pick_provider(cfg, project, provider)
    out = project / "build" / "voice"
    if prov in ("chatterbox", "kokoro", "qwen3") and (prov in ("chatterbox", "qwen3") or cfg["voice"].get("studio")):
        import voicelab                            # the local voice studio: references/local-voices.md
        return voicelab.synthesize(project, cfg, prov, True if force else False)
    if prov == "none":
        save_json(out / "clips.json", {"provider": "none", "clips": {}})
        log("voice: none (music only)")
        return {"provider": "none", "clips": {}}
    pron = (cfg["brief"].get("voice") or {}).get("pronunciations") or {}
    if prov == "fish":                              # voice.fish.sample without an id: clone once, write the id back
        import fishaudio
        fishaudio.ensure_reference(project, cfg, key)
    lines, moods = [], {}
    for s in sb["scenes"]:
        for ln in scene_lines(s, pron):
            lines.append(ln)
            moods[ln["id"]] = s.get("mood")
    clips, used = {}, prov
    for k, ln in enumerate(lines):
        ctx = (lines[k - 1]["say"] if k else "", lines[k + 1]["say"] if k + 1 < len(lines) else "")
        pdir = out / used
        pdir.mkdir(parents=True, exist_ok=True)
        try:
            clip = synth_line(ln["say"], used, key, _mood_cfg(cfg, moods.get(ln["id"])), pdir, ln["id"], ctx, force, ln.get("tag"))
        except FishError as e:
            if used == "elevenlabs":
                warn(f"{e}; falling back to edge-tts for the rest of this run")
                used = "edge-tts"
                pdir = out / used
                pdir.mkdir(parents=True, exist_ok=True)
                clip = synth_line(ln["say"], used, key, _mood_cfg(cfg, moods.get(ln["id"])), pdir, ln["id"], ctx, force)
            else:
                raise
        clip["wav"] = str(Path(clip["wav"]).relative_to(project)).replace("\\", "/")
        clip["mp3"] = str(Path(clip["mp3"]).relative_to(project)).replace("\\", "/")
        clips[ln["id"]] = clip
        log(f"  {ln['id']:<18} {clip['speech_end']:5.2f}s  {ln['display'][:70]}")
    res = {"provider": used, "voice": voice_settings_summary(cfg, used), "post": cfg["voice"].get("post", ""), "clips": clips}
    save_json(out / "clips.json", res)
    log(f"voice: {len(clips)} lines via {used} -> {out / 'clips.json'}")
    return res


def build_track(project: Path, timeline: dict, out_wav: Path, post: str | None = None) -> Path | None:
    """Place every voiced line at its time on one mono track (adelay + amix), then apply the post chain."""
    lines = [v for v in timeline.get("voice_lines", []) if v.get("wav")]
    if not lines:
        return None
    dur = timeline["duration"] + 1.0
    args = [ffmpeg_bin(), "-y", "-loglevel", "error"]
    parts = []
    for i, v in enumerate(lines):
        args += ["-i", str(Path(project) / v["wav"])]
        ms = int(round(v["at"] * 1000))
        parts.append(f"[{i}]adelay={ms}|{ms},apad=whole_dur={dur}[v{i}]")
    mix = "".join(f"[v{i}]" for i in range(len(lines))) + f"amix=inputs={len(lines)}:normalize=0:duration=longest,atrim=0:{dur}"
    if post:
        mix += "," + post
    fc = ";".join(parts) + ";" + mix + "[out]"
    script = out_wav.with_suffix(".filter.txt")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(fc, encoding="utf-8")
    run(args + ["-filter_complex_script", str(script), "-map", "[out]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_f32le", str(out_wav)])
    return out_wav


# ------------------------------------------------------------------ catalogue
def list_voices(locale: str | None = None, project: Path | None = None) -> list[dict]:
    out = []
    try:
        import edge_tts
        for v in asyncio.run(edge_tts.list_voices()):
            if not locale or v["Locale"].lower().startswith(locale.lower()):
                out.append({"provider": "edge-tts", "voice": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]})
    except Exception as e:
        warn(f"edge-tts voice list unavailable: {e}")
    key = secret("ELEVENLABS_API_KEY", project)
    if key:
        try:
            req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
            with urllib.request.urlopen(req, timeout=30) as r:
                for v in json.loads(r.read().decode("utf-8")).get("voices", []):
                    out.append({"provider": "elevenlabs", "voice": v.get("voice_id"), "name": v.get("name"), "labels": v.get("labels")})
        except Exception as e:
            warn(f"ElevenLabs voice list unavailable: {e}")
    return out


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="<project> | voices | say")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--provider", choices=["elevenlabs", "fish", "edge-tts", "none"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--locale", default=None)
    ap.add_argument("--out", default="say.mp3")
    a = ap.parse_args(argv)
    if a.target == "voices":
        for v in list_voices(a.locale):
            log(json.dumps(v, ensure_ascii=False))
        return 0
    if a.target == "say":
        from fvcore import defaults
        cfg = {"voice": defaults()["voice"]}
        prov, key = pick_provider(cfg, None, a.provider)
        disp, say, _ = parse_say(a.text or "")
        audio, words = elevenlabs(say, cfg["voice"], key) if prov == "elevenlabs" else edge(say, cfg["voice"]["fallback"])
        Path(a.out).write_bytes(audio)
        log(json.dumps({"out": a.out, "provider": prov, "words": len(words), "display": disp}))
        return 0
    synthesize(Path(a.target), a.provider, a.force)
    return 0


if __name__ == "__main__":
    main_guard(cli)
