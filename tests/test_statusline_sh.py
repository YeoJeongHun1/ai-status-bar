"""statusline_export.sh (macOS/zsh): 필드 선별(사용량만 저장)·PID 임시파일·원래 명령 파이프(보간 없음). 실제 zsh 로 실행한다."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from providers import claude_code as cc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "statusline_export.sh")
SAMPLE = {
    "model": {"id": "claude-x", "display_name": "Fable 5"},
    "cwd": "/Users/someone/secret-project", "transcript_path": "/Users/someone/.claude/t.jsonl",
    "session_id": "sess-123", "workspace": {"current_dir": "/Users/someone/secret-project"},
    "cost": {"total_cost_usd": 1.23},
    "rate_limits": {"five_hour": {"used_percentage": 32.4, "resets_at": 1790000000},
                    "seven_day": {"used_percentage": 68, "resets_at": 1790400000}},
}

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("zsh"), reason="zsh 필요 (macOS/Linux)")


def run_sh(tmp_home, stdin_json, config_dir):
    env = dict(os.environ, HOME=str(tmp_home), CLAUDE_CONFIG_DIR=config_dir, PATH=os.path.dirname(sys.executable) + ":" + os.environ.get("PATH", ""))
    return subprocess.run(["/bin/zsh", SH], input=stdin_json, capture_output=True, text=True, env=env, timeout=60)


def out_dir_of(tmp_home):
    return tmp_home / "Library" / "Application Support" / "AIStatusBar" / "official"


def test_sh_saves_only_usage_fields(tmp_path, monkeypatch):
    cfg = str(tmp_path / "claude-cfg")
    os.makedirs(cfg)
    r = run_sh(tmp_path, json.dumps(SAMPLE), cfg)
    assert r.returncode == 0, r.stderr
    out_dir = out_dir_of(tmp_path)
    files = sorted(os.listdir(out_dir))
    assert files == [cc.official_key(cfg) + ".json"], files            # PID 임시파일은 남지 않는다
    saved = json.loads((out_dir / files[0]).read_text(encoding="utf-8"))
    assert set(saved) == {"saved_at", "model", "rate_limits"}
    assert saved["model"] == "Fable 5"
    assert saved["rate_limits"]["five_hour"] == {"used_percentage": 32.4, "resets_at": 1790000000}
    text = json.dumps(saved)
    for leaked in ("secret-project", "transcript", "sess-123", "cost", "cwd"):
        assert leaked not in text
    assert r.stdout.strip() == "Fable 5 | 5h 32% | 7d 68%"
    monkeypatch.setattr(cc, "OFFICIAL_DIR", str(out_dir))
    usage, saved_at = cc.read_official(cfg)
    assert [(w["key"], w["pct"]) for w in usage["windows"]] == [("5h", 32.4), ("7d", 68.0)]


def test_sh_key_matches_python_for_trailing_slash_and_dotdot(tmp_path):
    base = tmp_path / "claude-cfg"
    base.mkdir()
    cfg = str(tmp_path / "other" / ".." / "claude-cfg") + "/"
    (tmp_path / "other").mkdir()
    r = run_sh(tmp_path, json.dumps(SAMPLE), cfg)
    assert r.returncode == 0, r.stderr
    assert os.listdir(out_dir_of(tmp_path)) == [cc.official_key(cfg) + ".json"]


def test_sh_pipes_to_original_command_without_interpolation(tmp_path):
    cfg = str(tmp_path / "claude-cfg")
    os.makedirs(cfg)
    out_dir = out_dir_of(tmp_path)
    out_dir.mkdir(parents=True)
    marker = tmp_path / "marker.txt"
    # $notavar 는 이 스크립트가 풀지 않는다 (sh 가 푸는 건 원래 동작이라, sh 에서도 안 풀리게 작은따옴표로 감싼 명령)
    orig_cmd = f"grep -c rate_limits > '{marker}'; echo 'ORIGINAL-OK $notavar'"
    (out_dir / (cc.official_key(cfg) + ".original.json")).write_text(
        json.dumps({"original_statusLine": {"type": "command", "command": orig_cmd}}), encoding="utf-8")
    r = run_sh(tmp_path, json.dumps(SAMPLE), cfg)
    assert r.returncode == 0, r.stderr
    assert "ORIGINAL-OK $notavar" in r.stdout
    assert marker.exists() and marker.read_text().strip() == "1"     # stdin JSON 이 원래 명령으로 넘어갔다
    assert sorted(os.listdir(out_dir)) == sorted([cc.official_key(cfg) + ".json", cc.official_key(cfg) + ".original.json"])


def test_sh_empty_stdin_writes_nothing(tmp_path):
    cfg = str(tmp_path / "claude-cfg")
    os.makedirs(cfg)
    r = run_sh(tmp_path, "", cfg)
    assert r.returncode == 0 and r.stdout == ""
    assert not out_dir_of(tmp_path).exists()


def test_install_and_uninstall_with_sh(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    out_dir = tmp_path / "official"
    monkeypatch.setattr(cc, "OFFICIAL_DIR", str(out_dir))
    (cfg / "settings.json").write_text(json.dumps({"statusLine": {"type": "command", "command": "bash $HOME/.claude/statusline-command.sh"}, "other": 1}), encoding="utf-8")
    cc.statusline_install(str(cfg), SH)
    assert cc.statusline_installed(str(cfg))
    sl = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))["statusLine"]
    assert sl == {"type": "command", "command": f'/bin/zsh "{SH}"'}
    assert (cfg / "settings.json.bak-aistatusbar").exists()
    cc.statusline_uninstall(str(cfg))
    restored = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
    assert restored["statusLine"]["command"] == "bash $HOME/.claude/statusline-command.sh" and restored["other"] == 1
    assert not os.listdir(out_dir)
