"""Clean a finished project: remove the intermediate ("garbage") files, keep the originals.

    fishvideo clean <dir>            dry run: list what would be deleted and what is kept, with sizes
    fishvideo clean <dir> --yes      delete (ONLY after the user approved the final video AND said yes to cleaning)
    fishvideo clean <dir> --yes --keep-voice   also keep the voice clip cache (cheap re-renders later)
    fishvideo clean <dir> --final-only [--yes]  keep ONLY the deliverable: out/ (video, thumbnail, covers, captions,
                                     post texts, titles, tags, transcript, credits, metadata.json) plus a copy of
                                     brief.yaml and storyboard.yaml in out/metadata/source/. Everything else goes:
                                     build/, assets/, research/, reference/, voice caches. The recommended clean
                                     once the user has approved the final video.

Deleted (regenerable):
  build/                  frames, per-platform intermediates, mixes, stills, captures' frame dumps
  reference/src.*         downloaded reference videos (analysis only) and their frame dumps
  reference/dissect*/     frame sheets of reference analysis
  assets/_candidates/     search previews that were never picked
  assets/_cache/          raw downloads before processing
  research/pages/         raw fetched page text (sources.json and facts.md are kept)
  *.tmp, __pycache__
Kept (originals):
  brief.yaml, storyboard.yaml, script.md, interview answers, approvals.json
  assets/ that the storyboard uses + assets/credits.json (licences)
  research/sources.json, research/facts.md, research/trends.md
  reference/report.md, reference/*analysis*.md (the notes, not the media)
  out/  (the deliverable)
Nothing is deleted without --yes. The skill must ask the user first.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from fvcore import ensure_project, log, main_guard, save_json

GARBAGE_DIRS = ["build", "assets/_candidates", "assets/_cache", "research/pages"]
GARBAGE_GLOBS = ["reference/src.*", "reference/dissect*", "reference/frames", "reference/sheets", "**/*.tmp", "**/__pycache__"]


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def plan_final(project: Path) -> tuple[list[Path], list[Path]]:
    """Everything except out/ (and the clean record) is removed."""
    keep_names = {"out", "cleaned.json"}
    victims = [p for p in project.iterdir() if p.name not in keep_names]
    return victims, [p for p in project.iterdir() if p.name in keep_names]


def plan(project: Path, keep_voice: bool = False) -> tuple[list[Path], list[Path]]:
    out = project / "out"
    victims: list[Path] = []
    for d in GARBAGE_DIRS:
        p = project / d
        if not p.exists():
            continue
        if d == "build" and keep_voice and (p / "voice").exists():
            victims += [c for c in p.iterdir() if c.name != "voice"]
        else:
            victims.append(p)
    for g in GARBAGE_GLOBS:
        for p in project.glob(g):
            if out in p.parents or p == out:
                continue
            if not any(v == p or v in p.parents for v in victims):
                victims.append(p)
    kept = [p for p in project.iterdir() if p not in victims]
    return victims, kept


def clean(project: Path, yes: bool = False, keep_voice: bool = False, final_only: bool = False) -> dict:
    project = ensure_project(project)
    out = project / "out"
    if not out.exists():
        log("!! no out/ folder yet: package the video before cleaning (nothing deleted)")
        return {"deleted": [], "freed_mb": 0}
    if final_only:
        videos = [f for f in out.rglob("*.mp4")]
        if not videos or not any(out.rglob("credits.txt")):
            log("!! out/ has no video or no credits.txt: run `fishvideo package` first; --final-only would lose the licences (nothing deleted)")
            return {"deleted": [], "freed_mb": 0}
        victims, kept = plan_final(project)
    else:
        victims, kept = plan(project, keep_voice)
    total = sum(_size(v) for v in victims)
    log(f"{'DELETING' if yes else 'would delete'} ({total / 1e6:.1f} MB):")
    for v in victims:
        log(f"  - {v.relative_to(project)}  {_size(v) / 1e6:.1f} MB")
    log("kept:")
    for k in sorted(kept):
        log(f"  + {k.relative_to(project)}")
    if not yes:
        log(f"\ndry run only. Ask the user; if they agree run: fishvideo clean <dir>{' --final-only' if final_only else ''} --yes")
        return {"deleted": [], "would_free_mb": round(total / 1e6, 1)}
    if final_only:                                   # the small source files travel with the deliverable
        src = out / "metadata" / "source"
        src.mkdir(parents=True, exist_ok=True)
        for name in ("brief.yaml", "storyboard.yaml"):
            if (project / name).exists():
                shutil.copy2(project / name, src / name)
    for v in victims:
        if v.is_dir():
            shutil.rmtree(v, ignore_errors=True)
        elif v.exists():
            v.unlink()
    rec = {"deleted": [str(v.relative_to(project)) for v in victims], "freed_mb": round(total / 1e6, 1), "mode": "final-only" if final_only else "intermediates"}
    save_json(project / "cleaned.json", rec)
    log(f"freed {total / 1e6:.1f} MB")
    return rec


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--keep-voice", action="store_true")
    ap.add_argument("--final-only", action="store_true", help="keep only out/ (the video, thumbnail, captions, post texts and metadata)")
    a = ap.parse_args(argv)
    clean(Path(a.project), a.yes, a.keep_voice, a.final_only)
    return 0


if __name__ == "__main__":
    main_guard(cli)
