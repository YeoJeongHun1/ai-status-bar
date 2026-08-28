"""statusline_export.ps1: 필드 선별(사용량만 저장)·PID 임시파일·원래 명령 파이프. Windows PowerShell 로 실제 실행한다."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from providers import claude_code as cc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, "statusline_export.ps1")
SAMPLE = {
    "model": {"id": "claude-x", "display_name": "Fable 5"},
    "cwd": "C:\\Users\\someone\\secret-project", "transcript_path": "C:\\Users\\someone\\.claude\\t.jsonl",
    "session_id": "sess-123", "workspace": {"current_dir": "C:\\Users\\someone\\secret-project"},
    "cost": {"total_cost_usd": 1.23},
    "rate_limits": {"five_hour": {"used_percentage": 32.4, "resets_at": 1790000000},
                    "seven_day": {"used_percentage": 68, "resets_at": 1790400000}},
}

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell 필요")


def run_ps1(tmp_path, monkeypatch, stdin_json, config_dir):
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), CLAUDE_CONFIG_DIR=config_dir)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1],
                       input=stdin_json, capture_output=True, text=True, env=env, timeout=60)
    return r


def test_ps1_saves_only_usage_fields(tmp_path, monkeypatch):
    cfg = str(tmp_path / "claude-cfg")
    os.makedirs(cfg)
    r = run_ps1(tmp_path, monkeypatch, json.dumps(SAMPLE), cfg)
    assert r.returncode == 0, r.stderr
    out_dir = tmp_path / "AIStatusBar" / "official"
    files = sorted(os.listdir(out_dir))
    assert files == [cc.official_key(cfg) + ".json"], files            # PID 임시파일은 남지 않는다
    saved = json.loads((out_dir / files[0]).read_text(encoding="utf-8"))
    assert set(saved) == {"saved_at", "model", "rate_limits"}
    assert saved["model"] == "Fable 5"
    assert saved["rate_limits"]["five_hour"] == {"used_percentage": 32.4, "resets_at": 1790000000}
    text = json.dumps(saved)
    for leaked in ("secret-project", "transcript", "sess-123", "cost", "cwd"):
        assert leaked not in text
    assert r.stdout.strip() == "Fable 5 | 5h 32% | 7d 68%"            # 원래 명령이 없으면 한 줄
    # 앱 쪽 read_official 이 그 파일을 읽는다
    monkeypatch.setattr(cc, "OFFICIAL_DIR", str(out_dir))
    usage, saved_at = cc.read_official(cfg)
    assert [(w["key"], w["pct"]) for w in usage["windows"]] == [("5h", 32.4), ("7d", 68.0)]


def test_ps1_pipes_to_original_command_without_interpolation(tmp_path, monkeypatch):
    cfg = str(tmp_path / "claude-cfg")
    os.makedirs(cfg)
    out_dir = tmp_path / "AIStatusBar" / "official"
    out_dir.mkdir(parents=True)
    # 원래 명령에 $var 와 %VAR% 가 섞여 있어도 이 스크립트가 보간하지 않는다 (cmd 가 %VAR% 를 푸는 건 원래 동작)
    marker = tmp_path / "marker.txt"
    orig_cmd = f'findstr /c:"rate_limits" > "{marker}" & echo ORIGINAL-OK $notavar'
    (out_dir / (cc.official_key(cfg) + ".original.json")).write_text(
        json.dumps({"original_statusLine": {"type": "command", "command": orig_cmd}}), encoding="utf-8")
    r = run_ps1(tmp_path, monkeypatch, json.dumps(SAMPLE), cfg)
    assert r.returncode == 0, r.stderr
    assert "ORIGINAL-OK $notavar" in r.stdout                          # $notavar 가 PowerShell 에서 풀리지 않았다
    assert marker.exists() and "rate_limits" in marker.read_text()   # stdin JSON 이 원래 명령으로 넘어갔다


def test_uninstall_removes_export_file(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    out_dir = tmp_path / "official"
    monkeypatch.setattr(cc, "OFFICIAL_DIR", str(out_dir))
    (cfg / "settings.json").write_text(json.dumps({"statusLine": {"type": "command", "command": "echo old"}, "other": 1}), encoding="utf-8")
    cc.statusline_install(str(cfg), "C:/app/statusline_export.ps1")
    assert cc.statusline_installed(str(cfg))
    (out_dir / (cc.official_key(str(cfg)) + ".json")).write_text("{}", encoding="utf-8")
    cc.statusline_uninstall(str(cfg))
    restored = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
    assert restored["statusLine"] == {"type": "command", "command": "echo old"} and restored["other"] == 1
    assert not os.listdir(out_dir)                                     # 보관본 + export 파일 모두 삭제
