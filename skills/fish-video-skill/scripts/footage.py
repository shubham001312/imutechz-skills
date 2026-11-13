"""fishvideo footage: a Short cut from REAL footage (news clips, launch videos, b-roll, screen recordings) with the house
fish.audio voice, logos and objects over the shots, synthesised SFX and a music bed; QA'd for motion; the insider cover.
Spec format and the full path: references/footage-shorts.md.

    fishvideo footage new <dir>                      spec.yaml from the template + assets/ build/ out/
    fishvideo footage yt search "<query>" [-n 6]     find footage;  fishvideo footage yt get <dir>/assets <id> ...
    fishvideo footage commons|nasa "<query>" [--video] [-n 12];  fishvideo footage get <url> <dest>
    fishvideo footage sheet <video> <out.jpg> [--step 2] [--cols 6] [--start S] [--end E]   pick in-points by looking
    fishvideo footage voice <dir> [--force] [--speed 1.1]    fish.audio narration + whisper word timings -> anchors
    fishvideo footage render <dir> [--preview]
    fishvideo footage qa <dir>                       length, motion per 0.5 s, loudness, transcript, frame sheet
    fishvideo footage thumb <dir>                    the insider cover (fishvideo thumbnail) -> out/thumbnail-*.png
    fishvideo footage package <dir> [--no-thumb]     thumbnail + titles, post, tags, pinned comment, sources
    fishvideo footage all <dir>                      voice, render, qa, package (stops on a QA FAIL)
    fishvideo footage sfx [--force]                  (re)build sfx/synth/
"""
import argparse, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fvcore import FishError, main_guard  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent


def cli(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="fishvideo footage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("dir"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("yt"); p.add_argument("action", choices=["search", "get"]); p.add_argument("args", nargs="+"); p.add_argument("-n", type=int, default=6)
    for c in ("commons", "nasa"):
        p = sub.add_parser(c); p.add_argument("query"); p.add_argument("--video", action="store_true"); p.add_argument("-n", type=int, default=12)
    p = sub.add_parser("get"); p.add_argument("url"); p.add_argument("dest")
    p = sub.add_parser("sheet"); p.add_argument("video"); p.add_argument("out"); p.add_argument("--step", type=float, default=2.0)
    p.add_argument("--cols", type=int, default=6); p.add_argument("--start", type=float, default=0.0); p.add_argument("--end", type=float, default=None)
    p = sub.add_parser("voice"); p.add_argument("dir"); p.add_argument("--force", action="store_true"); p.add_argument("--speed", default=None)
    p = sub.add_parser("render"); p.add_argument("dir"); p.add_argument("--preview", action="store_true")
    p = sub.add_parser("qa"); p.add_argument("dir")
    p = sub.add_parser("thumb"); p.add_argument("dir")
    p = sub.add_parser("package"); p.add_argument("dir"); p.add_argument("--no-thumb", action="store_true")
    p = sub.add_parser("all"); p.add_argument("dir"); p.add_argument("--force-voice", action="store_true")
    p = sub.add_parser("sfx"); p.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "new":
        d = Path(a.dir)
        if (d / "spec.yaml").exists() and not a.force:
            raise FishError(f"{d}/spec.yaml exists (use --force to overwrite)")
        for s in ("assets", "build", "out"):
            (d / s).mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILL / "templates/footage-spec.yaml", d / "spec.yaml")
        print(f"{d}/spec.yaml written: replace every TODO (references/footage-shorts.md)")
        return 0
    if a.cmd in ("yt", "commons", "nasa", "get", "sheet", "sfx"):
        import footage_tools as ft
        if a.cmd == "yt":
            if a.action == "search":
                ft.yt_search(" ".join(a.args), a.n)
            else:
                ft.yt_get(a.args[0], a.args[1:])
        elif a.cmd == "commons":
            ft.commons(a.query, a.video, a.n)
        elif a.cmd == "nasa":
            ft.nasa(a.query, a.video, a.n)
        elif a.cmd == "get":
            ft.download(a.url, a.dest)
        elif a.cmd == "sheet":
            ft.sheet(a.video, a.out, a.step, a.cols, a.start, a.end)
        else:
            print("\n".join(ft.synth_sfx(a.force)))
        return 0
    d = Path(a.dir)
    if not (d / "spec.yaml").exists():
        raise FishError(f"{d}/spec.yaml not found (fishvideo footage new {d})")
    if a.cmd == "voice":
        import footage_voice
        footage_voice.run(d, a.force, a.speed)
    elif a.cmd == "render":
        import footage_render
        footage_render.render(d, a.preview)
    elif a.cmd == "qa":
        import footage_qa
        return 0 if footage_qa.run(d) else 1
    elif a.cmd == "thumb":
        import footage_package
        footage_package.thumb(d)
    elif a.cmd == "package":
        import footage_package
        footage_package.run(d, not a.no_thumb)
    elif a.cmd == "all":
        import footage_voice, footage_render, footage_qa, footage_package
        footage_voice.run(d, a.force_voice)
        footage_render.render(d)
        if not footage_qa.run(d):
            raise FishError("QA FAIL (above): fix the spec and run `fishvideo footage render` + `qa` again")
        footage_package.run(d)
    return 0


if __name__ == "__main__":
    main_guard(cli)
