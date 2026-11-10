"""`assets github` and `assets terminal`. The HTTP layer is mocked; one network-marked test hits the real GitHub."""
import hashlib
import io

import pytest
import yaml
from PIL import Image

import assets
import fvnet
from fvcore import FishError, load_json
from test_tools import mock_urlopen


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "brief.yaml").write_text("title: t\n", encoding="utf-8")
    return tmp_path


def png_bytes():
    b = io.BytesIO()
    Image.new("RGB", (12, 6), "#123456").save(b, "PNG")
    return b.getvalue()


REPO = {"full_name": "acme/widget", "description": "A widget", "stargazers_count": 48213, "forks_count": 1204, "license": {"spdx_id": "MIT"},
        "homepage": "https://acme.dev", "pushed_at": "2026-11-01T00:00:00Z", "topics": ["cli"], "html_url": "https://github.com/acme/widget"}


def test_terminal_size_and_deterministic(proj):
    seq = [("cmd", "ollama run llama3"), ("out", "hello")]
    a = assets.render_terminal(seq)
    assert a.size == (1600, 1000)
    assert assets.render_terminal(seq, scale=2).size == (3200, 2000)
    h = lambda im: hashlib.sha256(im.tobytes()).hexdigest()
    assert h(a) == h(assets.render_terminal(seq)) != h(assets.render_terminal([("cmd", "other")]))
    p1 = assets.terminal(proj, ["x"], ["y"], out="t1")
    p2 = assets.terminal(proj, ["x"], ["y"], out="t2")
    assert p1.read_bytes() == p2.read_bytes()                      # same input, same file bytes


def test_terminal_credit_marks_output_illustrative_and_commands_only_not(proj):
    assets.terminal(proj, ["git status"], ["clean"], out="with-out")
    assets.terminal(proj, ["git status"], None, out="cmd-only")
    by = {c["id"]: c for c in load_json(proj / "assets" / "credits.json")}
    assert by["terminal-with-out"]["label"] == "illustrative" and "output written by the author" in by["terminal-with-out"]["license"]
    assert by["terminal-with-out"]["url"] == "made locally"
    assert "label" not in by["terminal-cmd-only"]


def test_terminal_from_file_and_long_lines_and_errors(proj, tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("$ npm i foo\nadded 1 package\n$ foo --help\n" + "x" * 400 + "\n", encoding="utf-8")
    assert assets.terminal_lines(from_file=f)[:2] == [("cmd", "npm i foo"), ("out", "added 1 package")]
    assert assets.terminal(proj, from_file=f, out="ff").exists()
    with pytest.raises(FishError):
        assets.terminal_lines()


def test_terminal_points_beat_at_card(proj):
    (proj / "storyboard.yaml").write_text(yaml.safe_dump({"scenes": [{"id": "b1", "type": "image", "params": {}}]}), encoding="utf-8")
    assets.terminal(proj, ["ls"], ["a"], out="card", beat="b1")
    p = yaml.safe_load((proj / "storyboard.yaml").read_text())["scenes"][0]["params"]
    assert p["src"] == "assets/own/card.png" and p["label"] == "illustrative"


def test_github_command_mocked(monkeypatch, proj, capsys):
    seen = []
    mock_urlopen(monkeypatch, {"api.github.com/repos/acme/widget": REPO, "opengraph.githubassets.com/1/acme/widget": png_bytes()}, seen)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SECRETVALUE")
    (proj / "storyboard.yaml").write_text(yaml.safe_dump({"scenes": [{"id": "b1", "type": "image", "params": {}}]}), encoding="utf-8")
    m = assets.github(proj, "acme/widget", beat="b1", today="2026-11-10")
    assert (proj / "assets/github/acme-widget-card.png").exists() and m["stars"] == 48213 and m["license"] == "MIT"
    out = capsys.readouterr().out
    assert "ghp_SECRETVALUE" not in out and "48213" in out
    assert any("Bearer ghp_SECRETVALUE" in str(h.get("Authorization", "")) for _, h, _ in seen)
    brief = yaml.safe_load((proj / "brief.yaml").read_text())
    assert {"text": "acme/widget has 48,213 GitHub stars (as of 2026-11-10)", "value": "48,213", "source": "https://github.com/acme/widget"} in brief["facts"]
    c = next(x for x in load_json(proj / "assets/credits.json") if x["provider"] == "screenshot")
    assert (c["author"], c["risk"], c["url"]) == ("acme", "platform", "https://github.com/acme/widget") and "editorial" in c["license"]
    assert yaml.safe_load((proj / "storyboard.yaml").read_text())["scenes"][0]["params"]["src"] == "assets/github/acme-widget-card.png"
    assets.github(proj, "acme/widget", today="2026-11-11")         # again: facts are replaced, not piled up
    assert sum("stars" in f["text"] for f in yaml.safe_load((proj / "brief.yaml").read_text())["facts"]) == 1


def test_github_rejects_bad_repo_and_api_failure(monkeypatch, proj):
    with pytest.raises(FishError):
        assets.github(proj, "not a repo")
    mock_urlopen(monkeypatch, {})
    with pytest.raises(fvnet.NetError):
        assets.github(proj, "acme/widget")


@pytest.mark.network
def test_github_live_ollama(proj):
    m = assets.github(proj, "ollama/ollama")
    assert m["stars"] > 1000 and m["license"] == "MIT"
    with Image.open(proj / m["card"]) as im:
        assert im.size[0] >= 600


def test_find_brand_does_not_turn_openai_into_openai_gym():
    import icons
    data = [{"slug": "openaigym", "title": "OpenAI Gym"}, {"slug": "nodedotjs", "title": "Node.js", "aliases": {"aka": ["node"]}}, {"slug": "vuedotjs", "title": "Vue.js"}]
    assert icons.find_brand("openai", data) is None
    assert icons.find_brand("vue", data)["slug"] == "vuedotjs"
    assert icons.find_brand("node", data)["slug"] == "nodedotjs"
