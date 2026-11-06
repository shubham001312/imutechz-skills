"""Unit tests for the pure functions of the Fish Video Skill (fast, offline)."""
import json
import subprocess

import pytest

import brief
import captions
import fvcore
import package
import reference
import research
import storyboard as sb
import voice


# ------------------------------------------------------------------ brief
@pytest.mark.parametrize("text,sec", [("a 45 second promo", 45), ("2 min explainer", 120), ("make it 1:30 long", 90), ("90s cut", 90), ("about cats", None)])
def test_parse_length(text, sec):
    assert brief.parse_length(text) == sec


def test_parse_prompt_extracts_only_stated_facts():
    b = brief.parse_prompt("A 60 second LinkedIn and YouTube Shorts promo for https://acme.dev in Hindi, like https://youtu.be/abc123")
    assert b["length"] == 60
    assert b["platforms"] == ["linkedin", "shorts"]  # prompt order
    assert b["website"]["url"] == "https://acme.dev"
    assert b["reference"]["src"] == "https://youtu.be/abc123"
    assert b["language"] == "hi-IN"
    assert b["structure"] == "promo"
    assert "facts" not in b


def test_parse_prompt_defaults_to_tour_with_a_site():
    b = brief.parse_prompt("Walk through https://example.com for YouTube")
    assert b["structure"] == "product-tour" and b["platforms"] == ["youtube"]


def test_make_brief_defaults_to_the_chatterbox_soft_voice():
    b = brief.make_brief("A 30 s explainer about rainwater")
    assert b["voice"]["provider"] == "chatterbox"
    assert b["voice"]["studio"]["style"] == "chatterbox-soft"
    assert b["pacing"] == {"max_word_gap": 0.9, "line_gap": 0.05} and b["mix"]["music_under_voice_db"] == -12
    assert b["voice"]["elevenlabs"]["voice_id"] == "fydPJq00SigRIaPxWgiS"      # still there for a user who picks it
    assert b["length"] == 30 and b["title"]


# ------------------------------------------------------------------ narration markup
def test_parse_say_pairs_and_units():
    disp, say, units = sb.parse_say("Run {GGUF|G G U F} files, {v0.3|version zero point three}.")
    assert disp == "Run GGUF files, v0.3."
    assert say == "Run G G U F files, version zero point three."
    assert [u["w"] for u in units] == ["Run", "GGUF", "files,", "v0.3."]
    # character ranges point into the spoken string
    u = units[1]
    assert say[u["s"]:u["e"]] == "G G U F"


def test_apply_pronunciations_whole_words_only():
    out = sb.apply_pronunciations("IMURUN and IMURUNX and {IMURUN|x}", {"IMURUN": "Imu run"})
    assert out == "{IMURUN|Imu run} and IMURUNX and {IMURUN|x}"


def test_map_units_from_word_timings():
    _, say, units = sb.parse_say("Hello {GGUF|G G U F} world")
    words = [{"text": "Hello", "start": 0.1, "end": 0.4, "char": 0}, {"text": "G", "start": 0.5, "end": 0.6, "char": 6},
             {"text": "F", "start": 0.9, "end": 1.0, "char": 12}, {"text": "world", "start": 1.1, "end": 1.4, "char": 14}]
    m = sb.map_units(units, words)
    assert m[1] == {"w": "GGUF", "t0": 0.5, "t1": 1.0}
    assert m[2]["t0"] == 1.1


def test_estimate_seconds_scales_with_words():
    a = sb.estimate_seconds("one two three four five six", 150)
    b = sb.estimate_seconds("one two three four five six seven eight nine ten eleven twelve", 150)
    assert 2.0 < a < 3.0 and b > a * 1.8


# ------------------------------------------------------------------ storyboard
def test_validate_catches_errors():
    errs, warns = sb.validate({"scenes": [{"id": "a", "type": "nope"}, {"id": "a", "type": "tour", "params": {"shot": "x"}}]})
    assert any("unknown type" in e for e in errs)
    assert any("duplicate id" in e for e in errs)
    assert any("not in captures" in e for e in errs)
    assert any("end" in w for w in warns)


def test_resolve_snaps_to_bars(smoke_project):
    cfg = fvcore.project_config(smoke_project)
    cfg["pacing"]["snap"] = "bar"          # the old grid is opt-in now; narration drives time by default
    story = fvcore.load_yaml(smoke_project / "storyboard.yaml")
    tl = sb.resolve(smoke_project, "youtube", cfg, story)
    assert tl["W"] == 1920 and tl["bpm"] == 120
    for s in tl["scenes"]:
        assert abs(s["t0"] / 2 - round(s["t0"] / 2)) < 1e-9, "every cut on a 2 s bar line"
    assert tl["duration"] == tl["bars"] * 2
    # narration fits inside its scene
    for v in tl["voice_lines"]:
        sc = next(s for s in tl["scenes"] if s["id"] == v["scene"])
        assert sc["t0"] <= v["at"] and v["at"] + v["dur"] <= sc["t1"]
    assert tl["captions"]["burn"] is False
    tl2 = sb.resolve(smoke_project, "shorts", cfg, story)
    assert tl2["captions"]["burn"] is True and tl2["H"] == 1920
    assert tl2["music"][-1][1] == 0


def test_resolve_uses_voice_clip_lengths(smoke_project):
    cfg = fvcore.project_config(smoke_project)
    cfg["pacing"].update(snap="bar", lead_in=0.35, tail=0.55)          # legacy bar grid
    story = fvcore.load_yaml(smoke_project / "storyboard.yaml")
    line = sb.scene_lines(story["scenes"][0], cfg["brief"]["voice"]["pronunciations"])[0]
    clip = {"say": line["say"], "speech_end": 7.3, "wav": "x.wav", "words": [{"text": "x", "start": 0.0, "end": 7.3, "char": 0}]}
    tl = sb.resolve(smoke_project, "youtube", cfg, story, {line["id"]: clip})
    # lead-in 0.35 + speech 7.3 + tail 0.55 = 8.2 s -> ceil(8.2 / 2) = 5 bars
    assert tl["scenes"][0]["bars"] == 5
    assert tl["voice_lines"][0]["estimated"] is False and tl["voice_lines"][0]["wav"] == "x.wav"


def test_build_writes_timelines(smoke_project):
    sb.build(smoke_project, quiet=True)
    for p in ("youtube", "shorts", "thumbnail"):
        tl = json.loads((smoke_project / "build" / f"timeline-{p}.json").read_text(encoding="utf-8"))
        assert tl["scenes"]
    assert (smoke_project / "build" / "captures.json").exists()
    md = sb.script_md(smoke_project).read_text(encoding="utf-8")
    assert "Every drop, counted." in md and "Tide well" in md


def test_scaffold_is_a_skeleton_not_copy(tmp_path):
    """The scaffold gives structure only; the gate blocks any TODO / stock phrase."""
    import interview
    from fvcore import save_yaml
    b = brief.make_brief("A 40 second explainer about \"Solar kettles\" for YouTube")
    b["points"] = ["Sun heats water", "No fuel needed", "Works off-grid"]
    b["style"] = "whiteboard-explainer"
    story = sb.scaffold(b)
    errs, warns = sb.validate(story)
    assert not errs
    assert story["scenes"][-1]["type"] == "end"
    assert any("TODO" in w for w in warns)          # every word is left for the agent
    assert "explained" not in repr(story).lower()   # no v1 stock copy
    save_yaml(tmp_path / "brief.yaml", b)
    save_yaml(tmp_path / "storyboard.yaml", story)
    probs = interview.copy_problems(tmp_path)
    assert probs and any("placeholder" in p for p in probs)
    errs = interview.gate(tmp_path)
    assert any("interview" in e for e in errs)


# ------------------------------------------------------------------ captions
def words_of(text, start=0.0, step=0.4):
    return [{"w": w, "t0": round(start + i * step, 3), "t1": round(start + i * step + 0.3, 3)} for i, w in enumerate(text.split())]


def test_chunk_words_limits_and_order():
    ws = words_of("This is a fairly long sentence that should be split into readable caption cues for the viewer. And a second one.")
    cues = captions.chunk_words(ws, max_chars=20, max_lines=2)
    assert all(len(c["text"]) <= 40 for c in cues)
    assert " ".join(c["text"] for c in cues) == " ".join(w["w"] for w in ws)
    assert all(cues[i]["end"] <= cues[i + 1]["start"] + 1e-9 for i in range(len(cues) - 1))
    assert not captions.sync_check(cues, ws)


def test_chunk_breaks_on_pause():
    ws = words_of("first part", 0) + words_of("second part", 3.0)
    cues = captions.chunk_words(ws)
    assert [c["text"] for c in cues] == ["first part", "second part"]


def test_wrap_lines_balanced():
    lines = captions.wrap_lines("The quick brown fox jumps over the lazy dog again", 30, 2)
    assert len(lines) == 2 and all(len(l) <= 30 for l in lines)


def test_srt_roundtrip_and_check():
    cues = captions.chunk_words(words_of("Hello there friend. How are you today?"))
    srt = captions.to_srt(cues)
    back = captions.parse_srt(srt)
    assert len(back) == len(cues) and back[0]["text"].startswith("Hello")
    assert captions.check_cues(back) == []
    vtt = captions.to_vtt(cues)
    assert vtt.startswith("WEBVTT") and "-->" in vtt
    bad = [{"start": 0, "end": 1, "text": "x" * 100}, {"start": 0.5, "end": 2, "text": "y"}]
    issues = captions.check_cues(bad, 42, 2, 20)
    assert any("overlaps" in i for i in issues) and any("chars/s" in i for i in issues)


def test_fmt_time():
    assert fvcore.fmt_time(3661.5) == "01:01:01,500"
    assert fvcore.fmt_time(1.0, ".") == "00:00:01.000"


# ------------------------------------------------------------------ research / fact check
def test_extract_html():
    html = "<html><head><title>Acme &amp; Co</title><meta name=description content='Fast kettles'></head><body><nav>menu</nav><h1>Boil in 90 seconds</h1><p>Used by 1,200 cafés.</p><script>x=1</script></body></html>"
    ex = research.extract(html)
    assert ex["title"] == "Acme & Co" and ex["description"] == "Fast kettles"
    assert ex["headings"] == ["Boil in 90 seconds"]
    assert "menu" not in ex["text"] and "x=1" not in ex["text"] and "1,200" in ex["text"]


@pytest.mark.parametrize("s,n", [("10,631", "10631"), ("2.10", "2.1"), ("v0.3.0", "0.3.0"), ("15", "15")])
def test_norm_number(s, n):
    assert research.norm_number(s) == n


def test_check_claims_flags_unsourced_numbers(smoke_project):
    r = research.check_claims(smoke_project)
    assert r["unsupported"] == []
    story = fvcore.load_yaml(smoke_project / "storyboard.yaml")
    story["scenes"][0]["say"] = "Saves 42% of water."
    fvcore.save_yaml(smoke_project / "storyboard.yaml", story)
    r = research.check_claims(smoke_project)
    assert r["unsupported"] == ["hook: 42"]


# ------------------------------------------------------------------ reference
def test_shots_from_cuts_merges_flashes():
    shots = reference.shots_from_cuts([1.0, 1.1, 3.0, 9.9], 10.0)
    assert [s["start"] for s in shots] == [0.0, 1.0, 3.0]
    assert shots[-1]["end"] == 10.0
    p = reference.pacing(shots, 10.0)
    assert p["shots"] == 3 and p["per_minute"] == 18.0


def test_kmeans_finds_two_colours():
    px = [(255, 0, 0)] * 70 + [(0, 0, 255)] * 30
    out = reference.kmeans(px, 2)
    assert out[0][0] == [255, 0, 0] and abs(out[0][1] - 0.7) < 1e-9


# ------------------------------------------------------------------ voice
def test_eleven_words_from_alignment():
    text = "Hi, G G U F!"
    al = {"characters": list(text), "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
          "character_end_times_seconds": [i * 0.1 + 0.08 for i in range(len(text))]}
    w = voice.eleven_words(al)
    assert [x["text"] for x in w] == ["Hi,", "G", "G", "U", "F!"]
    assert w[0]["end"] == pytest.approx(0.18)  # the comma does not stretch the word
    assert w[4]["char"] == 10


def test_pick_provider_falls_back_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    cfg = {"voice": fvcore.defaults()["voice"]}
    monkeypatch.setattr(fvcore, "SKILL", tmp_path)  # no skill .env either
    prov, key = voice.pick_provider(cfg, tmp_path)
    assert prov == "edge-tts" and key == ""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    assert voice.pick_provider(cfg, tmp_path) == ("elevenlabs", "test-key-not-real")


def test_secret_reads_dotenv_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    (tmp_path / ".env").write_text("# c\nELEVENLABS_API_KEY='abc'\n", encoding="utf-8")
    assert fvcore.secret("ELEVENLABS_API_KEY", tmp_path) == "abc"


# ------------------------------------------------------------------ package / qa helpers
def test_chapters_need_three_of_ten_seconds():
    tl = {"scenes": [{"t0": 0, "chapter": None}, {"t0": 14, "chapter": "01 · What"}, {"t0": 32, "chapter": "02 · How"}]}
    assert package.chapters(tl) == [("0:00", "Intro"), ("0:14", "What"), ("0:32", "How")]
    tl["scenes"][2]["t0"] = 18
    assert package.chapters(tl) == []


def test_fill_template():
    out = package.fill("A {{x}}\n\n\n\n{{missing}}B", {"x": 1})
    assert out == "A 1\n\nB\n"


def test_faststart_detection(tmp_path):
    ff = fvcore.ffmpeg_bin()
    base = [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    subprocess.run(base + ["-movflags", "+faststart", str(a)], check=True)
    subprocess.run(base + [str(b)], check=True)
    import qa
    assert qa.faststart(a) is True and qa.faststart(b) is False


def test_slugify_and_hash():
    assert fvcore.slugify("Hello, World! 2026") == "hello-world-2026"
    assert fvcore.sha1({"a": 1}) == fvcore.sha1({"a": 1}) != fvcore.sha1({"a": 2})


def test_deep_merge():
    assert fvcore.deep_merge({"a": {"b": 1, "c": 2}, "l": [1]}, {"a": {"b": 3}, "l": [2]}) == {"a": {"b": 3, "c": 2}, "l": [2]}


# ------------------------------------------------------------------ interview / gate
def test_interview_maps_answers_and_gates(tmp_path):
    import interview
    from fvcore import save_yaml, load_yaml
    save_yaml(tmp_path / "brief.yaml", brief.make_brief("A short about habits for YouTube Shorts"))
    assert interview.open_questions(tmp_path)[0]["round"] == "purpose"
    ans = {"topic": "Why habits stick", "goal": "story", "audience": "curious beginners", "platforms": '["shorts"]',
           "length": "25", "style": "glow-metaphor", "hook": "visual", "theme": "none", "palette": "mono-glow", "mode": "auto", "type": "grotesk",
           "texture": "grain", "voice_energy": "cinematic", "voice": "christopher", "music": "cinematic-swell", "sfx": "rich",
           "real_assets": "none", "screen": "none", "points": "cue\nroutine\nreward", "cta": "follow", "language": "en-US",
           "captions": "pop", "thumbnail": "frame", "checkpoints": '["final"]', "keys_have": '[]'}
    interview.record(tmp_path, ans)
    b = load_yaml(tmp_path / "brief.yaml")
    assert b["platforms"] == ["shorts"] and b["brand"]["colors"]["bg"] == "#050505"
    assert b["voice"]["fallback"]["voice"] == "en-US-ChristopherNeural" and b["voice"]["provider"] == "edge-tts"
    assert b["tempo"]["bpm"] == 80 and b["captions"]["style"] == "pop" and b["sfx"]["density"] == "rich"
    assert b["points"] == ["cue", "routine", "reward"]
    assert any("not confirmed" in e for e in interview.gate(tmp_path, "script"))
    interview.confirm(tmp_path)
    assert any("trend research missing" in e for e in interview.gate(tmp_path, "script"))   # live research is enforced
    import trends
    trends.mark_unavailable(tmp_path, "offline unit test: no search")
    assert interview.gate(tmp_path, "script") == []
    # a storyboard copied from the scaffold is still blocked at render
    save_yaml(tmp_path / "storyboard.yaml", sb.scaffold(load_yaml(tmp_path / "brief.yaml")))
    assert interview.gate(tmp_path, "render")


# ------------------------------------------------------------------ looks: new scenes, captions style, texture, camera
def test_resolve_passes_looks_fields(smoke_project):
    cfg = fvcore.project_config(smoke_project)
    cfg["brief"]["voice"] = {"provider": "none"}
    cfg["brief"]["captions"] = {"style": "pop"}
    story = {"texture": "paper", "sfx": "rich", "scenes": [
        {"id": "a", "type": "collage", "bars": 2, "caption": "Most of your day runs on autopilot.",
         "camera": "drift+dolly-in", "camera_shake": 0.3, "params": {"title": "X"}},
        {"id": "b", "type": "neonline", "transition": "zoom", "camera_from": "prev", "params": {"steps": [{"label": "A"}, {"label": "B"}]}},
        {"id": "c", "type": "stepcard", "transition": "flip", "params": {"n": 1}},
        {"id": "end", "type": "end", "transition": "defocus", "params": {}},
    ]}
    errs, _ = sb.validate(story)
    assert not errs
    tl = sb.resolve(smoke_project, "shorts", cfg, story)
    assert tl["texture"] == "paper" and tl["sfx"] == {"density": "rich"} and tl["captions"]["style"] == "pop"
    a, b = tl["scenes"][0], tl["scenes"][1]
    assert a["camera"] == "drift+dolly-in" and a["camera_shake"] == 0.3 and b["camera_from"] == "prev"
    assert "camera" not in tl["scenes"][2]
    # silent captions: words placed inside the scene, no voice lines
    assert not tl["voice_lines"] and tl["words"] and tl["words"][0]["w"] == "Most"
    assert all(a["t0"] <= w["t0"] < a["t1"] for w in tl["words"])
    assert tl["scenes"][2]["bars"] == 1  # stepcards are short


def test_validate_rejects_unknown_transition():
    errs, _ = sb.validate({"scenes": [{"id": "a", "type": "collage", "transition": "spin"}]})
    assert any("transition" in e for e in errs)


# ------------------------------------------------------------------ explicit cues, custom scenes, custom sound levels
def test_validate_allows_custom_scene_types_only_when_declared():
    scene = {"id": "a", "type": "myscene", "params": {}}
    assert sb.validate({"scenes": [scene]})[0]
    assert not sb.validate({"custom_scenes": ["scenes/custom.js"], "scenes": [scene]})[0]


def test_roadmap_and_pile_are_known_scene_types():
    errs, _ = sb.validate({"scenes": [{"id": "a", "type": "pile", "params": {}}, {"id": "b", "type": "roadmap", "params": {}}]})
    assert not errs


def test_resolve_keeps_explicit_cues_for_the_stage(smoke_project):
    cfg = fvcore.project_config(smoke_project)
    cfg["brief"]["voice"] = {"provider": "none"}
    cue = {"lt": 0.5, "type": "impact", "lvl": 3}
    tl = sb.resolve(smoke_project, "shorts", cfg, {"scenes": [{"id": "a", "type": "kinetic", "bars": 2, "cues": [cue], "params": {"lines": ["x"]}}]})
    assert tl["scenes"][0]["params"]["cues"] == [cue]


def test_stage_reads_explicit_cues():
    src = (fvcore.SKILL / "scripts" / "stage" / "main.js").read_text(encoding="utf-8")
    assert "it.c.p.cues" in src


def test_qa_flags_explicit_cue_that_never_reached_the_render():
    import qa
    story = {"scenes": [{"id": "a", "cues": [{"type": "boom"}, {"type": "pop", "lvl": 1}]}]}
    assert qa.explicit_cues(story, [{"scene": "a", "type": "boom"}], "standard")["status"] == "PASS"  # pop is filtered by density
    assert qa.explicit_cues(story, [], "standard")["status"] == "FAIL"


def test_qa_bare_regions_finds_an_empty_half(tmp_path):
    import qa
    ff = fvcore.ffmpeg_bin()
    half = tmp_path / "half.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=5", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=5",
                    "-filter_complex", "[1]crop=320:90:0:0[b];[0][b]overlay=0:90", "-pix_fmt", "yuv420p", str(half)], check=True)
    full = tmp_path / "full.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=5", "-pix_fmt", "yuv420p", str(full)], check=True)
    assert qa.bare_regions(half)["status"] == "WARN"
    assert qa.bare_regions(full)["status"] == "PASS"


def test_sfx_levels_from_the_brief_apply_to_custom_cue_types(tmp_path):
    import wave
    import numpy as np
    import sfx
    (tmp_path / "brief.yaml").write_text("title: t\nmix:\n  sfx_levels:\n    mysound: -6\n", encoding="utf-8")
    assert sfx.load_brief_mix(tmp_path / "missing") == {}
    d = tmp_path / "assets" / "sfx" / "mysound"
    d.mkdir(parents=True)
    tone = (np.sin(np.arange(4800) * 0.05) * 20000).astype("<i2")
    with wave.open(str(d / "a.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(tone.tobytes())
    b = tmp_path / "build" / "youtube"
    b.mkdir(parents=True)
    fvcore.save_json(b / "info.json", {"duration": 1.0, "cues": [{"t": 0.2, "type": "mysound"}]})
    assert sfx.build(tmp_path, "youtube")["placed"] == 1
    data = (b / "sfx-samples.wav").read_bytes()
    peak = np.abs(np.frombuffer(data[data.find(b"data") + 8:], dtype="<f4")).max()
    assert abs(20 * np.log10(peak) - (-6)) < 0.2


def test_mix_ffmpeg_hang_is_killed_retried_then_reported(monkeypatch):
    """A stalled mix ffmpeg (0% CPU, never exits) must not hang render: timeout, one retry, actionable error."""
    import sys
    import render
    calls = []
    real = fvcore.run
    def fake(cmd, **kw):                 # stands in for ffmpeg: a process that sleeps forever
        calls.append(kw.get("timeout"))
        return real([sys.executable, "-c", "import time; time.sleep(60)"], **kw)
    monkeypatch.setattr(render, "run", fake)
    with pytest.raises(fvcore.FishError) as e:
        render._run_mix(["ffmpeg"], 5.0, timeout=0.5)
    assert calls == [0.5, 0.5]
    assert "FISH_MIX_TIMEOUT" in str(e.value)


def test_mix_ffmpeg_retry_recovers_after_one_stall(monkeypatch):
    import sys
    import render
    real, n = fvcore.run, []
    def fake(cmd, **kw):
        n.append(1)
        code = "import time; time.sleep(60)" if len(n) == 1 else "pass"
        return real([sys.executable, "-c", code], **kw)
    monkeypatch.setattr(render, "run", fake)
    render._run_mix(["ffmpeg"], 5.0, timeout=0.5)
    assert len(n) == 2


def _synth(n, fn, H=36, W=64):
    import numpy as np
    return np.stack([fn(i) for i in range(n)]).astype(float)


def _busy(seed=0, H=36, W=64):
    import numpy as np
    return np.random.default_rng(seed).integers(40, 220, (H, W)).astype(float)


def test_flat_regions_catches_a_two_second_empty_half():
    import qa
    def f(i):                                   # 4 s at 2 fps; bottom half empty from 1.0 s to 3.0 s (4 samples = 2 s)
        a = _busy(i); 
        if 2 <= i < 6: a[18:, :] = 20
        return a
    got = qa.flat_regions(_synth(8, f), fps=2, hold=1.5)
    assert any("bottom-left" in g for g in got) and any("bottom-right" in g for g in got)


def test_qa_bare_regions_finds_a_two_second_empty_half(tmp_path):
    """Regression: three one-second samples in a row were required, so a 2 s empty half passed."""
    import qa
    ff = fvcore.ffmpeg_bin()
    v = tmp_path / "gap.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=6", "-vf",
                    "drawbox=x=0:y=90:w=320:h=90:color=black:t=fill:enable='between(t,2,4)'", "-pix_fmt", "yuv420p", str(v)], check=True)
    assert qa.bare_regions(v)["status"] == "WARN"


def test_flat_regions_catches_nearly_blank_frames_over_a_faint_grid():
    import numpy as np
    import qa
    def f(i):
        a = np.full((36, 64), 30.0); a[::4, :] += 8; a[:, ::4] += 8     # faint grid: std > 3, so a plain flatness test misses it
        a[17:19, 24:40] = 240                                           # a title only
        return a
    assert _synth(1, f)[0][1:16, 1:31].std() > 3
    got = qa.flat_regions(_synth(8, f), fps=2, hold=1.5)
    assert any("top-left" in g for g in got)


def test_flat_regions_no_false_positive_on_fades_or_busy_frames():
    import qa
    def fade(i):                                # 1 s fade in from black at 2 fps: only 2 dark samples, under the 1.5 s hold
        k = min(1.0, i / 2.0)
        return _busy(i) * k
    frames = _synth(10, fade)
    assert qa.flat_regions(frames, fps=2, hold=1.5) == []
    assert qa.flat_regions(_synth(10, lambda i: _busy(i)), fps=2, hold=1.5) == []


def test_custom_scene_that_replaces_a_builtin_is_warned(tmp_path):
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "custom.js").write_text(
        '(() => { const S = (window.SCENES = window.SCENES || {});\n S.pile = { build() {} };\n S["roadmap"] = {};\n S.mything = {}; })();', encoding="utf-8")
    w = sb.custom_scene_overrides(tmp_path, {"custom_scenes": ["scenes/custom.js"]})
    assert len(w) == 2 and any("'pile'" in x for x in w) and any("'roadmap'" in x for x in w)
    assert not any("mything" in x for x in w)
    assert sb.custom_scene_overrides(tmp_path, {}) == []


def test_factcheck_skips_decorative_glyphs_but_not_real_numbers():
    sbd = {"scenes": [{"id": "a", "type": "roadmap", "say": "Plain words.", "params": {"nodes": [
        {"label": "Embed", "glyph": "0.12"},                                   # decorative by field
        {"label": "Ghost 7777", "decorative": True},                           # decorative by flag
        {"label": "Real 4242"}]}}]}
    got = {n for _, _, n in research.claims_in(sbd)}
    assert "4242" in got and "0.12" not in got and "7777" not in got


def test_package_slug_follows_the_current_title_not_the_prompt():
    b = brief.make_brief("A 20 s explainer about this")
    assert b["title"] != "this" and "slug" not in b          # a filler word is no title; no stale slug is saved
    b["title"] = "How Vector Search Works"
    assert package.package_slug(b) == "how-vector-search-works"
    b["title"] = "Renamed Later"
    assert package.package_slug(b) == "renamed-later"


def test_speech_mode_cuts_follow_the_voice_and_gaps_stay_small(smoke_project):
    cfg = fvcore.project_config(smoke_project)
    story = fvcore.load_yaml(smoke_project / "storyboard.yaml")
    lines = [l for s in story["scenes"] for l in sb.scene_lines(s)]
    clips = {l["id"]: {"say": l["say"], "speech_end": 3.1, "wav": "x.wav", "words": [{"text": "x", "start": 0.0, "end": 3.1, "char": 0}]} for l in lines}
    tl = sb.resolve(smoke_project, "shorts", cfg, story, clips)
    assert tl["snap"] == "speech"
    g = tl["gaps"]
    assert g["values"] and 0.1 <= min(g["values"]) and g["max"] <= 0.6, g
    # a planned pause is honoured and capped at 0.8 s
    assert sb.scene_lines({"id": "x", "say": [{"text": "Wait.", "pause": 5, "tag": "reveal"}]})[0]["pause"] == 0.8
    assert sb.scene_lines({"id": "x", "say": [{"text": "Wait.", "tag": "nonsense"}]})[0]["tag"] is None


def test_two_projects_get_different_scores_and_the_score_is_stored(tmp_path):
    import score
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    sa = score.derive(a, {"title": "Onoda part one", "music": {"mood": "dark-drone"}})
    sb2 = score.derive(b, {"title": "Cold brew in 60 seconds", "music": {"mood": "lofi-tech"}})
    assert score.signature(sa) != score.signature(sb2) and sa["seed"] != 12345
    assert (a / "score.json").exists() and score.derive(a, {"title": "changed later"}) == sa    # stored: repeatable
    other = score.derive(tmp_path / "c", {"title": "Onoda part two", "music": {"mood": "dark-drone"}})
    assert other["seed"] != sa["seed"]
    assert score.derive(tmp_path / "d", {"score": {"fixed": True, "key": "G"}}, {"fixed": True, "key": "G"}) == {"key": "G"}
