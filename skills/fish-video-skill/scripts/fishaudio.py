"""fish.audio cloud TTS with voice cloning (provider `fish`). Mirrors the ElevenLabs path in voice.py.

    fishvideo voice <dir> --provider fish
    fishvideo voice clone <dir> --sample my-voice.wav --provider fish --i-have-consent [--title T] [--text "transcript"]

API (checked against docs.fish.audio, 2026-11-12)
  TTS    POST https://api.fish.audio/v1/tts   Authorization: Bearer $FISH_API_KEY   header `model: s2.1-pro`
         JSON {text, reference_id, format, temperature, top_p, prosody:{speed, volume}, normalize, language}
         -> chunked audio bytes. No word timings are returned: they are estimated from the audio (see word_times).
  Clone  POST https://api.fish.audio/model    multipart {type=tts, title, train_mode=fast, visibility=private, voices=<file>}
         -> 201 {"_id": ...}; that id is the reference_id. Cached in the project's brief.yaml voice.fish.reference_id.
  Emotion  S2 family reads free-form [bracket] cues at the start of a sentence ("[calm]"); S1 uses (parenthesis).

The key comes from FISH_API_KEY (environment or .env) and is never printed or written.
"""
from __future__ import annotations

import argparse
import json
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from fvcore import FishError, load_yaml, log, main_guard, save_yaml, secret

TTS_URL = "https://api.fish.audio/v1/tts"
MODEL_URL = "https://api.fish.audio/model"
KEY_NAME = "FISH_API_KEY"

# Subtle, documentary delivery: a calm base, small lifts on hooks and reveals. Override with voice.fish.tags.
DEFAULT_TAGS = {"hook": "confident", "setup": "calm", "reveal": "determined", "punchline": "slightly satisfied", "beat": "calm"}
DEFAULT_BASE_TAG = "calm"
DEFAULT_TARGET_WPS = 2.7           # 2.6-2.8 documentary pace; the Shorts default elsewhere is ~3.3


def need_key(project: Path | None = None) -> str:
    key = secret(KEY_NAME, project)
    if not key:
        raise FishError(f"{KEY_NAME} is not set. Add `{KEY_NAME}=...` to the project or skill .env (or the environment); "
                        "the fish voice provider never falls back to another voice.")
    return key


def fish_cfg(voice_cfg: dict) -> dict:
    return voice_cfg.get("fish") or {}


def tag_text(say: str, tag: str | None, fc: dict) -> str:
    """Prefix the emotion cue the API understands. Empty `tags` entry or `emotion: false` turns it off."""
    if fc.get("emotion", True) is False:
        return say
    tags = {**DEFAULT_TAGS, **(fc.get("tags") or {})}
    cue = tags.get(tag) if tag else fc.get("base_tag", DEFAULT_BASE_TAG)
    if not cue:
        return say
    cue = str(cue).strip("[]() ")
    model = str(fc.get("model", "s2.1-pro"))
    return (f"({cue}) " if model == "s1" else f"[{cue}] ") + say


def _err(e: urllib.error.HTTPError) -> FishError:
    detail = e.read().decode("utf-8", "replace")[:300]
    return FishError(f"fish.audio HTTP {e.code}: {detail}")


def tts(text: str, fc: dict, key: str, speed: float = 1.0) -> bytes:
    """One TTS request; returns audio bytes in voice.fish.format. `text` already carries any emotion cue."""
    if not fc.get("reference_id"):
        raise FishError("voice.fish.reference_id is missing: run `fishvideo voice clone <dir> --sample <audio> --provider fish --i-have-consent` "
                        "or set voice.fish.reference_id (a voice model id from fish.audio).")
    body = {"text": text, "reference_id": fc["reference_id"], "format": fc.get("format", "mp3"),
            "temperature": fc.get("temperature", 0.6), "top_p": fc.get("top_p", 0.7),
            "prosody": {"speed": round(float(speed), 3), "volume": fc.get("volume", 0)}, "normalize": fc.get("normalize", True)}
    if fc.get("language"):
        body["language"] = fc["language"]
    req = urllib.request.Request(TTS_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "model": str(fc.get("model", "s2.1-pro"))})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        raise _err(e)
    except urllib.error.URLError as e:
        raise FishError(f"fish.audio unreachable: {e.reason}")
    if not audio:
        raise FishError("fish.audio returned no audio")
    return audio


def create_model(sample: Path, title: str, key: str, transcript: str | None = None) -> str:
    """Create a private voice model from one sample file; returns its id."""
    sample = Path(sample)
    b = uuid.uuid4().hex
    parts = []
    for name, val in (("type", "tts"), ("title", title), ("train_mode", "fast"), ("visibility", "private")) + ((("texts", transcript),) if transcript else ()):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode("utf-8"))
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="voices"; filename="{sample.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode("utf-8")
                 + sample.read_bytes() + b"\r\n")
    data = b"".join(parts) + f"--{b}--\r\n".encode()
    req = urllib.request.Request(MODEL_URL, data=data, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            js = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _err(e)
    except urllib.error.URLError as e:
        raise FishError(f"fish.audio unreachable: {e.reason}")
    if not js.get("_id"):
        raise FishError("fish.audio created no model id")
    return str(js["_id"])


def word_times(say: str, wav: Path) -> list[dict]:
    """Fish returns no timings: spread the words over the SPEECH part of the take, weighted by letters.
    (Exact enough for captions and scene timing; `fishvideo voice check` can verify with faster-whisper.)"""
    import re
    toks = [(m.group(0), m.start()) for m in re.finditer(r"\S+", say)]
    if not toks:
        return []
    t0, t1 = 0.0, None
    try:
        import voicelab
        x, sr = voicelab.read_wav(wav)
        a, b = voicelab._trim(x, sr, pad=0.0)
        t0, t1 = a / sr, b / sr
    except Exception:  # noqa: BLE001 - numpy missing or odd file: use the whole file
        pass
    if t1 is None or t1 <= t0:
        t1 = max(t0 + 0.5, 0.35 * len(toks))
    weights = [max(1, sum(ch.isalnum() for ch in t)) + 1 for t, _ in toks]
    total, t, words = sum(weights), t0, []
    for (tok, ch), wgt in zip(toks, weights):
        d = (t1 - t0) * wgt / total
        words.append({"text": tok, "start": round(t, 3), "end": round(t + d * 0.92, 3), "char": ch})
        t += d
    return words


def target_wps(fc: dict) -> float:
    return float(fc.get("target_wps", DEFAULT_TARGET_WPS))


def next_speed(speed: float, n_words: int, span: float, fc: dict) -> float | None:
    """Closed loop: the speed for one regeneration, or None when the line is within tolerance (or too short to steer)."""
    if n_words < int(fc.get("min_words", 6)) or span <= 0:
        return None
    wps = n_words / span
    if abs(wps - target_wps(fc)) <= float(fc.get("tolerance", 0.2)):
        return None
    lo, hi = fc.get("speed_range", [0.7, 1.3])
    new = round(min(hi, max(lo, speed * target_wps(fc) / wps)), 3)
    return None if abs(new - speed) < 0.01 else new


# ------------------------------------------------------------------ clone command
def clone_project(project: Path, sample: Path, title: str | None, consent: bool, transcript: str | None = None) -> str:
    import voicelab
    from fvcore import ensure_project
    project = ensure_project(project)
    sample = Path(sample)
    voicelab.check_reference(sample if sample.is_absolute() else Path.cwd() / sample, consent)
    key = need_key(project)
    brief_p = project / "brief.yaml"
    brief = load_yaml(brief_p)
    rid = create_model(sample if sample.is_absolute() else Path.cwd() / sample, title or f"{brief.get('title', project.name)} narrator", key, transcript)
    v = brief.setdefault("voice", {})
    v["provider"] = "fish"
    f = v.setdefault("fish", {})
    f["reference_id"] = rid
    f.pop("sample", None)
    save_yaml(brief_p, brief)
    log(f"fish: voice model created and saved to {brief_p.name} -> voice.fish.reference_id = {rid}")
    return rid


def ensure_reference(project: Path, cfg: dict, key: str) -> dict:
    """voice.fish.sample without a reference_id: clone once, write the id back, return the updated fish config."""
    fc = dict(fish_cfg(cfg["voice"]))
    if fc.get("reference_id") or not fc.get("sample"):
        return fc
    s = Path(fc["sample"])
    consent = bool(fc.get("sample_consent") or fc.get("consent"))
    rid = clone_project(project, s if s.is_absolute() else project / s, fc.get("title"), consent, fc.get("sample_text"))
    fc["reference_id"] = rid
    cfg["voice"].setdefault("fish", {})["reference_id"] = rid
    return fc


def cli_clone(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo voice clone")
    ap.add_argument("dir")
    ap.add_argument("--sample", required=True)
    ap.add_argument("--provider", default="fish", choices=["fish"])
    ap.add_argument("--title", default=None)
    ap.add_argument("--text", default=None, help="transcript of the sample (skips fish's ASR)")
    ap.add_argument("--i-have-consent", action="store_true", help="the sample is your own voice, or the speaker agreed to this use")
    a = ap.parse_args(argv)
    clone_project(Path(a.dir), Path(a.sample), a.title, a.i_have_consent, a.text)
    return 0


if __name__ == "__main__":
    main_guard(lambda: cli_clone(__import__("sys").argv[1:]))
