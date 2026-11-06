"""fishvideo: make a polished animated explainer / promo video from one brief.

    fishvideo new <dir> [--recipe roadmap-explainer|story-short|bold-short] --prompt "..." [--url URL] [--ref VIDEO] [--platforms youtube,linkedin] [--length 60] [--lang en-IN]
    fishvideo research <dir> [--url URL ...] [--from-json results.json]
    fishvideo reference <dir> [--src file|youtube-url]
    fishvideo script <dir> [--force]          scaffold storyboard.yaml (if missing) + write script.md
    fishvideo storyboard <dir> [--table youtube]
    fishvideo factcheck <dir>
    fishvideo capture <dir> [shot ...]
    fishvideo voice <dir> [--provider elevenlabs|edge-tts|chatterbox|kokoro|none] [--force]
    fishvideo voice setup|engines|say|audition|check|redo|measure ...   free local voices (references/local-voices.md)
    fishvideo music <dir> [--platform youtube]
    fishvideo music source <dir> [--q "style words"]    licensed CC0 / CC BY track for the trend, else the synthesised score
    fishvideo captions <dir>
    fishvideo stills <dir> [--platform youtube] [--at 1,5,9 | --scenes]
    fishvideo render <dir> [--platform youtube,linkedin] [--scale 0.5] [--from 10 --to 20] [--fast]
    fishvideo qa <dir> [--platform ...]
    fishvideo package <dir> [--name "Project 2"]
    fishvideo all <dir> [--prompt "..."] [--scale 1] [--fast]      every step, end to end (after the interview)
    fishvideo doctor [--keys]                                         check the toolchain, keys and optional extras

  Interview and gates (asked ONCE, before creation):
    fishvideo interview <dir> [--set id=value ...] [--answers a.json] [--summary] [--confirm]
    fishvideo voices <dir> --audition          render the audition line in each shortlisted voice
    fishvideo gate <dir> [--stage script|render]
    fishvideo approve <dir> storyboard|stills|final
  Research, YouTube, trends, assets, screen recording, analysis:
    fishvideo yt <search|info|subs|download|clip|suggest> ...
    fishvideo trends <dir> --topic "..." [--region IN] [--days 30]
    fishvideo assets <search|get|cutout|clip|shot|logo|icon|emoji|sfx-pack|credits> ...
    fishvideo memes <templates|trending|films|add|sheet|cut|caption|lint|sources> ...   memes, reaction clips, captions (see references/memes-and-real-assets.md)
    fishvideo sounds <synth|add|audition|search|list> ...   cue sounds: synthesise, import, audition
    fishvideo screenrec <record|import> <dir> <shot> ...
    fishvideo dissect <video> --out <dir> [--fps 4] [--vtt subs.vtt]
    fishvideo sfx <dir> --platform shorts      place sample SFX (normally inside render)
  Frame and thumbnail design (references/frame-design.md):
    fishvideo frame <sheet|lint|guides|variants|palette|compare> ...    review, measure and try looks on rendered stills
    fishvideo thumb <make|check|sheet|pick|cutout> ...                  designed 1280x720 thumbnails, legibility checks, mock feed
  Required before package:
    fishvideo thumbnail <dir>      the house thumbnail (headline + logo or picture tiles on a glowing road), checked; `package` refuses without it (--no-thumbnail only if the user asks)
  Quality gates (measured; a recipe makes them hard):
    fishvideo recipes | gates <dir> | signoff <dir> [--check]    formats, the imagery gate, the frame-sheet checklist
  Themes (config/themes.yaml):
    fishvideo themes [show <id> | preview [--out DIR] [--only a,b] | apply <dir> <id>]    list the looks, render one gallery image per theme
  Finish:
    fishvideo clean <dir> [--yes] [--keep-voice]   remove intermediates (only after the user approves + agrees)

Run with the skill's venv Python:  .venv/Scripts/python scripts/fishvideo.py ...  (Windows)
                                   .venv/bin/python scripts/fishvideo.py ...      (macOS/Linux)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fvcore import (SKILL, FishError, browser_bin, ensure_project, ffmpeg_bin, ffprobe_bin, last_json_line, load_json, load_yaml, save_json,
                    log, main_guard, node, node_bin, project_config, run, secret, warn)
import brief as briefmod
import captions as capmod
import package as pkgmod
import qa as qamod
import reference as refmod
import render as rendermod
import research as resmod
import storyboard as sbmod
import voice as voicemod
import interview as ivmod

PASSTHRU = {"yt": "youtube", "trends": "trends", "assets": "assets", "screenrec": "screenrec", "dissect": "dissect", "sfx": "sfx", "clean": "clean",
            "review": "review", "voiceover": "voiceover", "beats": "beats", "memes": "memes", "sounds": "sounds",
            "frame": "design", "thumb": "thumbs", "themes": "themes", "recipes": "recipes", "gates": "gates", "signoff": "gates", "budget": "gates", "thumbnail": "thumbs"}


def passthru(cmd: str, argv: list[str]) -> int:
    import importlib
    mod = importlib.import_module(PASSTHRU[cmd])
    if cmd == "thumbnail":
        return mod.thumbnail_cli(argv) or 0
    if cmd == "budget":
        return mod.budget_cli(argv) or 0
    if cmd == "signoff":
        return mod.signoff_cli(argv) or 0
    return mod.cli(argv) or 0


def brief_recipe(project: Path):
    return (project_config(project)["brief"]).get("recipe")


def qa_fail_errors(project: Path) -> list[str]:
    """Why `package` must refuse: a platform with no QA report, a stale one, or any FAIL check (each named with its detail)."""
    errs = []
    for plat in sbmod.platforms_of(project_config(project)):
        f = project / "build" / plat / "qa.json"
        if not f.exists():
            errs.append(f"{plat}: no QA report: run `fishvideo qa {project.name}`")
            continue
        finals = list((project / "build" / plat).glob("final*.mp4"))
        if finals and f.stat().st_mtime < max(x.stat().st_mtime for x in finals) - 1:
            errs.append(f"{plat}: the QA report is older than the last render: run `fishvideo qa {project.name}` again")
        for c in (load_json(f).get("checks") or []):
            if c.get("status") == "FAIL":
                errs.append(f"{plat}: QA FAIL `{c.get('check')}`: {str(c.get('detail'))[:160]}")
    return errs


def qa_gate_or_override(project: Path, reason: str | None, dest_after: bool = False) -> str | None:
    """Raise when QA is failing; with --accept-qa-fail the override is recorded (build/qa-override.json, and in the package) and returned."""
    errs = qa_fail_errors(project)
    if not errs:
        return None
    if not reason or len(reason.split()) < 3:
        raise FishError("package: QA is failing, so nothing is packaged:\n  - " + "\n  - ".join(errs[:12]) +
                        f"\nFix them and run `fishvideo qa {project.name}`. Only if the user accepts the failure, say so explicitly: `--accept-qa-fail \"<their words, 3+ words>\"` (it is recorded in the package).")
    import time
    save_json(project / "build" / "qa-override.json", {"when": time.strftime("%Y-%m-%d %H:%M"), "reason": reason, "failures": errs})
    warn("QA override recorded: " + reason)
    return reason


def gate_or_fail(project: Path, stage: str, force: bool = False) -> None:
    errs = ivmod.gate(project, stage, force)
    if errs:
        raise FishError("gate: not ready to " + stage + ":\n  - " + "\n  - ".join(errs))


def step(name: str):
    log(f"\n=== {name} " + "=" * max(0, 60 - len(name)))
    return time.time()


def cmd_new(a) -> Path:
    over = {}
    if a.url:
        over["website"] = {"url": a.url}
        over["sources"] = [a.url]
    if a.ref:
        over["reference"] = {"src": a.ref}
    if a.platforms:
        over["platforms"] = a.platforms.split(",")
    if a.length:
        over["length"] = a.length
    if a.lang:
        over["language"] = a.lang
    if a.title:
        over["title"] = a.title
    if getattr(a, "recipe", None):
        import recipes
        parsed = briefmod.parse_prompt(a.prompt or "") if a.prompt else {}
        base = {k: v for k, v in recipes.brief_over(a.recipe).items() if k not in parsed}      # the request beats the recipe's defaults
        over = {**base, **{k: v for k, v in over.items() if v not in (None, "", [], {})}}
    proj = briefmod.new_project(a.dir, a.prompt or "", force=a.force, **over)
    if getattr(a, "recipe", None):
        recipes.create(proj, a.recipe)
        import themes
        b = load_yaml(proj / "brief.yaml")
        themes.apply_to_brief(b)
        from fvcore import save_yaml
        save_yaml(proj / "brief.yaml", b)
        log(f"theme {b['theme']}; other themes for this recipe: {', '.join(t for t in recipes.get(a.recipe)['themes'] if t != b['theme'])}. Gallery: fishvideo themes preview")
    return proj


def cmd_capture(project: Path, shots: list[str]) -> None:
    spec = load_json(project / "build" / "captures.json", default={"shots": []})
    if not spec["shots"]:
        log("no captures in the storyboard")
        return
    if not browser_bin():
        raise FishError("capture needs Chromium/Brave/Chrome: set BROWSER=/path")
    node("capture.mjs", project, *shots)


def cmd_all(a) -> int:
    t0 = time.time()
    project = Path(a.dir).resolve()
    if not (project / "brief.yaml").exists():
        if not a.prompt:
            raise FishError("no brief.yaml: pass --prompt to create one")
        step("new")
        cmd_new(a)
    if not a.no_gate:
        gate_or_fail(project, "script")
    cfg = project_config(project)
    brief = cfg["brief"]
    if brief.get("sources") or (brief.get("website") or {}).get("url"):
        step("research")
        try:
            resmod.gather(project)
        except FishError as e:
            warn(f"research: {e}")
    if (brief.get("reference") or {}).get("src") and not a.skip_reference:
        step("reference")
        try:
            src = brief["reference"]["src"]
            path = refmod.download(src, project / "reference") if src.startswith("http") else Path(src)
            refmod.analyse(path, project / "reference")
        except FishError as e:
            warn(f"reference: {e}")
    step("script")
    if not (project / "storyboard.yaml").exists():
        rs = project / "research" / "sources.json"
        from fvcore import save_yaml
        save_yaml(project / "storyboard.yaml", sbmod.scaffold(brief, load_json(rs) if rs.exists() else None))
        log("scaffolded storyboard.yaml: write every TODO (copy, params, narration) for THIS video, then re-run `fishvideo all`")
        if not a.no_gate:
            raise FishError("the storyboard is a skeleton: write it before rendering (fishvideo gate blocks TODO text)")
    sbmod.build(project)
    step("capture")
    spec = load_json(project / "build" / "captures.json")
    missing = [s["id"] for s in spec["shots"] if a.recapture or not (project / "build" / "cap" / s["id"] / "meta.json").exists()]
    if missing:
        cmd_capture(project, missing)
    else:
        log("captures up to date")
    step("voice")
    voicemod.synthesize(project, a.provider)
    step("storyboard (timed to the voice)")
    sbmod.build(project)
    sbmod.script_md(project)
    step("factcheck")
    fc = resmod.check_claims(project)
    if fc["unsupported"]:
        msg = f"{len(fc['unsupported'])} numbers have no source: {fc['unsupported'][:6]}"
        if a.strict:
            raise FishError(msg)
        warn(msg)
    else:
        log(f"{fc['checked']} numbers, all supported")
    if not a.no_gate:
        gate_or_fail(project, "render")
    step("render")
    plats = a.platform.split(",") if a.platform else None
    rendermod.render(project, plats, scale=a.scale, workers=a.workers, fast=a.fast)
    step("thumbnails")
    try:
        import thumbs
        if not (project / "build" / "thumbnail" / "variants.json").exists():
            thumbs.thumbnail(project)
        else:
            log("thumbnail variants up to date (fishvideo thumb make to redraw)")
    except FishError as e:
        warn(f"thumbnails: {e}")
    step("qa")
    reps = qamod.qa(project, plats, lint=not a.no_lint)
    step("package")
    if not a.no_gate:
        qa_gate_or_override(project, None)
        import thumbs
        te = thumbs.package_gate(project)
        if te:
            raise FishError("package: the thumbnail step is not done:\n  - " + "\n  - ".join(te))
    dest = pkgmod.package(project, name=a.name)
    status = "FAIL" if any(r["status"] == "FAIL" for r in reps) else "PASS"
    log(f"\nall done in {(time.time() - t0) / 60:.1f} min: QA {status} -> {dest}")
    return 1 if status == "FAIL" and a.strict else 0


def cmd_doctor(keys: bool = False) -> int:
    ok = True

    def chk(name, fn):
        nonlocal ok
        try:
            v = fn()
            log(f"  ok    {name:<14} {v}")
        except Exception as e:
            ok = False
            log(f"  MISS  {name:<14} {e}")

    def _chatterbox():
        import voicelab
        if not voicelab.engine_ready("chatterbox"):
            raise RuntimeError("not installed: the recommended soft voice needs `fishvideo voice setup --engine chatterbox` (one command); until then pick another voice on purpose")
        return "installed (recommended soft voice: style chatterbox-soft)"
    chk("chatterbox", _chatterbox)

    def _fonts():
        import themes
        m = themes.missing_fonts(None)
        if m:
            raise RuntimeError(f"{len(m)} theme font files missing ({', '.join(sorted({x[0] for x in m})[:4])}...): run `npm install` in the skill folder")
        return "all theme fonts installed"
    chk("fonts", _fonts)
    chk("python", lambda: sys.version.split()[0])
    chk("pyyaml", lambda: __import__("yaml").__version__)
    chk("edge-tts", lambda: __import__("edge_tts").__version__)
    chk("yt-dlp", lambda: __import__("yt_dlp").version.__version__)
    chk("node", lambda: run([node_bin(), "-v"], capture=True).stdout.strip())
    chk("puppeteer", lambda: "installed" if (SKILL / "node_modules" / "puppeteer-core").exists() else (_ for _ in ()).throw(FishError("npm install")))
    chk("ffmpeg", lambda: run([ffmpeg_bin(), "-version"], capture=True).stdout.split("\n")[0][:60])
    chk("ffprobe", lambda: ffprobe_bin())
    chk("browser", lambda: browser_bin() or (_ for _ in ()).throw(FishError("set BROWSER=/path/to/chromium")))
    chk("numpy", lambda: __import__("numpy").__version__)
    chk("pillow", lambda: __import__("PIL").__version__)

    def opt(name, mod, hint):
        import importlib.util   # find, don't import: loading torch made doctor take minutes
        if importlib.util.find_spec(mod):
            log(f"  ok    {name:<14} installed")
        else:
            log(f"  info  {name:<14} not installed ({hint})")
    opt("rembg", "rembg", 'cut-outs: pip install "rembg[cpu]"')
    opt("kokoro", "kokoro", "local voices: pip install kokoro soundfile")
    opt("faster-whisper", "faster_whisper", "align your own VO: pip install faster-whisper")
    try:
        import voicelab
        for eng, st in voicelab.engines_status().items():
            if isinstance(st, dict):
                log(f"  {'ok  ' if st['installed'] else 'info'}  {'tts ' + eng:<14} " + (f"installed ({st['python']})" if st["installed"] else f"not installed (free local voice: fishvideo voice setup --engine {eng})"))
    except Exception as e:  # noqa: BLE001 - doctor must never fail on an optional engine
        log(f"  info  local voices   could not check: {str(e)[:80]}")
    lib = SKILL / "sfx" / "library" / "index.json"
    log(f"  {'ok  ' if lib.exists() else 'info'}  sfx library    {'present' if lib.exists() else 'not fetched: fishvideo assets sfx-pack (Kenney CC0); synth SFX used until then'}")
    KEYS = [("ELEVENLABS_API_KEY", "premium voices", "elevenlabs.io > Profile > API keys (paid plan for commercial use)", "edge-tts / Kokoro voices"),
            ("PEXELS_API_KEY", "stock photos + video", "pexels.com/api (free, instant)", "Openverse / Wikimedia / NASA (key-less)"),
            ("PIXABAY_API_KEY", "stock photos + video", "pixabay.com/api/docs (free, log in to see the key)", "Pexels or key-less sources"),
            ("FREESOUND_API_KEY", "CC0 sound effects", "freesound.org/apiv2/apply (free)", "Kenney CC0 packs + synth SFX"),
            ("YOUTUBE_API_KEY", "trending charts, fast search", "console.cloud.google.com > YouTube Data API v3 > Credentials (free quota)", "yt-dlp search (key-less)"),
            ("IMGFLIP_API_KEY", "full meme-template search (paid plan)", "imgflip.com/api", "the free top-templates list")]
    for k, what, how, fb in KEYS:
        have = bool(secret(k))
        log(f"  {'ok  ' if have else 'info'}  {k:<20} {'present' if have else 'missing'}" + ("" if have or not keys else f": {what}. Get it: {how}. Without it: {fb}"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fishvideo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def proj(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("dir")
        return p

    for name in ("new", "all"):
        p = proj(name)
        p.add_argument("--prompt", default="")
        p.add_argument("--url", default=None)
        p.add_argument("--ref", default=None)
        p.add_argument("--platforms", default=None)
        p.add_argument("--length", type=float, default=None)
        p.add_argument("--lang", default=None)
        p.add_argument("--title", default=None)
        p.add_argument("--recipe", default=None, help="roadmap-explainer | story-short | bold-short (fishvideo recipes)")
        p.add_argument("--force", action="store_true")
        if name == "all":
            p.add_argument("--platform", default=None, help="render only these (comma list)")
            p.add_argument("--scale", type=float, default=1.0)
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--fast", action="store_true")
            p.add_argument("--provider", default=None, choices=["elevenlabs", "edge-tts", "chatterbox", "kokoro", "none"])
            p.add_argument("--recapture", action="store_true")
            p.add_argument("--skip-reference", action="store_true")
            p.add_argument("--no-lint", action="store_true")
            p.add_argument("--strict", action="store_true", help="fail on unsupported numbers or a QA FAIL")
            p.add_argument("--name", default=None)
            p.add_argument("--no-gate", action="store_true", help="tests/CI only: skip the interview + copy gate")
    p = proj("research"); p.add_argument("--url", action="append", default=[]); p.add_argument("--from-json", default=None)
    p = proj("reference"); p.add_argument("--src", default=None); p.add_argument("--threshold", type=float, default=0.3)
    p = proj("script"); p.add_argument("--force", action="store_true")
    p = proj("storyboard"); p.add_argument("--table", default=None)
    proj("factcheck")
    p = proj("capture"); p.add_argument("shots", nargs="*")
    p = proj("voice"); p.add_argument("--provider", default=None, choices=["elevenlabs", "edge-tts", "chatterbox", "kokoro", "none"]); p.add_argument("--force", action="store_true")
    p = proj("music"); p.add_argument("--platform", default=None)
    proj("captions")
    p = proj("stills"); p.add_argument("--platform", default=None); p.add_argument("--at", default=None); p.add_argument("--scenes", action="store_true"); p.add_argument("--every", default=None)
    p = proj("render")
    p.add_argument("--platform", default=None); p.add_argument("--scale", type=float, default=1.0); p.add_argument("--workers", type=int, default=4)
    p.add_argument("--from", dest="t_from", type=float, default=None); p.add_argument("--to", dest="t_to", type=float, default=None)
    p.add_argument("--fast", action="store_true"); p.add_argument("--no-voice", action="store_true"); p.add_argument("--no-music", action="store_true")
    p = proj("qa"); p.add_argument("--platform", default=None); p.add_argument("--no-lint", action="store_true"); p.add_argument("--preview", action="store_true")
    p = proj("package"); p.add_argument("--name", default=None); p.add_argument("--out", default=None)
    p.add_argument("--no-thumbnail", action="store_true", help="only when the user explicitly asks for no thumbnail")
    p.add_argument("--accept-qa-fail", default=None, help="package despite failing QA: the user's words accepting it (recorded in the package)")
    p.add_argument("--no-gate", action="store_true")
    p = sub.add_parser("doctor"); p.add_argument("--keys", action="store_true", help="explain how to get each missing key")
    p = proj("gate"); p.add_argument("--stage", default="render", choices=["script", "render"])
    p = proj("approve"); p.add_argument("what", choices=["storyboard", "stills", "final"])
    p = proj("voices"); p.add_argument("--audition", action="store_true"); p.add_argument("--list", action="store_true")
    return ap


def cli(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in PASSTHRU:
        return passthru(argv[0], argv[1:])
    if argv[:2] == ["music", "source"]:             # licensed music matching the trend, CC0 / CC BY only (SKILL.md, "Audio")
        import assets
        return assets.cli(["music-source", *argv[2:]]) or 0
    if argv and argv[0] == "interview":
        return ivmod.cli(argv[1:])
    if argv and argv[0] == "voice" and len(argv) > 1 and argv[1] in ("setup", "engines", "say", "audition", "check", "redo", "measure", "words"):
        import voicelab                            # local voice studio (references/local-voices.md)
        return voicelab.cli(argv[1:])
    a = build_parser().parse_args(argv)
    if a.cmd == "doctor":
        return cmd_doctor(a.keys)
    if a.cmd == "new":
        cmd_new(a)
        return 0
    if a.cmd == "all":
        return cmd_all(a)
    project = ensure_project(a.dir)
    cfg = project_config(project)
    if a.cmd == "gate":
        errs = ivmod.gate(project, a.stage)
        for e in errs:
            log(f"  BLOCKED  {e}")
        log("gate: ready" if not errs else f"gate: {len(errs)} problem(s)")
        return 1 if errs else 0
    if a.cmd == "approve":
        ivmod.approve(project, a.what)
        return 0
    if a.cmd == "voices":
        if a.list:
            for v in voicemod.list_voices(cfg["brief"].get("language"), project):
                log(f"  {v}")
        else:
            ivmod.audition(project)
        return 0
    if a.cmd == "research":
        resmod.gather(project, a.url, Path(a.from_json) if a.from_json else None)
    elif a.cmd == "reference":
        refmod.cli([str(project)] + (["--src", a.src] if a.src else []) + ["--threshold", str(a.threshold)])
    elif a.cmd == "script":
        gate_or_fail(project, "script")
        f = project / "storyboard.yaml"
        if not f.exists() or a.force:
            from fvcore import save_yaml
            rs = project / "research" / "sources.json"
            save_yaml(f, sbmod.scaffold(cfg["brief"], load_json(rs) if rs.exists() else None))
            log(f"scaffolded {f}")
        sbmod.build(project)
        log(f"wrote {sbmod.script_md(project)}")
    elif a.cmd == "storyboard":
        sbmod.build(project)
        if a.table:
            log(sbmod.table(project, a.table))
    elif a.cmd == "factcheck":
        r = resmod.check_claims(project)
        log(f"{r['checked']} numbers checked; {len(r['unsupported'])} unsupported")
        for x in r["unsupported"]:
            log(f"  UNSUPPORTED  {x}")
        return 1 if r["unsupported"] else 0
    elif a.cmd == "capture":
        sbmod.build(project, quiet=True)
        cmd_capture(project, a.shots)
    elif a.cmd == "voice":
        voicemod.synthesize(project, a.provider, a.force)
        sbmod.build(project)
    elif a.cmd == "music":
        sbmod.build(project, quiet=True)
        for p in [a.platform] if a.platform else sbmod.platforms_of(cfg):
            node("frames.mjs", project, "--platform", p, "--info-only")
            node("music.mjs", project, "--platform", p)
    elif a.cmd == "captions":
        sbmod.build(project, quiet=True)
        for p in sbmod.platforms_of(cfg):
            log(f"{p}: {capmod.write_files(project, p)}")
    elif a.cmd == "stills":
        import themes
        themes.check_fonts(cfg["brief"])
        sbmod.build(project, quiet=True)
        p = a.platform or sbmod.platforms_of(cfg)[0]
        extra = ["--scenes"] if a.scenes else ["--every", a.every] if a.every else ["--at", a.at or "0.5"]
        node("stills.mjs", project, "--platform", p, *extra)
    elif a.cmd == "render":
        if a.t_from is None and a.t_to is None:
            gate_or_fail(project, "render")  # previews may run on a draft; full renders may not
        rendermod.render(project, a.platform.split(",") if a.platform else None, scale=a.scale, workers=a.workers,
                         t_from=a.t_from, t_to=a.t_to, fast=a.fast, use_voice=not a.no_voice, use_music=not a.no_music)
    elif a.cmd == "qa":
        reps = qamod.qa(project, a.platform.split(",") if a.platform else None, not a.no_lint, a.preview)
        return 1 if any(r["status"] == "FAIL" for r in reps) else 0
    elif a.cmd == "package":
        if not a.no_thumbnail and not a.no_gate:
            import thumbs
            te = thumbs.package_gate(project)
            if te:
                raise FishError("package: the thumbnail step is not done:\n  - " + "\n  - ".join(te))
        if brief_recipe(project) and not a.no_gate:
            import gates
            e = gates.signoff_errors(project)
            if e:
                raise FishError("package: the frame-sheet sign-off is not done:\n  - " + "\n  - ".join(e))
        ov = None if a.no_gate else qa_gate_or_override(project, a.accept_qa_fail)
        dest = pkgmod.package(project, Path(a.out) if a.out else None, a.name)
        if ov:
            (Path(dest) / "qa").mkdir(exist_ok=True)
            (Path(dest) / "qa" / "QA-OVERRIDE.md").write_text(f"# QA override\n\nPackaged with failing QA checks because: {ov}\n\n" + "\n".join("- " + e for e in qa_fail_errors(project)) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    main_guard(cli)
