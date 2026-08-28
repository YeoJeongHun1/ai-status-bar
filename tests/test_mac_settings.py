"""macOS settings.json — Windows 와 같은 스키마·화이트리스트·원자적 저장 (tkinter 없이)."""
import json
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="macOS 패키지 (Windows 는 tests/test_settings.py)")

from mac import settings as S     # noqa: E402


def test_defaults_when_no_file(tmp_path):
    s = S.load_settings(str(tmp_path / "none.json"))
    assert s["display_mode"] == "all" and s["entries"] == [] and s["data_source"] == "api"


def test_clamps_and_whitelists(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "slide_sec": 99999, "display_mode": "bogus", "language": "zz", "data_source": "telepathy",
        "style": {"bars": "weird", "label_color": "red", "label": 1},
        "entries": [{"provider": "unknown", "path": "p"}, {"provider": "codex", "path": "q", "label": "L"}],
    }), encoding="utf-8")
    s = S.load_settings(str(p))
    assert s["slide_sec"] == 3600 and s["display_mode"] == "all" and s["language"] == "auto" and s["data_source"] == "api"
    assert s["style"] == {"label": True, "bars": "auto", "label_color": ""}
    assert [(e["provider"], e["label"]) for e in s["entries"]] == [("codex", "L")]


def test_windows_settings_file_is_readable(tmp_path):
    """Windows 판이 저장한 파일 그대로."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "entries": [{"provider": "claude_code", "path": "C:\\Users\\me\\.claude", "label": "me", "enabled": True,
                     "windows": {"5h": True, "7d": False}}],
        "display_mode": "slide", "slide_sec": 12, "fixed_entry": "", "show_scoped": False,
        "style": {"label": True, "bars": "bars", "label_color": "#ff8800"}, "placement": "auto",
        "overflow_policy": "numbers", "switch_indicator": "arrow", "language": "ja", "data_source": "official",
        "official_hide_unsupported": False, "seen_providers": ["claude_code", "codex"],
    }), encoding="utf-8")
    s = S.load_settings(str(p))
    assert s["display_mode"] == "slide" and s["slide_sec"] == 12 and s["language"] == "ja"
    assert s["entries"][0]["windows"] == {"5h": True, "7d": False}
    assert s["placement"] == "auto" and s["overflow_policy"] == "numbers" and s["switch_indicator"] == "arrow"
    assert s["data_source"] == "official" and s["official_hide_unsupported"] is False
    assert [e["path"] for e in S.enabled_entries_of(s)] == ["C:\\Users\\me\\.claude"]


def test_save_is_atomic_and_round_trips(tmp_path):
    p = str(tmp_path / "sub" / "settings.json")
    s = S.load_settings(p)
    s["slide_sec"] = 45
    S.save_settings(s, p)
    assert not os.path.exists(p + ".tmp")
    assert S.load_settings(p)["slide_sec"] == 45


def test_enabled_entries_hide_codex_in_official_mode():
    s = json.loads(json.dumps(S.DEFAULT_SETTINGS))
    s["entries"] = [
        {"provider": "claude_code", "path": "a", "label": "a", "enabled": True, "windows": {}},
        {"provider": "codex", "path": "b", "label": "b", "enabled": True, "windows": {}},
        {"provider": "codex", "path": "c", "label": "c", "enabled": False, "windows": {}},
    ]
    assert [e["path"] for e in S.enabled_entries_of(s)] == ["a", "b"]
    s["data_source"] = "official"
    assert [e["path"] for e in S.enabled_entries_of(s)] == ["a"]


def test_ensure_discovered_runs_once_per_provider(monkeypatch):
    s = json.loads(json.dumps(S.DEFAULT_SETTINGS))
    monkeypatch.setattr(S, "merge_discovered", lambda entries, providers=None: 0)
    assert S.ensure_discovered(s) is True
    assert sorted(s["seen_providers"]) == ["claude_code", "codex"]
    assert S.ensure_discovered(s) is False
