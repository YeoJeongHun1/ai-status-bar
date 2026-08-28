"""설정 파일: 마이그레이션(이전 이름 키)·범위 클램프·화이트리스트·원자적 저장."""
import json
import os

import pytest

import ai_status_bar as B


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(B, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(B, "OLD_SETTINGS_PATH", str(tmp_path / "old" / "settings.json"))
    return tmp_path


def test_defaults_when_no_file(cfg):
    s = B.load_settings()
    assert s["display_mode"] == "all" and s["placement"] == "left" and s["overflow_policy"] == "slide"
    assert s["entries"] == [] and s["data_source"] == "api"


def test_migrates_old_claude_status_bar_settings(cfg):
    old = cfg / "old"
    old.mkdir()
    (old / "settings.json").write_text(json.dumps({
        "accounts": [{"path": "C:/x/.claude", "label": "old-acc", "enabled": True}],
        "display_mode": "cycle", "cycle_on": True, "cycle_sec": 12, "show_5h": True, "show_7d": False,
        "language": "ja", "data_source": "api", "style": {"badge": True, "mark": True},
    }), encoding="utf-8")
    s = B.load_settings()
    assert len(s["entries"]) == 1 and s["entries"][0]["provider"] == "claude_code"
    assert s["entries"][0]["windows"] == {"5h": True, "7d": False}
    assert s["display_mode"] == "slide" and s["slide_sec"] == 12 and s["language"] == "ja"
    assert "badge" not in s["style"] and "mark" not in s["style"]


def test_clamps_and_whitelists(cfg):
    (cfg / "settings.json").write_text(json.dumps({
        "slide_sec": 99999, "display_mode": "bogus", "placement": "nope", "overflow_policy": "x",
        "switch_indicator": "y", "language": "zz", "data_source": "telepathy",
        "style": {"bars": "weird", "label_color": "red"},
        "entries": [{"provider": "unknown", "path": "p"}, {"provider": "codex", "path": "q"}],
    }), encoding="utf-8")
    s = B.load_settings()
    assert s["slide_sec"] == 3600
    assert s["display_mode"] == "all" and s["placement"] == "left" and s["overflow_policy"] == "slide"
    assert s["switch_indicator"] == "dots" and s["language"] == "auto" and s["data_source"] == "api"
    assert s["style"]["bars"] == "auto" and s["style"]["label_color"] == ""
    assert [e["provider"] for e in s["entries"]] == ["codex"]


def test_save_is_atomic_and_round_trips(cfg):
    s = B.load_settings()
    s["slide_sec"] = 45
    B.save_settings(s)
    assert not os.path.exists(B.SETTINGS_PATH + ".tmp")
    assert B.load_settings()["slide_sec"] == 45


def test_poll_sec_is_clamped_at_import():
    assert B.POLL_SEC >= 60


def test_enabled_entries_of_reads_only_the_given_settings():
    s = B.load_settings.__globals__["DEFAULT_SETTINGS"].copy()
    s = json.loads(json.dumps(s))
    s["entries"] = [
        {"provider": "claude_code", "path": "a", "label": "a", "enabled": True, "windows": {}},
        {"provider": "codex", "path": "b", "label": "b", "enabled": True, "windows": {}},
        {"provider": "codex", "path": "c", "label": "c", "enabled": False, "windows": {}},
    ]
    assert [e["path"] for e in B.enabled_entries_of(s)] == ["a", "b"]
    s["data_source"] = "official"
    assert [e["path"] for e in B.enabled_entries_of(s)] == ["a"]          # Codex 는 공식 데이터가 없어 숨김
