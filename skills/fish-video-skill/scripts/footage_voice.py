"""Voice for one Short: fish.audio TTS -> build/voice.wav, whisper word timings -> build/words.json.

    fishvideo footage voice <dir> [--force] [--speed 1.1]

Script markup in spec.yaml `script`:
    {name}                    anchor: the start time of the next spoken word (used by shots/overlays/sfx `at:`)
    [spoken words|SHOWN]      caption shows SHOWN for these spoken words (numbers, units)
"""
import json, re, subprocess, sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
from fvcore import FishError, ffmpeg_bin  # noqa: E402
FF = ffmpeg_bin()
# The house voice: fish.audio public voice "calm storyteller male" (deep, measured; sample in assets/voices/). Override per
# project with `voice: {reference_id, model, temperature, top_p}` in spec.yaml.
VOICE = {"reference_id": "e686ae649ee44f219a108aacba206c1a", "model": "s2.1-pro", "format": "wav", "temperature": 0.6, "top_p": 0.7}


def whisper_py() -> str:
    """An interpreter with faster-whisper (FISH_WHISPER_PYTHON, a voice engine env, or this one)."""
    import voicelab
    py = voicelab.whisper_python()
    if not py:
        raise FishError("word timings need faster-whisper: `fishvideo voice setup --engine qwen3` (or pip install faster-whisper)")
    return str(py)

TOKEN = re.compile(r"\{(\w+)\}|\[([^\]|]+)\|([^\]]+)\]([^\s{\[]*)|([^\s{\[]+)")


def parse(script: str):
    """-> units [{spoken:[words], shown, anchor_names}], spoken text."""
    units, pending = [], []
    for m in TOKEN.finditer(script):
        if m.group(1):
            pending.append(m.group(1)); continue
        if m.group(2):
            words, shown = m.group(2).split(), m.group(3) + m.group(4)
            words[-1] += m.group(4)
        else:
            words, shown = [m.group(5)], m.group(5)
        units.append({"spoken": words, "shown": shown, "anchors": pending}); pending = []
    if pending:
        units.append({"spoken": [], "shown": "", "anchors": pending})
    spoken = " ".join(w for u in units for w in u["spoken"])
    return units, spoken


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


WHISPER_SRC = r'''
import json, sys
import subprocess, numpy as np
from faster_whisper import WhisperModel
raw = subprocess.run([sys.argv[4] if len(sys.argv) > 4 else "ffmpeg", "-loglevel", "error", "-i", sys.argv[1], "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
audio = np.frombuffer(raw, np.float32)
m = WhisperModel(sys.argv[3] if len(sys.argv) > 3 else "small.en", device="cpu", compute_type="int8")
segs, _ = m.transcribe(audio, word_timestamps=True, language="en")
out = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
json.dump(out, open(sys.argv[2], "w"))
'''


def transcribe(audio, out_json, model="small.en"):
    subprocess.run([whisper_py(), "-c", WHISPER_SRC, str(audio), str(out_json), model, FF], check=True, capture_output=True)


def align(script_words, heard, total):
    """Map each script word to (start, end) using difflib on normalised tokens; interpolate the gaps."""
    import difflib
    a = [norm(w) for w in script_words]; b = [norm(h["w"]) for h in heard]
    times = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            h = heard[blk.b + k]; times[blk.a + k] = (h["s"], h["e"])
    # interpolate unknown runs between known neighbours
    i = 0
    while i < len(times):
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None:
                j += 1
            t0 = times[i - 1][1] if i > 0 else (heard[0]["s"] if heard else 0)
            t1 = times[j][0] if j < len(times) else (heard[-1]["e"] if heard else total)
            n = j - i; step = max(0.05, (t1 - t0) / n)
            for k in range(n):
                times[i + k] = (t0 + k * step, t0 + (k + 1) * step * 0.95)
            i = j
        else:
            i += 1
    return times


def run(vdir: Path, force=False, speed=None):
    spec = yaml.safe_load((vdir / "spec.yaml").read_text())
    units, spoken = parse(spec["script"])
    b = vdir / "build"; b.mkdir(exist_ok=True)
    wav = b / "voice.wav"
    sp = float(speed or spec.get("speed", 1.08))
    meta = b / "voice.meta.json"
    if force or not wav.exists() or json.loads(meta.read_text() if meta.exists() else "{}") != {"text": spoken, "speed": sp}:
        import fishaudio
        key = fishaudio.need_key(SKILL)
        text = f"[{spec.get('tone', 'calm')}] " + spoken
        raw = fishaudio.tts(text, {**VOICE, **(spec.get("voice") or {})}, key, speed=sp)
        (b / "voice_raw.wav").write_bytes(raw)
        # trim leading/trailing silence, normalise to -16 LUFS-ish, 48k mono
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(b / "voice_raw.wav"), "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse,"
                        "highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I=-15:TP=-1.5:LRA=7",
                        "-ar", "48000", "-ac", "1", str(wav)], check=True)
        meta.write_text(json.dumps({"text": spoken, "speed": sp}))
    dur = float(subprocess.run([FF, "-i", str(wav)], capture_output=True, text=True).stderr.split("Duration: ")[1].split(",")[0].split(":")[-1])
    hj = b / "heard.json"
    transcribe(wav, hj)
    heard = json.loads(hj.read_text())
    words = [w for u in units for w in u["spoken"]]
    times = align(words, heard, dur)
    k, anchors, caps = 0, {}, []
    for u in units:
        n = len(u["spoken"])
        if n == 0:
            for a in u["anchors"]:
                anchors[a] = dur
            continue
        s, e = times[k][0], times[k + n - 1][1]
        for a in u["anchors"]:
            anchors[a] = round(s, 3)
        caps.append({"text": u["shown"], "s": round(s, 3), "e": round(e, 3)})
        k += n
    out = {"duration": round(dur, 3), "anchors": anchors, "captions": caps, "spoken": spoken,
           "heard": " ".join(h["w"] for h in heard)}
    (b / "words.json").write_text(json.dumps(out, indent=1))
    print(f"voice {dur:.2f}s  words {len(words)}  wps {len(words) / dur:.2f}")
    print("HEARD:", out["heard"])
    print("ANCHORS:", anchors)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    sp = None
    if "--speed" in a:
        i = a.index("--speed"); sp = a[i + 1]; del a[i:i + 2]
    run(Path(a[0]), "--force" in a, sp)
