"""Engine worker for the local voice studio (scripts/voicelab.py).

It runs INSIDE an isolated engine environment, never in the skill's own venv:

    <engine python> -I voicelab_worker.py  < job.json  > one JSON line on stdout

Jobs ({"op": ...}):
  probe       which engine modules this environment has
  tts         {"engine": "chatterbox"|"kokoro"|"qwen3", "items": [{text, out, seed, ...}]}  ->  16-bit mono WAV per item
  transcribe  {"files": [...], "model": "small.en", "language": "en"}  ->  words with times per file
  watermark   {"files": [...]}  ->  Chatterbox's PerTh watermark score per file (1.0 = present)
  quality     {"files": [...]}  ->  torchaudio SQUIM_OBJECTIVE estimates (a signal-quality proxy)

Only the standard library is imported at module level, so `probe` works in any Python.
Everything the engines print goes to stderr; stdout carries the single result line.
"""
from __future__ import annotations

import importlib.util
import json
import os
import struct
import sys
import time
import wave

MODULES = ("chatterbox", "kokoro", "qwen_tts", "faster_whisper", "perth", "torchaudio", "torch", "numpy")


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def write_wav16(path: str, samples, sr: int) -> float:
    """float samples in [-1, 1] -> 16-bit mono WAV. Returns the duration in seconds."""
    import numpy as np
    x = np.asarray(samples, dtype="float32").reshape(-1)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    return len(x) / float(sr)


def read_wav(path: str):
    """A WAV file (16-bit PCM or 32-bit float, any channel count) -> (mono float32 array, sample rate).
    Parsed by hand so no audio library is needed (faster-whisper's own decoder depends on PyAV)."""
    import numpy as np
    data = open(path, "rb").read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"not a WAV file: {path}")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if not fmt or raw is None:
        raise ValueError(f"unreadable WAV file: {path}")
    tag, ch, sr, bits = fmt
    if tag == 1 and bits == 16:
        x = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype("float32") / 32768.0
    elif tag == 3 and bits == 32:
        x = np.frombuffer(raw[: len(raw) // 4 * 4], dtype="<f4").astype("float32")
    else:
        raise ValueError(f"unsupported WAV encoding (tag {tag}, {bits} bit): {path}")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def resample(x, sr: int, to: int):
    import numpy as np
    if sr == to:
        return x
    n = int(round(len(x) * to / sr))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")


def seed_all(seed: int) -> None:
    import random
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2 ** 32))
    except ImportError:
        pass
    import torch
    torch.manual_seed(seed)


def op_probe(job: dict) -> dict:
    return {"python": sys.version.split()[0], "modules": {m: _has(m) for m in MODULES}}


def _threads() -> None:
    n = os.environ.get("FISH_TTS_THREADS")
    if n:
        import torch
        torch.set_num_threads(max(1, int(n)))


def tts_chatterbox(job: dict) -> list[dict]:
    import perth
    if getattr(perth, "PerthImplicitWatermarker", None) is None:
        # the watermark module failed to import (it needs pkg_resources); never generate without it
        raise RuntimeError("the PerTh watermark module is unavailable: install 'setuptools<81' in this environment")
    import torch
    from chatterbox.tts import ChatterboxTTS
    _threads()
    device = job.get("device") or ("cuda" if torch.cuda.is_available() else "cpu")
    model = ChatterboxTTS.from_pretrained(device=device)
    default, refs, out = model.conds, {}, []   # Conditionals hold graph tensors: share them, never deepcopy
    for it in job["items"]:
        t0 = time.time()
        seed_all(int(it.get("seed", 0)))
        ref = it.get("ref")
        ex = float(it.get("exaggeration", 0.5))
        if ref:
            if ref not in refs:
                model.prepare_conditionals(ref, exaggeration=ex)       # builds a new Conditionals object
                refs[ref] = model.conds
            model.conds = refs[ref]
        else:
            model.conds = default
        wav = model.generate(it["text"], exaggeration=ex, cfg_weight=float(it.get("cfg_weight", 0.5)),
                             temperature=float(it.get("temperature", 0.8)))
        dur = write_wav16(it["out"], wav.squeeze().detach().cpu().numpy(), model.sr)
        out.append({"out": it["out"], "sr": model.sr, "duration": round(dur, 3), "seconds": round(time.time() - t0, 2)})
    return out


def tts_kokoro(job: dict) -> list[dict]:
    import numpy as np
    from kokoro import KPipeline
    _threads()
    pipes, out = {}, []
    for it in job["items"]:
        t0 = time.time()
        voice = it.get("voice") or "af_heart"
        lang = voice[0]
        if lang not in pipes:
            pipes[lang] = KPipeline(lang_code=lang)
        seed_all(int(it.get("seed", 0)))
        chunks = []
        for res in pipes[lang](it["text"], voice=voice, speed=float(it.get("speed", 1.0))):
            a = res.audio if hasattr(res, "audio") else res[2]
            chunks.append(a.detach().cpu().numpy() if hasattr(a, "detach") else np.asarray(a))
        if not chunks:
            raise RuntimeError(f"kokoro returned no audio for: {it['text'][:60]}")
        dur = write_wav16(it["out"], np.concatenate(chunks), 24000)
        out.append({"out": it["out"], "sr": 24000, "duration": round(dur, 3), "seconds": round(time.time() - t0, 2)})
    return out


def tts_qwen3(job: dict) -> list[dict]:
    """Qwen3-TTS CustomVoice (Apache-2.0): a preset speaker directed by a plain-English `instruct` per sentence."""
    import torch
    from qwen_tts import Qwen3TTSModel
    _threads()
    cuda = torch.cuda.is_available() and job.get("device") != "cpu"
    items = job.get("items") or []
    model_id = job.get("model") or next((i["model"] for i in items if i.get("model")), None) or "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
    log_ = sys.stderr.write
    log_(f"qwen3: model {model_id}\n")
    model = Qwen3TTSModel.from_pretrained(model_id, device_map="cuda:0" if cuda else "cpu",
                                          dtype=torch.bfloat16 if cuda else torch.float32)
    out = []
    for it in job["items"]:
        t0 = time.time()
        seed_all(int(it.get("seed", 0)))
        kw = {"text": it["text"], "language": it.get("language") or "English", "speaker": it.get("voice") or "Ryan"}
        if it.get("instruct"):
            kw["instruct"] = it["instruct"]
        wavs, sr = model.generate_custom_voice(**kw)
        x = wavs[0]
        x = x.detach().float().cpu().numpy() if hasattr(x, "detach") else x
        dur = write_wav16(it["out"], x, sr)
        out.append({"out": it["out"], "sr": sr, "duration": round(dur, 3), "seconds": round(time.time() - t0, 2),
                    "device": "cuda" if cuda else "cpu"})
    return out


def op_tts(job: dict) -> dict:
    engine = job.get("engine")
    if engine == "chatterbox":
        return {"items": tts_chatterbox(job), "watermark": True}
    if engine == "kokoro":
        return {"items": tts_kokoro(job)}
    if engine == "qwen3":
        return {"items": tts_qwen3(job)}
    raise RuntimeError(f"unknown engine: {engine}")


def op_transcribe(job: dict) -> dict:
    from faster_whisper import WhisperModel
    model = WhisperModel(job.get("model") or "small.en", device="cpu", compute_type="int8")
    lang, out = job.get("language"), {}
    for f in job["files"]:
        x, sr = read_wav(f)
        segs, _ = model.transcribe(resample(x, sr, 16000), word_timestamps=True, language=lang, beam_size=int(job.get("beam_size", 5)),
                                   condition_on_previous_text=False)
        words = []
        for sg in segs:
            for w in (sg.words or []):
                if any(ch.isalnum() for ch in w.word):
                    words.append({"text": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
        out[f] = words
    return {"words": out}


def op_watermark(job: dict) -> dict:
    import perth
    if getattr(perth, "PerthImplicitWatermarker", None) is None:
        raise RuntimeError("the PerTh watermark module is unavailable: install 'setuptools<81' in this environment")
    wm, out = perth.PerthImplicitWatermarker(), {}
    for f in job["files"]:
        x, sr = read_wav(f)
        out[f] = float(wm.get_watermark(x, sample_rate=sr))
    return {"watermark": out}


def op_quality(job: dict) -> dict:
    """torchaudio SQUIM_OBJECTIVE: reference-free estimates of STOI, PESQ and SI-SDR (weights CC BY 4.0).
    A proxy for distortion and noise. It says nothing about how human a voice sounds."""
    import torch
    import torchaudio
    model = torchaudio.pipelines.SQUIM_OBJECTIVE.get_model()
    out = {}
    for f in job["files"]:
        x, sr = read_wav(f)
        with torch.no_grad():
            stoi, pesq, sdr = model(torch.from_numpy(resample(x, sr, 16000)).unsqueeze(0))
        out[f] = {"stoi": round(float(stoi[0]), 3), "pesq": round(float(pesq[0]), 2), "si_sdr": round(float(sdr[0]), 1)}
    return {"quality": out}


OPS = {"probe": op_probe, "tts": op_tts, "transcribe": op_transcribe, "watermark": op_watermark, "quality": op_quality}


def main() -> int:
    real = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)                      # engines print progress bars and warnings: keep stdout for the result
    sys.stdout = sys.stderr
    try:
        job = json.loads(sys.stdin.read() or "{}")
        fn = OPS.get(job.get("op"))
        if fn is None:
            raise RuntimeError(f"unknown op: {job.get('op')}")
        res = {"ok": True, **fn(job)}
    except Exception as e:  # noqa: BLE001 - the caller needs the message, not a traceback on stdout
        import traceback
        traceback.print_exc(file=sys.stderr)
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"[:600]}
    real.write(json.dumps(res) + "\n")
    real.flush()
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
