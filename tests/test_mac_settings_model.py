"""macOS 설정 창 로직(폼·프리셋·행 조작)과 넘침 상태 기계 — AppKit 없이."""
import json
import os
from datetime import datetime, timedelta

from mac import settings_model as M
from mac.settings import DEFAULT_SETTINGS, entry_key
from providers import get as get_provider


def S(**over):
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s.update(over)
    return s


def test_form_round_trip_and_whitelist():
    s = S(display_mode="slide", slide_sec=12, show_scoped=False, language="ja", data_source="official",
          entries=[{"provider": "claude_code", "path": "/a", "label": "A", "enabled": True, "windows": {"5h": True, "7d": False}}])
    s["style"] = {"label": True, "bars": "numbers", "label_color": "#ff8800"}
    s["fixed_entry"] = "claude_code|/a"
    form, rows = M.form_from_settings(s), M.rows_from_settings(s)
    out = M.form_to_settings(form, rows)
    for k in ("display_mode", "slide_sec", "show_scoped", "language", "data_source", "style", "fixed_entry"):
        assert out[k] == s[k], k
    assert out["entries"][0]["windows"] == {"5h": True, "7d": False}
    form.update(display_mode="bogus", bars="weird", label_color="red", slide_sec="abc", overflow_policy="x", max_width_pt=99999)
    out = M.form_to_settings(form, rows)
    assert out["display_mode"] == "all" and out["style"]["bars"] == "auto" and out["style"]["label_color"] == ""
    assert out["slide_sec"] == 30 and out["overflow_policy"] == "slide" and out["max_width_pt"] == 2000
    assert sorted(out["seen_providers"]) == ["claude_code", "codex"]


def test_empty_label_falls_back_to_provider_label_and_fixed_entry_is_validated():
    rows = [M.new_row("codex", "/x/.codex", "  ")]
    form = M.form_from_settings(S())
    form["fixed_entry"] = "missing|key"
    out = M.form_to_settings(form, rows)
    assert out["entries"][0]["label"] == get_provider("codex").label("/x/.codex")
    assert out["fixed_entry"] == "codex|/x/.codex"


def test_snapshot_tracks_autostart_and_form():
    rows = M.rows_from_settings(S())
    form = M.form_from_settings(S())
    a = M.snapshot(form, rows)
    form["autostart"] = True
    assert M.snapshot(form, rows) != a
    form["autostart"] = None
    assert M.snapshot(form, rows) == a


def test_presets_match_and_apply():
    form = M.form_from_settings(S())
    for key, values in M.PRESETS:
        M.apply_preset(form, values)
        out = M.form_to_settings(form, [])
        assert M.preset_matches(out, values), key
        assert sum(M.preset_matches(out, v) for _, v in M.PRESETS) == 1, key    # 프리셋은 서로 겹치지 않는다
    ps = M.preset_settings(dict(M.PRESETS)["pinned"])
    assert [e["label"] for e in ps["entries"]] == ["work", "home"] and ps["fixed_entry"] == entry_key(ps["entries"][0])


def test_preview_data_uses_real_values_when_present():
    ents = M.SAMPLE_ENTRIES
    real = {entry_key(ents[0]): {"usage": {"windows": [{"key": "5h", "pct": 1.0, "resets_at": None}], "scoped": []}}}
    d = M.preview_data(ents, real, now=datetime(2026, 1, 1, 12, 0, 0))
    assert d[entry_key(ents[0])]["usage"]["windows"][0]["pct"] == 1.0
    assert [w["pct"] for w in d[entry_key(ents[1])]["usage"]["windows"]] == [18.0, 33.0]     # 예시값


def test_row_ops(tmp_path):
    rows = [M.new_row("claude_code", "/a", "a"), M.new_row("codex", "/b", "b")]
    assert M.move_row(rows, 0, 1) == 1 and [r["path"] for r in rows] == ["/b", "/a"]
    assert M.move_row(rows, 0, -1) == 0                                   # 범위 밖이면 그대로
    p = get_provider("codex")
    assert M.add_folder(rows, p, "/b/") == ("dup", None)
    st, row = M.add_folder(rows, p, str(tmp_path))
    assert st == "nocred" and row["path"] == str(tmp_path) and len(rows) == 2   # 확인 전엔 붙이지 않는다
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")
    st, row = M.add_folder(rows, p, str(tmp_path))
    assert st == "ok" and rows[-1] is row


def test_rescan_adds_only_new(monkeypatch):
    class P:
        id, cred_file = "codex", "auth.json"
        def discover(self): return ["/new", "/b"]
        def label(self, d): return os.path.basename(d)
    rows = [M.new_row("codex", "/b", "b")]
    assert M.rescan(rows, [P()]) == 1 and rows[-1]["path"] == "/new"


def test_indicator_prefix():
    assert M.indicator_prefix("dots", 1, 3) == "○●○ "
    assert M.indicator_prefix("arrow", 0, 2) == "⇄ "
    assert M.indicator_prefix("none", 0, 2) == "" and M.indicator_prefix("dots", 0, 1) == ""


def test_tiers_follow_bars_style():
    assert M.tiers("auto") == ("full", "compact", "collapsed")
    assert M.tiers("bars") == ("full", "collapsed") and M.tiers("numbers") == ("compact", "collapsed")


def test_overflow_policy_hysteresis_and_notify_gap():
    widths = {"full": 300, "compact": 180, "collapsed": 20}
    ov = M.Overflow()
    s = S(overflow_policy="slide"); s["style"]["bars"] = "auto"
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    assert ov.decide(widths.get, None, s, 2, t0) == ("full", None, False)             # 폭을 모르면 조절 없음
    assert ov.decide(widths.get, 400, s, 2, t0) == ("full", None, False)
    assert ov.decide(widths.get, 200, s, 2, t0) == ("compact", None, False)           # 막대 → 숫자만 (정책 전 단계)
    assert ov.decide(widths.get, 100, s, 2, t0) == ("compact", "slide", True)         # 정책: 한 항목씩 슬라이드 + 알림
    assert ov.decide(widths.get, 100, s, 2, t0 + timedelta(seconds=5)) == ("compact", "slide", False)
    assert ov.decide(widths.get, 310, s, 2, t0) == ("compact", None, False)           # 여유 40 미만이면 복귀 안 함
    assert ov.decide(widths.get, 340, s, 2, t0) == ("full", None, False)              # 여유 40 이상 → 복귀
    assert ov.decide(widths.get, 100, s, 2, t0 + timedelta(minutes=5)) == ("compact", "slide", False)   # 10분 안 → 알림 없음
    ov2 = M.Overflow()
    s2 = S(overflow_policy="collapse")
    assert ov2.decide(widths.get, 100, s2, 2, t0) == ("collapsed", "collapse", True)
    assert ov2.decide(widths.get, 100, s2, 2, t0 + timedelta(minutes=11)) == ("collapsed", "collapse", False)
    ov3 = M.Overflow()
    s3 = S(overflow_policy="slide")
    assert ov3.decide(widths.get, 100, s3, 1, t0) == ("compact", "numbers", True)     # 항목 하나면 슬라이드 → 숫자만
    s4 = S(overflow_policy="numbers"); s4["style"]["bars"] = "bars"
    assert M.Overflow().decide(widths.get, 100, s4, 2, t0) == ("full", "numbers", True)   # bars 스타일엔 compact 단계가 없다


def test_clip_runs():
    runs = [("5h ", None), ("23%", 23), (" · 7d ", None), ("66%", 66)]
    w = lambda rs: sum(len(t) * 7 for t, _ in rs)
    assert M.clip_runs(runs, w, 1000) == runs
    out = M.clip_runs(runs, w, 60)
    assert out[-1] == ("…", None) and w(out) <= 60 and out[0] == runs[0]
    assert M.clip_runs(runs, w, 1) == [runs[0], ("…", None)]
