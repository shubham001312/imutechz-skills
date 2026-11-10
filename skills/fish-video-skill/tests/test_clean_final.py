"""fishvideo clean --final-only keeps only the deliverable (out/) and refuses without a video and credits."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import clean  # noqa: E402


def _project(tmp_path: Path, with_credits=True) -> Path:
    p = tmp_path / "proj"
    for d in ("build/frames", "assets/photos", "research", "reference", "out/video", "out/metadata", "out/thumbnails"):
        (p / d).mkdir(parents=True)
    (p / "brief.yaml").write_text("title: t\n")
    (p / "storyboard.yaml").write_text("scenes: []\n")
    (p / "build/frames/f.png").write_bytes(b"x" * 1000)
    (p / "assets/photos/a.jpg").write_bytes(b"x" * 500)
    (p / "out/video/t-shorts.mp4").write_bytes(b"v" * 100)
    (p / "out/metadata/shorts-post.txt").write_text("post")
    (p / "out/thumbnails/thumbnail-1280x720.png").write_bytes(b"p")
    if with_credits:
        (p / "out/metadata/credits.txt").write_text("credits")
    return p


def test_final_only_dry_run_deletes_nothing(tmp_path):
    p = _project(tmp_path)
    r = clean.clean(p, yes=False, final_only=True)
    assert r["deleted"] == [] and (p / "build").exists() and (p / "assets").exists()


def test_final_only_keeps_only_out_and_copies_sources(tmp_path):
    p = _project(tmp_path)
    r = clean.clean(p, yes=True, final_only=True)
    assert sorted(x.name for x in p.iterdir()) == ["cleaned.json", "out"]
    assert (p / "out/video/t-shorts.mp4").exists() and (p / "out/metadata/shorts-post.txt").exists()
    assert (p / "out/metadata/source/brief.yaml").exists() and (p / "out/metadata/source/storyboard.yaml").exists()
    assert r["mode"] == "final-only" and "build" in r["deleted"] and "assets" in r["deleted"]


def test_final_only_refuses_without_credits(tmp_path):
    p = _project(tmp_path, with_credits=False)
    r = clean.clean(p, yes=True, final_only=True)
    assert r["deleted"] == [] and (p / "assets").exists()
