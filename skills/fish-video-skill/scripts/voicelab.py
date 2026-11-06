"""Local voice studio: free narration made on this machine, with measured checks.

    fishvideo voice setup --engine chatterbox|kokoro|all [--gpu] [--dry-run]
    fishvideo voice engines                                  which engines are installed
    fishvideo voice say "text" --out a.wav [--engine E --gender G --style S --pace P]
    fishvideo voice audition --matrix [--out DIR | <project>] [--genders male,female --styles airy,soft]
    fishvideo voice check <project> [--fix] [--no-transcript] [--quality]
    fishvideo voice redo <project> <line-id> [--seed N --mood M --style S --exaggeration X]
    fishvideo voice measure <audio> ...

In brief.yaml:   voice: {provider: chatterbox, studio: {gender: female, style: airy, pace: natural}}

The engines (Chatterbox, Kokoro) and faster-whisper live in their own environments under
<skill>/.tts/<engine>, because their pinned dependencies conflict with the skill's venv. This module
never imports them: it sends JSON jobs to scripts/voicelab_worker.py running inside that environment.

What it does for every narration line: one sentence at a time, an emotion setting per sentence, real
pauses between sentences, a transcript check on every take (regenerated with a new seed when the words
are wrong), a closed loop that steers the pace to a target in words per second, then a gentle post chain.
Nothing here can hear: every label and check is a measurement. Audition the result before publishing.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from fvcore import (IS_WIN, SCRIPTS, SKILL, FishError, ensure_project, ffmpeg_bin, last_json_line, load_json, load_yaml, log,
                    main_guard, project_config, save_json, save_yaml, sha1, warn)

ENGINES = ("chatterbox", "kokoro")
SUBCOMMANDS = ("setup", "engines", "say", "audition", "check", "redo", "measure", "words")
SR_OUT = 48000
_CFG = None
_PROBE: dict[str, dict] = {}


def config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = load_yaml(SKILL / "config" / "voicelab.yaml")
    return _CFG


# ------------------------------------------------------------------ audio in and out
def read_wav(path: Path | str):
    """16-bit PCM or 32-bit float WAV -> (mono float32 array, sample rate)."""
    import numpy as np
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise FishError(f"not a WAV file: {path}")
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
        raise FishError(f"unreadable WAV file: {path}")
    tag, ch, sr, bits = fmt
    if tag == 1 and bits == 16:
        x = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype("float32") / 32768.0
    elif tag == 3 and bits == 32:
        x = np.frombuffer(raw[: len(raw) // 4 * 4], dtype="<f4").astype("float32")
    else:
        raise FishError(f"unsupported WAV encoding (tag {tag}, {bits} bit): {path}")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(path: Path | str, x, sr: int) -> Path:
    """Mono 32-bit float WAV (the format the renderer places on the voice track)."""
    import numpy as np
    pcm = np.asarray(x, dtype="<f4").tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, sr, sr * 4, 4, 32) + b"data" + struct.pack("<I", len(pcm))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(hdr + pcm)
    return p


def load_audio(path: Path | str):
    """Any audio file -> (mono float32, sample rate). WAV is read directly; other formats go through ffmpeg."""
    import numpy as np
    p = Path(path)
    if not p.exists():
        raise FishError(f"missing file: {p}")
    if p.suffix.lower() == ".wav":
        try:
            return read_wav(p)
        except FishError:
            pass
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR_OUT), "-f", "f32le", "-"], capture_output=True)
    if r.returncode != 0:
        raise FishError(f"cannot decode {p}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    return np.frombuffer(r.stdout, dtype="<f4").astype("float32"), SR_OUT


# ------------------------------------------------------------------ measurements (numpy only; nothing here listens)
def _speech_mask(x, sr: int, hop_s: float = 0.01, rel_db: float = -30.0):
    import numpy as np
    hop = max(1, int(sr * hop_s))
    n = len(x) // hop
    if n == 0:
        return np.zeros(0, dtype=bool), hop
    rms = np.sqrt((x[: n * hop].reshape(n, hop).astype("float64") ** 2).mean(1) + 1e-12)
    thr = max(np.percentile(rms, 95) * 10 ** (rel_db / 20), 10 ** (-60 / 20))
    return rms > thr, hop


def pitch(x, sr: int) -> tuple[float | None, float | None]:
    """Median fundamental frequency of the voiced frames (Hz) and its interquartile range.
    Autocorrelation on 40 ms frames at 16 kHz, searched between 60 and 400 Hz."""
    import numpy as np
    if sr != 16000:
        n = int(round(len(x) * 16000 / sr))
        if n < 2:
            return None, None
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    win, hop, lo, hi = 640, 320, 16000 // 400, 16000 // 60
    if len(x) < win * 2:
        return None, None
    x = np.asarray(x, dtype="float64")
    idx = np.arange(0, len(x) - win, hop)
    n = len(idx)
    rms = np.sqrt(np.array([(x[i:i + win] ** 2).mean() for i in idx]) + 1e-12)
    idx = idx[rms > max(np.percentile(rms, 95) * 10 ** (-25 / 20), 1e-4)]
    f0 = []
    for c0 in range(0, len(idx), 2000):                        # in batches: a long file stays small in memory
        fr = np.stack([x[i:i + win] for i in idx[c0:c0 + 2000]])
        fr = fr - fr.mean(1, keepdims=True)
        spec = np.fft.rfft(fr, 2 * win, axis=1)
        ac = np.fft.irfft(spec.real ** 2 + spec.imag ** 2, axis=1)[:, :win]
        ac /= ac[:, :1] + 1e-12
        for row in ac[:, lo:hi]:
            k = int(row.argmax())
            pk = row[k]
            if pk < 0.45:
                continue
            # the shortest lag that is nearly as strong: an octave-down error picks twice the true period
            for j in np.flatnonzero(row >= 0.9 * pk):
                if 0 < j < len(row) - 1 and row[j] >= row[j - 1] and row[j] >= row[j + 1]:
                    k = int(j)
                    break
            f0.append(16000.0 / (lo + k))
    if len(f0) < 5:
        return None, None
    q1, med, q3 = np.percentile(f0, [25, 50, 75])
    return round(float(med), 1), round(float(q3 - q1), 1)


def air_db(x, sr: int, split: float = 6000.0) -> float | None:
    """Energy above `split` Hz relative to the whole speech signal, in dB. Higher is brighter; too high is hiss."""
    import numpy as np
    if sr < split * 2.2:
        return None
    mask, hop = _speech_mask(x, sr)
    if not mask.any():
        return None
    sp = x[: len(mask) * hop].reshape(len(mask), hop)[mask].reshape(-1).astype("float64")
    nfft = 2048
    if len(sp) < nfft:
        return None
    k = (len(sp) - nfft) // (nfft // 2) + 1
    fr = np.stack([sp[i * (nfft // 2): i * (nfft // 2) + nfft] for i in range(k)]) * np.hanning(nfft)
    p = (np.abs(np.fft.rfft(fr, axis=1)) ** 2).mean(0)
    f = np.fft.rfftfreq(nfft, 1 / sr)
    tot = p[f >= 50].sum()
    return round(float(10 * np.log10(p[f >= split].sum() / tot + 1e-15)), 1) if tot > 0 else None


def measure(x, sr: int, n_words: int | None = None, pause_min: float = 0.2) -> dict:
    """Everything `voice check` and the audition index report about one piece of audio."""
    import numpy as np
    dur = len(x) / sr
    mask, hop = _speech_mask(x, sr)
    out = {"duration": round(dur, 3), "peak": round(float(np.abs(x).max()) if len(x) else 0.0, 4)}
    if not mask.any():
        return {**out, "silent": True}
    idx = np.flatnonzero(mask)
    first, last = int(idx[0]), int(idx[-1])
    head, span = first * hop / sr, (last + 1 - first) * hop / sr
    pauses, run = [], 0
    for v in mask[first:last + 1]:
        if v:
            if run * hop / sr >= pause_min:
                pauses.append(round(run * hop / sr, 2))
            run = 0
        else:
            run += 1
    voiced = float(mask[first:last + 1].sum() * hop / sr)
    sp = x[: len(mask) * hop].reshape(len(mask), hop)[mask]
    full, clip = np.abs(x) >= 0.999, 0
    if full.any():                                             # the longest run of samples at full scale
        d = np.diff(np.concatenate(([0], full.astype(np.int8), [0])))
        clip = int((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max())
    f0, spread = pitch(x, sr)
    out.update({"head": round(head, 3), "tail": round(max(0.0, dur - head - span), 3), "span": round(span, 3), "voiced": round(voiced, 3),
                "pauses": pauses, "rms_db": round(float(20 * np.log10(np.sqrt((sp.astype("float64") ** 2).mean()) + 1e-12)), 1),
                "clip_run": int(clip), "f0": f0, "f0_iqr": spread, "air_db": air_db(x, sr)})
    if n_words:
        out["words"] = n_words
        out["wps"] = round(n_words / span, 2) if span > 0 else None
        out["articulation"] = round(n_words / voiced, 2) if voiced > 0 else None
    return out


def gender_of(f0: float | None) -> str | None:
    """A label from measured pitch only: below the split reads as male, at or above it as female."""
    if not f0:
        return None
    return "male" if f0 < float(config()["genders"]["split_hz"]) else "female"


# ------------------------------------------------------------------ text
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number_words(tok: str) -> list[str]:
    """A digit token as spoken words (0-999, and years such as 2026), so "7 steps" matches "seven steps"."""
    if not tok.isdigit() or len(tok) > 4:
        return [tok]
    n = int(tok)

    def small(k: int) -> list[str]:
        if k < 20:
            return [_ONES[k]]
        if k < 100:
            return [_TENS[k // 10 - 2]] + ([_ONES[k % 10]] if k % 10 else [])
        return [_ONES[k // 100], "hundred"] + (small(k % 100) if k % 100 else [])
    if n < 1000:
        return small(n)
    if 1100 <= n <= 2099 and n % 100:
        return small(n // 100) + (["oh"] if n % 100 < 10 else []) + small(n % 100)
    return [tok]


def norm_words(text: str, aliases: dict | None = None) -> list[str]:
    """Lower-case words with punctuation removed; digits 0-20 and the tens become words; `aliases` maps a
    heard phrase to the written one (for names a transcriber spells its own way)."""
    t = str(text).lower().replace("’", "'").replace("%", " percent ")
    t = re.sub(r"'", "", t)
    t = re.sub(r"[^\w]+", " ", t, flags=re.UNICODE).replace("_", " ")
    for heard, written in (aliases or {}).items():
        t = re.sub(rf"\b{re.escape(str(heard).lower())}\b", str(written).lower(), t)
    return [x for w in t.split() for x in _number_words(w)]


def count_words(text: str) -> int:
    return len(norm_words(text))


def wer(ref: list[str], hyp: list[str]) -> float:
    """Word error rate: edit distance over the reference length."""
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref)


def text_match(written: str, heard: str, aliases: dict | None = None) -> dict:
    """Compare what was written with what a transcriber heard.
    exact  the words are the same, or differ only in where the spaces fall ("Gen AI" for "GenAI")
    ok     every difference looks like a spelling variant of the same word ("Lama Index" for "LlamaIndex"):
           no retry, but the line is flagged so a person listens
    else   a word is missing, added or different: the take is regenerated"""
    a, b = norm_words(written), norm_words(heard, aliases)
    sim = difflib.SequenceMatcher(None, "".join(a), "".join(b), autojunk=False).ratio() if a or b else 1.0
    diffs, ok = [], True
    if "".join(a) != "".join(b):
        vmin = float(config()["check"]["variant_similarity"])
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            wa, wb = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            if wa.replace(" ", "") == wb.replace(" ", ""):       # only the spacing differs
                continue
            diffs.append([wa, wb])
            if not wa or not wb or difflib.SequenceMatcher(None, wa.replace(" ", ""), wb.replace(" ", ""), autojunk=False).ratio() < vmin:
                ok = False
    return {"ok": ok, "exact": not diffs, "wer": round(wer(a, b), 3), "similarity": round(sim, 3), "diffs": diffs, "heard": heard}


def split_sentences(text: str, min_words: int = 3) -> list[tuple[int, int]]:
    """(start, end) spans of the sentences in `text`. A fragment under `min_words` joins its neighbour,
    because very short inputs make the engines rush or hallucinate."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?…]+[\"')\]]*(?:\s+|$)", text):
        if text[m.end():m.end() + 1].islower():                 # "engineer... it's easy": the sentence carries on
            continue
        if text[start:m.end()].strip():
            spans.append([start, m.end()])
        start = m.end()
    if text[start:].strip():
        spans.append([start, len(text)])
    out: list[list[int]] = []
    carry = None
    for a, b in spans:
        if carry is not None:
            a, carry = carry, None
        if count_words(text[a:b]) < min_words:
            carry = a
            continue
        out.append([a, b])
    if carry is not None:
        if out:
            out[-1][1] = len(text)
        else:
            out.append([carry, len(text)])
    res = []
    for a, b in out:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        res.append((a, b))
    return res


# ------------------------------------------------------------------ engine environments
def tts_home() -> Path:
    return Path(os.environ.get("FISH_TTS_HOME") or SKILL / ".tts")


def env_python(env_dir: Path) -> Path:
    return Path(env_dir) / ("Scripts/python.exe" if IS_WIN else "bin/python")


def engine_python(engine: str) -> Path | None:
    """The interpreter of an engine's environment: FISH_<ENGINE>_PYTHON, else <skill>/.tts/<engine>."""
    over = os.environ.get(f"FISH_{engine.upper()}_PYTHON")
    p = Path(over) if over else env_python(tts_home() / engine)
    return p if p.exists() else None


def worker_path() -> Path:
    return Path(os.environ.get("FISH_VOICELAB_WORKER") or SCRIPTS / "voicelab_worker.py")


def run_worker(py: Path | str, job: dict, logfile: Path | None = None) -> dict:
    """Run one job in an engine environment. No shell; the job goes in on stdin, one JSON line comes back."""
    r = subprocess.run([str(py), "-I", str(worker_path())], input=json.dumps(job), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if logfile and r.stderr:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with logfile.open("a", encoding="utf-8") as fh:
            fh.write(r.stderr[-20000:])
    res = last_json_line(r.stdout)
    if not res or not res.get("ok"):
        detail = (res or {}).get("error") or (r.stderr or "").strip()[-600:] or f"exit code {r.returncode}"
        if "espeak-ng-data" in (r.stderr or ""):        # espeak-ng keeps its data path in a 230-character buffer
            detail += " (the engine environment's path is probably too long for espeak-ng: use a shorter FISH_TTS_HOME)"
        raise FishError(f"voice engine job '{job.get('op')}' failed: {detail}")
    return res


def probe(py: Path | str) -> dict:
    key = str(py)
    if key not in _PROBE:
        try:
            _PROBE[key] = run_worker(py, {"op": "probe"})
        except (FishError, OSError) as e:
            _PROBE[key] = {"modules": {}, "error": str(e)[:200]}
    return _PROBE[key]


def engine_ready(engine: str) -> bool:
    py = engine_python(engine)
    return bool(py and probe(py).get("modules", {}).get(engine))


def whisper_python(prefer: str | None = None) -> Path | None:
    """An interpreter that has faster-whisper: FISH_WHISPER_PYTHON, the engine's own environment, another
    engine's, or this one. None when there is none (word timings are then estimated and takes are not verified)."""
    over = os.environ.get("FISH_WHISPER_PYTHON")
    cands = [Path(over)] if over else []
    cands += [p for p in (engine_python(e) for e in ([prefer] if prefer else []) + [e for e in ENGINES if e != prefer]) if p]
    cands.append(Path(sys.executable))
    for p in cands:
        if p.exists() and probe(p).get("modules", {}).get("faster_whisper"):
            return p
    return None


def engines_status() -> dict:
    out = {}
    for e in ENGINES:
        py = engine_python(e)
        mods = probe(py).get("modules", {}) if py else {}
        out[e] = {"installed": bool(mods.get(e)), "python": str(py) if py else None, "transcription": bool(mods.get("faster_whisper")),
                  "watermark": bool(mods.get("perth")) if e == "chatterbox" else None}
    out["transcription"] = bool(whisper_python())
    return out


def _find_python(version: str) -> list[str]:
    if sys.version_info[:2] == tuple(int(v) for v in version.split(".")):
        return [sys.executable]
    exe = shutil.which(f"python{version}")
    if exe:
        return [exe]
    if IS_WIN and shutil.which("py"):
        return ["py", f"-{version}"]
    raise FishError(f"Python {version} is needed for this engine and was not found. Install uv (https://docs.astral.sh/uv/), "
                    f"which fetches it automatically, or install Python {version}.")


def setup_commands(engine: str, home: Path | None = None, gpu: bool = False) -> tuple[Path, list[list[str]]]:
    """The exact commands `voice setup` runs for one engine (also printed by --dry-run)."""
    spec = config()["engines"][engine]
    dest = Path(home or tts_home()) / engine
    py = env_python(dest)
    uv = shutil.which("uv")
    pkgs = list(spec["packages"]) + list(spec.get("torch") or [])
    cpu = [] if gpu or sys.platform == "darwin" else ["--extra-index-url", "https://download.pytorch.org/whl/cpu"]
    cmds: list[list[str]] = []
    if not py.exists():
        cmds.append([uv, "venv", "--python", str(spec["python"]), str(dest)] if uv else [*_find_python(str(spec["python"])), "-m", "venv", str(dest)])
    if uv:
        strategy = ["--index-strategy", "unsafe-best-match"] if cpu else []   # torch +cpu builds live on the extra index
        cmds.append([uv, "pip", "install", "--python", str(py), *strategy, *cpu, *pkgs])
    else:
        cmds.append([str(py), "-m", "pip", "install", *cpu, *pkgs])
    return dest, cmds


def setup(engine: str, home: Path | None = None, gpu: bool = False, dry_run: bool = False) -> dict:
    """Create or update an engine environment. Safe to repeat: a finished environment is left alone."""
    if engine not in ENGINES:
        raise FishError(f"unknown engine '{engine}': one of {', '.join(ENGINES)}")
    spec = config()["engines"][engine]
    dest, cmds = setup_commands(engine, home, gpu)
    marker, want = dest / "fish-engine.json", {"engine": engine, "packages": list(spec["packages"]) + list(spec.get("torch") or []), "gpu": bool(gpu)}
    py = env_python(dest)
    if py.exists() and marker.exists() and load_json(marker, default={}) == want and probe(py).get("modules", {}).get(engine):
        log(f"{engine}: already set up at {dest}")
        return {"engine": engine, "path": str(dest), "changed": False}
    if dry_run:
        for c in cmds:
            log("  " + " ".join(c))
        return {"engine": engine, "path": str(dest), "changed": False, "dry_run": [" ".join(c) for c in cmds]}
    log(f"{engine}: setting up {dest} (isolated from the skill's own environment; this downloads several hundred MB)")
    for c in cmds:
        r = subprocess.run(c)
        if r.returncode != 0:
            raise FishError(f"setup failed ({r.returncode}): {' '.join(c[:6])} ...")
    if len(str(dest)) > 150:
        warn(f"{dest} is a long path: espeak-ng (Kokoro) fails on paths past about 230 characters. Set FISH_TTS_HOME to a shorter one if voices fail.")
    _PROBE.pop(str(py), None)
    mods = probe(py).get("modules", {})
    if not mods.get(engine):
        raise FishError(f"{engine} was installed but cannot be imported in {dest}")
    save_json(marker, want)
    log(f"{engine}: ready. Transcription: {'yes' if mods.get('faster_whisper') else 'no'}. The model weights download on first use.")
    return {"engine": engine, "path": str(dest), "changed": True}


# ------------------------------------------------------------------ settings
def _lang_letter(language: str | None) -> str:
    return "b" if str(language or "").lower().startswith("en-gb") else "a"


def _pace(pace) -> dict:
    """A named pace, or a number of words per second interpolated between the named ones."""
    P = config()["paces"]
    if isinstance(pace, str) and pace in P:
        return {"name": pace, **P[pace]}
    try:
        w = float(pace)
    except (TypeError, ValueError):
        raise FishError(f"unknown pace '{pace}': one of {', '.join(P)} or a number of words per second")
    if not 1.5 <= w <= 4.5:
        raise FishError(f"pace {w} words per second is outside the usable range 1.5-4.5")
    pts = sorted(P.values(), key=lambda p: p["wps"])
    lo = max([p for p in pts if p["wps"] <= w] or pts[:1], key=lambda p: p["wps"])
    hi = min([p for p in pts if p["wps"] >= w] or pts[-1:], key=lambda p: p["wps"])
    f = 0.0 if hi["wps"] == lo["wps"] else (w - lo["wps"]) / (hi["wps"] - lo["wps"])
    return {"name": f"{w:g} wps", "wps": w, **{k: round(lo[k] + (hi[k] - lo[k]) * f, 3) for k in ("cfg_weight", "speed", "pause_scale")}}


def studio_settings(voice_cfg: dict, engine: str, over: dict | None = None) -> dict:
    """Resolve brief.voice.studio (plus one line's overrides) into the numbers an engine needs."""
    c = config()
    st = {**c["defaults"], **(voice_cfg.get("studio") or {}), **(over or {})}
    gender, style = st.get("gender"), st.get("style")
    if gender not in ("male", "female"):
        raise FishError(f"voice.studio.gender must be male or female, not '{gender}'")
    if style not in c["styles"]:
        raise FishError(f"unknown voice style '{style}': one of {', '.join(c['styles'])}")
    sty, pace = c["styles"][style], _pace(st.get("pace"))
    lo, hi = c["pace_control"]["cfg_range"]
    S = {"engine": engine, "gender": gender, "style": style, "pace": pace["name"], "target_wps": pace["wps"], "loop": "cfg_fixed" not in sty, "seed": int(st.get("seed", 11)),
         "pause": float(st.get("pause", sty["pause"])), "pause_scale": pace["pause_scale"], "post": st.get("post", sty.get("post") or ""),
         "air": sty.get("air"), "loudnorm": sty.get("loudnorm"), "edges": sty.get("edges"), "pause_range": sty.get("pause_range"), "ex_range": sty.get("exaggeration_range"), "language": voice_cfg.get("language") or "en-US", "aliases": st.get("aliases") or {},
         "mood": st.get("mood"), "verify": st.get("verify", True)}
    if engine == "chatterbox":
        S.update({"exaggeration": float(st.get("exaggeration", sty["exaggeration"])),
                  "exaggeration_fixed": "exaggeration" in (over or {}),
                  "cfg_weight": float(st["cfg_weight"]) if "cfg_weight" in st else float(sty["cfg_fixed"]) if "cfg_fixed" in sty else round(min(hi, max(lo, float(pace["cfg_weight"] + sty.get("cfg_shift", 0)))), 3),
                  "temperature": float(st.get("temperature", sty.get("temperature", c["defaults"]["temperature"])))})
        ref = st.get("reference")
        if ref:
            S["ref"] = {"kind": "user", "path": str(ref), "consent": bool(st.get("reference_consent"))}
        elif gender != c["genders"]["builtin"]["chatterbox"]:
            S["ref"] = {"kind": "kokoro", "voice": st.get("kokoro_voice") or c["genders"][gender]["kokoro"][_lang_letter(S["language"])]}
        else:
            S["ref"] = None
    else:
        S.update({"voice": st.get("kokoro_voice") or c["genders"][gender]["kokoro"][_lang_letter(S["language"])],
                  "speed": float(st.get("speed", pace["speed"]))})
    return S


_HOSTED = ("elevenlabs", "eleven_", "eleven-", "edge-tts", "edgetts", "edge_tts", "azure-tts", "polly", "openai-tts", "playht", "cartesia")


def check_reference(path: Path, consent: bool) -> Path:
    """Guards for a cloning reference the user supplies. A real person's voice needs that person's consent, and a
    hosted provider's output must never be used: their terms do not grant it. The second guard can only catch
    the skill's own output folders and telling file names; it is a backstop, not proof."""
    p = Path(path)
    if not p.exists():
        raise FishError(f"reference clip not found: {p}")
    low = str(p.resolve()).lower().replace("\\", "/")
    if any(f"/build/voice/{d}/" in low for d in ("elevenlabs", "edge-tts")) or ("/build/auditions/" in low and "/build/auditions/studio/" not in low) \
            or any(h in p.name.lower() for h in _HOSTED):
        raise FishError(f"{p.name} looks like a hosted provider's output. Their terms do not allow using it to clone a voice. "
                        "Use your own recording, or let the studio make a reference with Kokoro (drop voice.studio.reference).")
    if not consent:
        raise FishError("a reference clip clones a voice. Set voice.studio.reference_consent: true (or pass --i-have-consent) only if it is "
                        "your own voice or the speaker agreed to this use.")
    return p


def resolve_reference(S: dict, workdir: Path, base: Path | None = None) -> tuple[str | None, str]:
    """(path of the reference clip or None, a label saying where the voice comes from)."""
    ref = S.get("ref")
    if S["engine"] != "chatterbox" or not ref:
        return None, f"kokoro preset {S['voice']}" if S["engine"] == "kokoro" else "chatterbox built-in voice"
    if ref["kind"] == "user":
        p = Path(ref["path"])
        p = check_reference(p if p.is_absolute() or not base else Path(base) / p, ref.get("consent", False))
        return str(p), f"user clip {p.name} (consent declared)"
    py = engine_python("kokoro")
    if not engine_ready("kokoro"):
        raise FishError(f"a {S['gender']} Chatterbox voice needs a reference clip. Run `fishvideo voice setup --engine kokoro` so the studio can "
                        "make one locally, or give your own with voice.studio.reference and reference_consent: true.")
    rc = config()["reference"]
    out = Path(workdir) / "refs" / f"kokoro-{ref['voice']}-{sha1({'t': rc['text'], 's': rc['speed']})}.wav"
    if not out.exists():
        run_worker(py, {"op": "tts", "engine": "kokoro", "items": [{"text": rc["text"], "voice": ref["voice"], "speed": rc["speed"], "seed": 0, "out": str(out)}]},
                   Path(workdir) / "worker.log")
    return str(out), f"reference made locally with Kokoro {ref['voice']}"


def plan_line(say: str, mood: str | None, S: dict) -> list[dict]:
    """One item per sentence: the text, its engine settings and the pause that follows it."""
    c = config()
    md = c["moods"].get(mood or S.get("mood") or "neutral")
    if md is None:
        warn(f"unknown mood '{mood}': one of {sorted(c['moods'])}")
        md = c["moods"]["neutral"]
    items = []
    for a, b in split_sentences(say):
        text = say[a:b]
        end = text.rstrip("\"')] ")
        kind = "exclaim" if end.endswith("!") else "question" if end.endswith("?") else "ellipsis" if ("..." in text or "…" in text) else None
        pause = S["pause"] * S["pause_scale"] * md["pause"] + (0.1 if kind == "ellipsis" else 0.0)
        if S.get("pause_range"):                                   # the soft preset: short sentences breathe less, questions more
            lo_p, hi_p = S["pause_range"]
            pause = lo_p if count_words(text) < 6 else 0.5 if kind == "question" else S["pause"]
            pause = min(hi_p, max(lo_p, pause))
        it = {"text": text, "start": a, "seed": S["seed"], "tries": 0, "history": [], "pause": round(pause, 3)}
        if S["engine"] == "chatterbox":
            ex = S["exaggeration"] if S.get("exaggeration_fixed") else S["exaggeration"] + md["exaggeration"] + (c["punctuation"].get(kind, 0) if kind else 0)
            lo_e, hi_e = S.get("ex_range") or (0.25, 0.95)
            it.update({"exaggeration": round(min(hi_e, max(lo_e, ex)), 2), "cfg_weight": S["cfg_weight"], "temperature": S["temperature"]})
        else:
            it.update({"voice": S["voice"], "speed": round(S["speed"], 3)})
        items.append(it)
    return items


# ------------------------------------------------------------------ takes
_TAKE_KEYS = ("text", "seed", "exaggeration", "cfg_weight", "temperature", "voice", "speed")


def _take_paths(it: dict, S: dict, takes: Path) -> tuple[Path, Path]:
    key = sha1({"engine": S["engine"], "ref": S.get("ref_id"), **{k: it[k] for k in _TAKE_KEYS if k in it}}, 14)
    return takes / f"{key}.wav", takes / f"{key}.json"


def _make_takes(pending: list[tuple[dict, dict]], engine: str, takes: Path, wpy: Path | None, language: str) -> None:
    """Generate the missing takes in ONE engine job (the model loads once), then transcribe them in one more."""
    py = engine_python(engine)
    if not engine_ready(engine):
        raise FishError(f"{engine} is not set up, and nothing falls back silently. " + (
            "Chatterbox is the recommended soft voice. Install it with ONE command: `fishvideo voice setup --engine chatterbox` (about 2 GB, several minutes, CPU is enough). "
            "Or choose another voice on purpose (`--provider edge-tts|elevenlabs|kokoro` or voice.provider in brief.yaml) and tell the user what changes: less natural pacing and no per-sentence emotion."
            if engine == "chatterbox" else f"run `fishvideo voice setup --engine {engine}`"))
    takes.mkdir(parents=True, exist_ok=True)
    items = []
    for it, S in pending:
        wav, _ = _take_paths(it, S, takes)
        items.append({**{k: it[k] for k in _TAKE_KEYS if k in it}, "out": str(wav), **({"ref": S["ref_path"]} if S.get("ref_path") else {})})
    words = sum(count_words(i["text"]) for i in items)
    log(f"  {engine}: {len(items)} takes, {words} words" + (" (several minutes on a CPU)" if engine == "chatterbox" and words > 60 else ""))
    res = run_worker(py, {"op": "tts", "engine": engine, "items": items}, takes.parent / "worker.log")
    heard = {}
    if wpy:
        lang = str(language or "en").split("-")[0].lower()
        model = config()["whisper_model"] if lang == "en" else config()["whisper_model"].split(".")[0]
        heard = run_worker(wpy, {"op": "transcribe", "files": [i["out"] for i in items], "model": model, "language": lang}, takes.parent / "worker.log")["words"]
    for (it, S), job, r in zip(pending, items, res["items"]):
        _, meta = _take_paths(it, S, takes)
        save_json(meta, {"params": {k: job[k] for k in job if k not in ("out", "ref")}, "duration": r["duration"], "sr": r["sr"],
                         "seconds": r.get("seconds"), "words": heard.get(job["out"]) if wpy else None})


def _trim(x, sr: int, pad: float = 0.03) -> tuple[int, int]:
    """Sample bounds of the speech in a take, with a small pad either side."""
    mask, hop = _speech_mask(x, sr)
    if not mask.any():
        return 0, len(x)
    import numpy as np
    idx = np.flatnonzero(mask)
    return max(0, int(idx[0] * hop - pad * sr)), min(len(x), int((idx[-1] + 1) * hop + pad * sr))


def solve_pace(n_words: int, durs: list[float], pauses: list[float], target: float | None, engine: str, setting: float) -> dict:
    """The closed loop's arithmetic. Given the speech length of each sentence take and the planned pauses, return the
    pauses and time-stretch that land on `target` words per second, or the engine setting to regenerate with.
    Order: move the pauses, then stretch a little, then ask for a regeneration."""
    P = config()["pace_control"]
    D, s, p = sum(durs), 1.0, list(pauses)
    wps = lambda: n_words / max(1e-6, D / s + sum(p))                           # noqa: E731
    res = {"target": target, "stretch": 1.0, "pauses": p, "wps": round(wps(), 3), "converged": None, "regen": None}
    if not target or n_words < int(P["min_words"]):
        return res
    tol, (lo, hi), ms = float(P["tolerance"]), P["pause_range"], float(P["max_stretch"])
    T = n_words / target
    if p and sum(p) > 0 and abs(wps() - target) > tol / 2:
        k = (T - D) / sum(p)
        p = [round(min(hi, max(lo, q * k)), 3) for q in p]
    if abs(wps() - target) > tol / 2:
        rest = T - sum(p)
        s = round(min(1 + ms, max(1 - ms, D / rest if rest > 0 else 1 + ms)), 4)
    w = wps()
    res.update({"stretch": s, "pauses": p, "wps": round(w, 3), "converged": bool(abs(w - target) <= tol)})
    if not res["converged"]:
        need = T - sum(pauses)                                # speech time that would hit the target with the planned pauses
        art_now, art_need = n_words / D, n_words / max(need, 0.25 * T)
        if engine == "chatterbox":
            a, b = P["cfg_range"]
            new = round(min(b, max(a, setting + (art_need - art_now) * float(P["cfg_per_wps"]))), 3)
            res["regen"] = {"cfg_weight": new} if abs(new - setting) >= 0.02 else None
        else:
            a, b = P["speed_range"]
            new = round(min(b, max(a, setting * art_need / art_now)), 3)
            res["regen"] = {"speed": new} if abs(new - setting) >= 0.02 else None
    return res


def _script_words(text: str, heard: list[dict] | None, t0: float, t1: float) -> tuple[list[dict], bool]:
    """Times, in the take, for the WRITTEN words of a sentence: aligned to the transcript when there is one,
    otherwise spread by length over the speech (t0 to t1). Returns (words, estimated)."""
    if heard:
        from voiceover import align
        ws = align([{"id": "s", "say": text}], heard)[0]["words"]
        if ws:
            return ws, False
    toks = [(m.group(0), m.start()) for m in re.finditer(r"\S+", text) if any(ch.isalnum() for ch in m.group(0))]
    total = sum(len(t) + 1 for t, _ in toks) or 1
    t, out = t0, []
    for tok, ch in toks:
        d = (t1 - t0) * (len(tok) + 1) / total
        out.append({"text": tok, "start": t, "end": t + d * 0.9, "char": ch})
        t += d
    return out, True


def _assemble(st: dict, out_wav: Path) -> dict:
    """Join a line's takes with its pauses, apply the stretch and the post chain, level it, and time every word."""
    import numpy as np
    c, S, sol = config(), st["S"], st["sol"]
    s = float(sol["stretch"])
    ed = S.get("edges") or c["edges"]
    head, tail = float(ed["head"]), float(ed["tail"])
    parts, words, sr, estimated = [], [], None, False
    t = head * s                                                # everything is laid out before the stretch
    for k, it in enumerate(st["items"]):
        x, sr = read_wav(it["wav"])
        a, b = _trim(x, sr)
        seg = x[a:b].copy()
        f = min(int(0.005 * sr), len(seg) // 4)
        if f:
            seg[:f] *= np.linspace(0, 1, f)
            seg[-f:] *= np.linspace(1, 0, f)
        sw, est = _script_words(it["text"], it["meta"].get("words"), a / sr, b / sr)
        estimated |= est
        for w in sw:
            w0 = min(max(w["start"] - a / sr, 0.0), len(seg) / sr)
            w1 = min(max(w["end"] - a / sr, w0), len(seg) / sr)
            words.append({"text": w["text"], "start": round((t + w0) / s, 3), "end": round((t + w1) / s, 3), "char": it["start"] + w["char"]})
        parts.append(seg)
        t += len(seg) / sr
        if k < len(st["items"]) - 1:
            gap = sol["pauses"][k] * s
            parts.append(np.zeros(int(gap * sr), dtype="float32"))
            t += gap
    x = np.concatenate([np.zeros(int(head * s * sr), dtype="float32")] + parts + [np.zeros(int(tail * s * sr), dtype="float32")])
    chain = ([f"atempo={s}"] if abs(s - 1) > 0.004 else []) + [f"aresample={SR_OUT}"] + ([S["post"]] if S.get("post") else []) + ([S["loudnorm"]] if S.get("loudnorm") else [])
    with tempfile.TemporaryDirectory() as td:
        raw, cooked = Path(td) / "raw.wav", Path(td) / "post.wav"
        write_wav(raw, x, sr)
        r = subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(raw), "-af", ",".join(chain), "-ac", "1", "-ar", str(SR_OUT), "-c:a", "pcm_f32le", str(cooked)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise FishError(f"post chain failed: {r.stderr[-400:]}")
        y, _ = read_wav(cooked)
    m = measure(y, SR_OUT)
    if not m.get("silent") and not S.get("loudnorm"):          # one static gain per line (the soft preset is levelled by loudnorm instead): no pumping, same level on every line
        gain = 10 ** ((float(c["level"]["speech_rms_db"]) - m["rms_db"]) / 20)
        y = y * min(gain, float(c["level"]["peak_max"]) / max(m["peak"], 1e-6))
    write_wav(out_wav, y, SR_OUT)
    n_words = sum(count_words(it["text"]) for it in st["items"])
    m = measure(y, SR_OUT, n_words)
    target = sol.get("target") if sol.get("converged") is not None else None
    return {"words": words, "duration": m["duration"], "estimated_timing": estimated,
            "studio": {"engine": S["engine"], "gender": S["gender"], "style": S["style"], "target_wps": target,
                       "wps": m.get("wps"), "converged": (abs(m["wps"] - target) <= float(c["pace_control"]["tolerance"])) if target and m.get("wps") else None,
                       "articulation": m.get("articulation"), "pauses": len(m.get("pauses") or []), "f0": m.get("f0"), "reads_as": gender_of(m.get("f0")),
                       "air_db": m.get("air_db"), "rms_db": m.get("rms_db"), "stretch": s, "rounds": st["rounds"],
                       "sentences": [{"text": it["text"], **{k: it[k] for k in ("exaggeration", "cfg_weight", "speed", "seed") if k in it},
                                      "similarity": (it.get("match") or {}).get("similarity"), "heard": (it.get("match") or {}).get("heard"),
                                      "ok": (it.get("match") or {}).get("ok")} for it in st["items"]]}}


def synth_lines(lines: list[dict], voice_cfg: dict, engine: str, outdir: Path, force: set | bool = False, base: Path | None = None) -> dict:
    """Voice lines [{id, say, mood?, over?}] and return {id: clip}. Line results are cached by text and settings.
    `force` is True for every line or a set of line ids."""
    c = config()
    outdir = Path(outdir)
    takes = outdir / "takes"
    outdir.mkdir(parents=True, exist_ok=True)
    wpy = whisper_python(engine)
    if not wpy:
        warn("no environment has faster-whisper: word timings are estimated and takes are NOT checked against the script")
    clips, state, refs = {}, {}, {}
    for ln in lines:
        S = studio_settings(voice_cfg, engine, ln.get("over"))
        rk = json.dumps(S.get("ref"), sort_keys=True)
        if rk not in refs:
            refs[rk] = resolve_reference(S, outdir, base)
        S["ref_path"], S["voice_source"] = refs[rk]
        S["ref_id"] = sha1(Path(S["ref_path"]).read_bytes()) if S["ref_path"] else None
        h = sha1({"say": ln["say"], "mood": ln.get("mood"), "S": {k: v for k, v in S.items() if k not in ("ref_path", "aliases", "verify")}, "checked": bool(wpy)})
        wav, js = outdir / f"{ln['id']}-{h}.wav", outdir / f"{ln['id']}-{h}.json"
        forced = force is True or (isinstance(force, (set, list, tuple)) and ln["id"] in force)
        if js.exists() and wav.exists() and not forced:
            clips[ln["id"]] = load_json(js)
            continue
        state[ln["id"]] = {"ln": ln, "S": S, "items": plan_line(ln["say"], ln.get("mood"), S), "rounds": 0, "wav": wav, "json": js, "hash": h, "forced": forced}
    retries, max_rounds = int(c["check"]["retries"]), int(c["pace_control"]["max_rounds"])
    for st in state.values():
        if st["forced"]:
            for it in st["items"]:
                for f in _take_paths(it, st["S"], takes):
                    f.unlink(missing_ok=True)
    budget = (retries + 2) * (max_rounds + 1) + 1
    for step in range(budget):
        last = step == budget - 1                               # on the last pass nothing may change: settle with what exists
        pending = []
        for st in state.values():
            for it in st["items"]:
                it["wav"], it["metafile"] = _take_paths(it, st["S"], takes)
                if not (it["wav"].exists() and it["metafile"].exists()):
                    pending.append((it, st["S"]))
        if pending:
            _make_takes(pending, engine, takes, wpy, pending[0][1]["language"])
        again = False
        for st in state.values():
            S = st["S"]
            for it in st["items"]:
                it["meta"] = load_json(it["metafile"])
                heard = it["meta"].get("words")
                if heard is None or not S.get("verify", True):
                    it["match"] = None
                    continue
                it["match"] = text_match(it["text"], " ".join(w["text"] for w in heard), S.get("aliases"))
                if not any(h[1] == it["seed"] for h in it["history"]):
                    it["history"].append((it["match"]["similarity"], it["seed"]))
                if it["match"]["ok"] or last:
                    continue
                if it["tries"] < retries:                       # wrong words: the same sentence again, new seed
                    it["tries"] += 1
                    it["seed"] = S["seed"] + it["tries"]
                    again = True
                elif max(it["history"])[1] != it["seed"]:       # out of retries: keep the closest take (it stays flagged)
                    it["seed"] = max(it["history"])[1]
                    again = True
        if again:
            continue
        for st in state.values():
            S, durs = st["S"], []
            for it in st["items"]:
                x, sr = read_wav(it["wav"])
                a, b = _trim(x, sr)
                durs.append((b - a) / sr)
            key = "cfg_weight" if engine == "chatterbox" else "speed"
            st["sol"] = solve_pace(sum(count_words(it["text"]) for it in st["items"]), durs, [it["pause"] for it in st["items"][:-1]],
                                   S["target_wps"] if S.get("loop", True) else None, engine, st["items"][0][key])
            if st["sol"]["regen"] and st["rounds"] < max_rounds and not last:
                st["rounds"] += 1
                for it in st["items"]:
                    it.update(st["sol"]["regen"])
                    it.update({"tries": 0, "history": [], "seed": S["seed"]})
                again = True
        if not again:
            break
    for lid, st in state.items():
        rec = _assemble(st, st["wav"])
        w = rec["words"]
        if not w:
            raise FishError(f"{lid}: no words could be timed")
        clip = {"say": st["ln"]["say"], "provider": engine, "hash": st["hash"], "wav": str(st["wav"]), "duration": round(rec["duration"], 3),
                "speech_start": round(w[0]["start"], 3), "speech_end": round(w[-1]["end"], 3), "words": w, "estimated_timing": rec["estimated_timing"],
                "studio": {**rec["studio"], "voice_source": st["S"]["voice_source"]}}
        save_json(st["json"], clip)
        clips[lid] = clip
    return {ln["id"]: clips[ln["id"]] for ln in lines}


# ------------------------------------------------------------------ the project provider
def handles(voice_cfg: dict, provider: str) -> bool:
    """Chatterbox always runs here. Kokoro runs here when the brief has voice.studio, or when Kokoro is not
    importable in the skill's own environment but its isolated environment is installed."""
    if provider == "chatterbox":
        return True
    if provider != "kokoro":
        return False
    if voice_cfg.get("studio"):
        return True
    import importlib.util
    return importlib.util.find_spec("kokoro") is None and engine_ready("kokoro")


# a line's `tag:` in the storyboard shapes its emotion inside the preset's approved range (soft: 0.32-0.55): hooks and reveals lift, setup stays low
TAG_MOODS = {"hook": "urgent", "reveal": "excited", "punchline": "triumphant", "setup": "serious", "beat": "neutral"}


def _project_lines(project: Path, cfg: dict) -> list[dict]:
    from storyboard import scene_lines
    sb = load_yaml(project / "storyboard.yaml")
    pron = (cfg["brief"].get("voice") or {}).get("pronunciations") or {}
    over = ((cfg["voice"].get("studio") or {}).get("lines")) or {}
    out = []
    for s in sb["scenes"]:
        for ln in scene_lines(s, pron):
            o = dict(over.get(ln["id"]) or {})
            out.append({"id": ln["id"], "say": ln["say"], "display": ln.get("display", ln["say"]), "mood": o.pop("mood", None) or TAG_MOODS.get(ln.get("tag") or "") or s.get("mood"), "over": o or None})
    return out


def synthesize(project: Path, cfg: dict, engine: str, force: set | bool = False) -> dict:
    """Voice every narration line with a local engine and write build/voice/clips.json (same shape as voice.py)."""
    project = Path(project)
    lines = _project_lines(project, cfg)
    out = project / "build" / "voice"
    clips = synth_lines(lines, cfg["voice"], engine, out / engine, force, base=project)
    for ln in lines:
        cl = clips[ln["id"]]
        cl["wav"] = str(Path(cl["wav"]).resolve().relative_to(project.resolve())).replace("\\", "/")
        st = cl["studio"]
        flag = "" if all(s.get("ok") is not False for s in st["sentences"]) else "  CHECK THE WORDS (a homophone? fishvideo voice words <dir> --add heard=written)"
        log(f"  {ln['id']:<18} {cl['speech_end']:5.2f}s  {st['wps'] or 0:.2f} wps  {ln['display'][:56]}{flag}")
    S = studio_settings(cfg["voice"], engine)
    first = next(iter(clips.values()))["studio"] if clips else {}
    res = {"provider": engine, "post": "anull",                 # the style's chain is already applied per line
           "voice": {"provider": engine, "gender": S["gender"], "style": S["style"], "pace": S["pace"], "target_wps": S["target_wps"],
                     "voice_source": first.get("voice_source"), "watermark": engine == "chatterbox", "language": S["language"]},
           "studio": {"engine": engine, "transcript_checked": bool(whisper_python(engine))}, "clips": clips}
    save_json(out / "clips.json", res)
    log(f"voice: {len(clips)} lines via {engine} ({S['gender']}, {S['style']}, {S['pace']}) -> {out / 'clips.json'}")
    return res


# ------------------------------------------------------------------ voice check
def check_project(project: Path, transcript: bool = True, quality: bool = False) -> dict:
    """Measure every voiced line and compare it with the script. Works on any provider's clips."""
    project = Path(project)
    data = load_json(project / "build" / "voice" / "clips.json", default={"clips": {}})
    clips = data.get("clips") or {}
    c = config()["check"]
    if not clips:
        return {"lines": {}, "rows": [], "provider": data.get("provider")}
    cfg = project_config(project)
    studio = bool(data.get("studio"))
    aliases = ((cfg["voice"].get("studio") or {}).get("aliases")) or {}
    files = {lid: project / cl["wav"] for lid, cl in clips.items()}
    wpy = whisper_python(data.get("provider") if data.get("provider") in ENGINES else None) if transcript else None
    heard, scores = {}, {}
    if wpy:
        lang = str((cfg["voice"].get("language") or "en")).split("-")[0].lower()
        model = config()["whisper_model"] if lang == "en" else config()["whisper_model"].split(".")[0]
        heard = run_worker(wpy, {"op": "transcribe", "files": [str(f) for f in files.values()], "model": model, "language": lang})["words"]
    if quality:
        py = engine_python("chatterbox")
        if py and probe(py).get("modules", {}).get("torchaudio"):
            scores = run_worker(py, {"op": "quality", "files": [str(f) for f in files.values()]})["quality"]
        else:
            warn("the signal-quality estimate needs torchaudio, which the chatterbox environment provides")
    lines, f0s, rmss = {}, [], []
    for lid, cl in clips.items():
        x, sr = load_audio(files[lid])
        n = count_words(cl["say"])
        m = measure(x, sr, n, float(c["pause_min"]))
        st, issues = cl.get("studio") or {}, []
        if wpy:
            tm = text_match(cl["say"], " ".join(w["text"] for w in heard.get(str(files[lid]), [])), aliases)
            m["match"] = tm
            d = "; ".join(f"wrote '{a}', heard '{b}'" for a, b in tm["diffs"][:3])
            if not tm["ok"]:
                issues.append(("FAIL", f"words differ: {d}"))
            elif not tm["exact"]:
                issues.append(("WARN", f"possible wrong word, listen: {d}"))
        if m.get("silent"):
            issues.append(("FAIL", "the file is silent"))
            lines[lid] = {"measure": m, "issues": issues}
            continue
        lo, hi = c["seconds_per_word"]
        if n and m["span"] / n < lo:
            issues.append(("FAIL", f"too short for {n} words ({m['span']:.1f}s): speech was cut off"))
        if n and m["span"] / n > hi:
            issues.append(("FAIL", f"too long for {n} words ({m['span']:.1f}s): the engine ran on"))
        target = st.get("target_wps")
        tol = float(config()["pace_control"]["tolerance"])
        if target and m.get("wps") and abs(m["wps"] - target) > tol:
            issues.append(("WARN", f"pace {m['wps']} wps, target {target}"))
        elif not target and m.get("wps") and n >= 6 and not c["pace_band"][0] <= m["wps"] <= c["pace_band"][1]:
            issues.append(("WARN", f"pace {m['wps']} wps is outside {c['pace_band'][0]}-{c['pace_band'][1]}"))
        want_pauses = len(split_sentences(cl["say"])) - 1
        if studio and len(m["pauses"]) < want_pauses:
            issues.append(("WARN", f"{len(m['pauses'])} pauses for {want_pauses + 1} sentences"))
        if m["clip_run"] >= int(c["clip_run"]):
            issues.append(("FAIL", f"clipping: {m['clip_run']} samples at full scale in a row"))
        if max(m["head"], m["tail"]) > float(c["edge_silence_max"]):
            issues.append(("WARN", f"silence at the edges: {m['head']:.2f}s before, {m['tail']:.2f}s after"))
        air = (config()["styles"].get(st.get("style")) or {}).get("air")
        if air and m.get("air_db") is not None and not air[0] <= m["air_db"] <= air[1]:
            issues.append(("WARN", f"brightness {m['air_db']} dB is outside the {st['style']} band {air[0]} to {air[1]}" + (" (may sound hissy)" if m["air_db"] > air[1] else "")))
        if st.get("gender") and gender_of(m.get("f0")) and gender_of(m["f0"]) != st["gender"]:
            issues.append(("WARN", f"median pitch {m['f0']} Hz reads as {gender_of(m['f0'])}, {st['gender']} was asked for"))
        if scores.get(str(files[lid])):
            m["quality"] = scores[str(files[lid])]
        if m.get("f0"):
            f0s.append(m["f0"])
        rmss.append(m["rms_db"])
        lines[lid] = {"measure": m, "issues": issues}
    if len(f0s) >= 3:
        import numpy as np
        med = float(np.median(f0s))
        for lid, ln in lines.items():
            f0 = ln["measure"].get("f0")
            if f0 and abs(f0 - med) / med > float(c["drift_fail"]):
                ln["issues"].append(("FAIL", f"voice drift: median pitch {f0} Hz against {med:.0f} Hz for the narration"))
            elif f0 and abs(f0 - med) / med > float(c["drift_warn"]):
                ln["issues"].append(("WARN", f"pitch {f0} Hz is {abs(f0 - med) / med:.0%} from the narration's {med:.0f} Hz"))
    if len(rmss) >= 3:
        import numpy as np
        med = float(np.median(rmss))
        for lid, ln in lines.items():
            r = ln["measure"].get("rms_db")
            if r is not None and abs(r - med) > float(c["loudness_spread_db"]):
                ln["issues"].append(("WARN", f"level {r} dB against {med:.1f} dB for the narration"))

    def row(name: str, words: tuple[str, ...], ok: str) -> dict:
        hit = [(lid, lv, msg) for lid, ln in lines.items() for lv, msg in ln["issues"] if any(w in msg for w in words)]
        status = "FAIL" if any(lv == "FAIL" for _, lv, _ in hit) else "WARN" if hit else "PASS"
        return {"check": name, "status": status, "detail": ok if not hit else f"{len(hit)} lines: " + "; ".join(f"{lid}: {msg}" for lid, _, msg in hit[:3])}
    rows = [row("voice words", ("words differ", "wrong word"), f"{len(lines)} lines match the script") if wpy else
            {"check": "voice words", "status": "WARN" if studio else "PASS", "detail": "not checked: no environment has faster-whisper (fishvideo voice setup)"},
            row("voice pace", ("pace", "pauses for"), "every line is inside its pace band"),
            row("voice signal", ("silent", "too short", "too long", "clipping", "silence at the edges", "level"), "no clipping, cut-offs or level jumps"),
            row("voice character", ("drift", "pitch", "brightness"), "pitch and brightness are consistent")]
    rep = {"provider": data.get("provider"), "transcript_checked": bool(wpy), "lines": lines, "rows": rows}
    save_json(project / "build" / "voice" / "check.json", rep)
    return rep


def qa_rows(project: Path) -> list[dict]:
    """Rows for `fishvideo qa`. Only for narration made by the studio (or when brief.voice.check is true), so
    existing projects keep their QA result. Never raises: a broken check must not break QA."""
    try:
        data = load_json(Path(project) / "build" / "voice" / "clips.json", default={})
        brief_voice = (load_yaml(Path(project) / "brief.yaml").get("voice") or {})
        if not data.get("clips") or not (data.get("studio") or brief_voice.get("check")):
            return []
        return check_project(Path(project))["rows"]
    except Exception as e:  # noqa: BLE001
        return [{"check": "voice check", "status": "WARN", "detail": f"could not run: {str(e)[:160]}"}]


def fix_lines(project: Path, rep: dict) -> list[str]:
    """Regenerate the lines whose words are wrong, with a new seed each (studio engines only)."""
    bad = [lid for lid, ln in rep["lines"].items() if any("words differ" in m or "wrong word" in m for _, m in ln["issues"])]
    if not bad or rep.get("provider") not in ENGINES:
        return []
    brief = load_yaml(project / "brief.yaml")
    lines = brief.setdefault("voice", {}).setdefault("studio", {}).setdefault("lines", {})
    base = int((brief["voice"]["studio"].get("seed")) or config()["defaults"]["seed"])
    for lid in bad:
        cur = lines.setdefault(lid, {})
        cur["seed"] = int(cur.get("seed", base)) + 101
    save_yaml(project / "brief.yaml", brief)
    synthesize(project, project_config(project), rep["provider"], set(bad))
    return bad


# ------------------------------------------------------------------ commands
def say(text: str, out: Path, engine: str, studio: dict, language: str = "en-US", work: Path | None = None) -> dict:
    """Voice one line outside a project. Returns its clip record (with measurements)."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(work) if work else Path(td)
        cl = synth_lines([{"id": "say", "say": text}], {"studio": studio, "language": language}, engine, d, force=True)["say"]
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cl["wav"], out)
    return cl


def audition_matrix(out: Path, engine: str, genders: list[str], styles: list[str], pace="natural", text: str | None = None, language: str = "en-US") -> list[dict]:
    """One short sample per gender and style, all in one engine job, plus an index of what was measured."""
    from interview import voices_cfg
    text = text or voices_cfg()["audition_line"]["en"]
    out = Path(out)
    lines = [{"id": f"{engine}-{g}-{s}", "say": text, "over": {"gender": g, "style": s, "pace": pace}} for g in genders for s in styles]
    clips = synth_lines(lines, {"language": language}, engine, out / ".work", force=True)
    rows = []
    for ln in lines:
        cl, st = clips[ln["id"]], clips[ln["id"]]["studio"]
        dst = out / f"{ln['id']}.wav"
        shutil.copyfile(cl["wav"], dst)
        rows.append({"file": dst.name, "gender": ln["over"]["gender"], "style": ln["over"]["style"], "wps": st["wps"], "target_wps": st["target_wps"],
                     "pauses": st["pauses"], "f0": st["f0"], "reads_as": st["reads_as"], "air_db": st["air_db"], "rms_db": st["rms_db"],
                     "words_ok": all(s.get("ok") is not False for s in st["sentences"]), "voice_source": st["voice_source"]})
    save_json(out / "index.json", {"engine": engine, "text": text, "samples": rows})
    md = [f"# Voice auditions ({engine})", "", f"Line: \"{text}\"", "",
          "Measured by the studio. Nobody has listened to these: play them and choose by ear.", "",
          "| file | asked for | pitch reads as | median pitch | pace (words/s) | pauses | brightness (dB) | words match |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['file']} | {r['gender']}, {r['style']} | {r['reads_as']} | {r['f0']} Hz | {r['wps']} (target {r['target_wps']}) | {r['pauses']} | {r['air_db']} | "
           f"{'yes' if r['words_ok'] else 'NO, listen'} |" for r in rows]
    (out / "index.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rows:
        log(f"  {r['file']:<34} {r['reads_as'] or '?':<6} {r['f0']} Hz  {r['wps']} wps  {r['pauses']} pauses  air {r['air_db']} dB")
    log(f"index: {out / 'index.md'}")
    return rows


def redo(project: Path, line_id: str, **over) -> dict:
    """Regenerate ONE line. The change is saved in brief.voice.studio.lines so a later full run keeps it."""
    project = ensure_project(project)
    cfg = project_config(project)
    engine = cfg["voice"].get("provider")
    if engine not in ENGINES:
        raise FishError(f"redo works with the local engines; this project's voice provider is '{engine}'")
    ids = [ln["id"] for ln in _project_lines(project, cfg)]
    if line_id not in ids:
        raise FishError(f"no narration line '{line_id}'. Lines: {', '.join(ids[:12])}{' ...' if len(ids) > 12 else ''}")
    brief = load_yaml(project / "brief.yaml")
    st = brief.setdefault("voice", {}).setdefault("studio", {})
    cur = st.setdefault("lines", {}).setdefault(line_id, {})
    over = {k: v for k, v in over.items() if v is not None}
    if not over:                                                # nothing asked: a new seed is the change
        over = {"seed": int(cur.get("seed", st.get("seed", config()["defaults"]["seed"]))) + 1}
    cur.update(over)
    save_yaml(project / "brief.yaml", brief)
    res = synthesize(project, project_config(project), engine, {line_id})
    return res["clips"][line_id]


def _table(rows: list[tuple]) -> None:
    for r in rows:
        log("  " + "  ".join(str(v) for v in r))


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo voice", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup"); p.add_argument("--engine", required=True, choices=[*ENGINES, "all"]); p.add_argument("--gpu", action="store_true")
    p.add_argument("--home", default=None); p.add_argument("--dry-run", action="store_true")
    sub.add_parser("engines")

    def voice_opts(p):
        p.add_argument("--engine", default=None, choices=ENGINES); p.add_argument("--gender", default=None, choices=["male", "female"])
        p.add_argument("--style", default=None); p.add_argument("--pace", default=None); p.add_argument("--seed", type=int, default=None)
    p = sub.add_parser("say"); p.add_argument("text"); p.add_argument("--out", required=True); voice_opts(p)
    p.add_argument("--reference", default=None); p.add_argument("--i-have-consent", action="store_true")
    p = sub.add_parser("audition"); p.add_argument("project", nargs="?"); p.add_argument("--matrix", action="store_true"); p.add_argument("--out", default=None)
    p.add_argument("--engine", default=None, choices=ENGINES); p.add_argument("--genders", default="male,female"); p.add_argument("--styles", default=None)
    p.add_argument("--pace", default="natural"); p.add_argument("--text", default=None)
    p = sub.add_parser("check"); p.add_argument("project"); p.add_argument("--fix", action="store_true"); p.add_argument("--no-transcript", action="store_true")
    p.add_argument("--quality", action="store_true", help="add torchaudio SQUIM estimates (a signal-quality proxy, not realism)")
    p = sub.add_parser("redo"); p.add_argument("project"); p.add_argument("line"); p.add_argument("--seed", type=int, default=None)
    p.add_argument("--mood", default=None); p.add_argument("--style", default=None); p.add_argument("--exaggeration", type=float, default=None); p.add_argument("--pace", default=None)
    p = sub.add_parser("words", help="homophones: tell the check that a transcriber's spelling is the word you wrote")
    p.add_argument("project"); p.add_argument("--add", action="append", default=[], metavar="HEARD=WRITTEN", help='e.g. --add emos=emus (the transcript hears "emos", the script says "emus")')
    p = sub.add_parser("measure"); p.add_argument("files", nargs="+"); p.add_argument("--words", type=int, default=None)
    a = ap.parse_args(argv)
    d = config()["defaults"]
    if a.cmd == "setup":
        for e in (ENGINES if a.engine == "all" else [a.engine]):
            setup(e, Path(a.home) if a.home else None, a.gpu, a.dry_run)
        return 0
    if a.cmd == "engines":
        log(json.dumps(engines_status(), indent=1))
        return 0
    if a.cmd == "say":
        studio = {k: v for k, v in {"gender": a.gender, "style": a.style, "pace": a.pace, "seed": a.seed, "reference": a.reference,
                                   "reference_consent": a.i_have_consent or None}.items() if v is not None}
        cl = say(a.text, Path(a.out), a.engine or d["engine"], studio)
        st = cl["studio"]
        log(json.dumps({"out": a.out, "wps": st["wps"], "target_wps": st["target_wps"], "converged": st["converged"], "pauses": st["pauses"], "f0": st["f0"],
                        "reads_as": st["reads_as"], "air_db": st["air_db"], "stretch": st["stretch"], "rounds": st["rounds"],
                        "words_ok": all(s.get("ok") is not False for s in st["sentences"]), "voice_source": st["voice_source"]}))
        return 0
    if a.cmd == "audition":
        if not a.matrix:
            raise FishError("use --matrix (for the interview's shortlist auditions: fishvideo voices <dir> --audition)")
        engine, lang = a.engine or d["engine"], "en-US"
        if a.project:
            project = ensure_project(a.project)
            vc = project_config(project)["voice"]
            engine, lang = a.engine or (vc.get("provider") if vc.get("provider") in ENGINES else engine), vc.get("language") or lang
        out = Path(a.out) if a.out else (project / "build" / "auditions" / "studio" if a.project else None)
        if out is None:
            raise FishError("give a project or --out DIR")
        styles = a.styles.split(",") if a.styles else list(config()["styles"])
        audition_matrix(out, engine, a.genders.split(","), styles, a.pace, a.text, lang)
        return 0
    if a.cmd == "check":
        project = ensure_project(a.project)
        rep = check_project(project, not a.no_transcript, a.quality)
        if a.fix:
            fixed = fix_lines(project, rep)
            if fixed:
                log(f"regenerated: {', '.join(fixed)}")
                rep = check_project(project, not a.no_transcript, a.quality)
        for lid, ln in rep["lines"].items():
            m = ln["measure"]
            log(f"  {lid:<18} {m.get('wps')} wps  {len(m.get('pauses') or [])} pauses  f0 {m.get('f0')}  air {m.get('air_db')}  " + ("ok" if not ln["issues"] else ""))
            for lv, msg in ln["issues"]:
                log(f"      {lv}  {msg}")
        for r in rep["rows"]:
            log(f"  {r['status']:<4}  {r['check']:<16} {r['detail']}")
        return 1 if any(r["status"] == "FAIL" for r in rep["rows"]) else 0
    if a.cmd == "words":
        f = Path(a.project) / "brief.yaml"
        b = load_yaml(f)
        al = (((b.setdefault("voice", {})).setdefault("studio", {})).setdefault("aliases", {}))
        for item in a.add:
            if "=" not in item:
                raise FishError(f"--add wants HEARD=WRITTEN, not '{item}'")
            h, w = item.split("=", 1)
            al[h.strip().lower()] = w.strip().lower()
        if a.add:
            save_yaml(f, b)
        log("known homophones (heard -> written): " + (", ".join(f"{k} -> {v}" for k, v in al.items()) or "none") +
            "\nThey only change the words check, never the audio, so no line is re-voiced. If a word is genuinely mispronounced, respell it for the engine in voice.pronunciations instead.")
        return 0
    if a.cmd == "redo":
        cl = redo(Path(a.project), a.line, seed=a.seed, mood=a.mood, style=a.style, exaggeration=a.exaggeration, pace=a.pace)
        st = cl["studio"]
        log(json.dumps({"line": a.line, "wav": cl["wav"], "wps": st["wps"], "words_ok": all(s.get("ok") is not False for s in st["sentences"])}))
        return 0
    if a.cmd == "measure":
        for f in a.files:
            x, sr = load_audio(f)
            m = measure(x, sr, a.words)
            log(json.dumps({"file": Path(f).name, **{k: m.get(k) for k in ("duration", "wps", "articulation", "pauses", "f0", "f0_iqr", "air_db", "rms_db", "peak", "clip_run", "head", "tail")},
                            "reads_as": gender_of(m.get("f0"))}))
        return 0
    return 0


if __name__ == "__main__":
    main_guard(cli)
