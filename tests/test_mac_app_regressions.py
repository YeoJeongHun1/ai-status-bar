"""macOS 앱 회귀 — B4(메인 스레드 키체인 -w 0회) · B5(메뉴 토글 연타 → 조회 ≤ 1) · B6(메뉴 언어 전환 실제 반영). macOS + pyobjc 에서만."""
import json
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS AppKit 필요")
pytest.importorskip("AppKit")

import i18n                                                        # noqa: E402
import polling                                                     # noqa: E402
from providers import claude_code as cc                            # noqa: E402
from mac import app as A, launchagent, settings_window as SW      # noqa: E402
from mac.settings import DEFAULT_SETTINGS                          # noqa: E402

OAUTH = json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat01-x", "expiresAt": 4102444800000,
                                      "subscriptionType": "max", "rateLimitTier": "default_claude_max_20x"}})


def fake_security(calls, allow_w):
    def _sec(args, timeout):
        calls.append(list(args))
        if "-w" in args:
            assert allow_w, f"security -w called on the UI path: {args}"
            return type("R", (), {"returncode": 0, "stdout": OAUTH, "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    return _sec


@pytest.fixture
def app(monkeypatch, tmp_path):
    cfg = tmp_path / ".claude"
    cfg.mkdir()
    monkeypatch.setattr(cc, "IS_MAC", True)
    monkeypatch.setattr(cc, "DEFAULT_CONFIG_DIR", str(cfg))
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s["entries"] = [{"provider": "claude_code", "path": str(cfg), "label": "me", "enabled": True, "windows": {}}]
    s["seen_providers"] = ["claude_code", "codex"]
    monkeypatch.setattr(A, "load_settings", lambda: json.loads(json.dumps(s)))
    monkeypatch.setattr(A, "save_settings", lambda *_: None)
    monkeypatch.setattr(A, "ensure_discovered", lambda _s: False)
    monkeypatch.setattr(launchagent, "is_enabled", lambda: False)
    monkeypatch.setattr(launchagent, "enable", lambda **k: None)
    monkeypatch.setattr(launchagent, "disable", lambda **k: None)
    monkeypatch.setattr(SW.launchagent, "is_enabled", lambda: False)
    i18n.set_language("ko")
    a = A.MacStatusBar()
    a.settings["language"] = "ko"
    yield a
    a.slide_timer.stop() if a.slide_timer.is_alive() else None
    a.poll_timer.stop()


def wait_threads():
    for _ in range(100):
        if not any(th.name == "refresh" for th in threading.enumerate()):
            return
        time.sleep(0.02)


def test_b4_ui_paths_never_call_security_w(app, monkeypatch):
    calls = []
    monkeypatch.setattr(cc, "_security", fake_security(calls, allow_w=False))
    e = app.entries()[0]
    app.build_menu()                       # 메뉴(카드) 경로
    app.card_for(e)
    app.detail_lines(e)
    ctl = SW.SettingsController.alloc().initWithApp_(app)
    ctl.show(tab=0)
    ctl.fill_status()
    ctl.rebuild_rows()
    ctl.rescan_(None)                      # 다시 탐색은 존재 확인(-w 없음)만
    ctl.close(force=True)
    assert all("-w" not in c for c in calls)
    assert app.info_for(e).get("unchecked") is True
    # 폴링 스레드가 info 캐시를 채우면 UI 는 그것을 쓴다
    monkeypatch.setattr(cc, "_security", fake_security(calls, allow_w=True))
    monkeypatch.setattr(cc.http, "get_json", lambda *a, **k: {"five_hour": {"utilization": 5, "resets_at": None},
                                                             "seven_day": {"utilization": 50, "resets_at": None}})
    app._refresh()
    assert app.info_for(e)["plan"] == "Max (default_claude_max_20x)"
    assert app.data[A.entry_key(e)]["error"] is None
    calls.clear()
    monkeypatch.setattr(cc, "_security", fake_security(calls, allow_w=False))
    app.build_menu()
    ctl2 = SW.SettingsController.alloc().initWithApp_(app)
    ctl2.show(tab=2)
    assert "Max" in ctl2.status_label.stringValue()
    ctl2.close(force=True)
    assert all("-w" not in c for c in calls)


def test_b4_keychain_denied_backs_off(app, monkeypatch):
    def denied(args, timeout):
        if "-w" in args:
            return type("R", (), {"returncode": 128, "stdout": "", "stderr": "User canceled the operation."})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(cc, "_security", denied)
    e = app.entries()[0]
    app._refresh()
    k = A.entry_key(e)
    assert app.data[k]["error"] == "err_keychain_denied" and app.backoff.blocked(k)
    assert polling.Backoff().fail("x", "err_keychain_prompt") is True


def test_b5_menu_toggles_are_debounced(app, monkeypatch):
    n = [0]
    monkeypatch.setattr(A.polling, "run_refresh", lambda *a, **k: n.__setitem__(0, n[0] + 1))
    for _ in range(5):
        app.toggle("show_scoped")
        app.set_bars("numbers")
    wait_threads()
    assert n[0] <= 1
    assert app.poll_timer.interval is None            # run() 전엔 타이머가 돌지 않는다 — 설정 변경이 타이머를 살리지 않는다


def test_b6_menu_language_switch_takes_effect(app):
    assert i18n.current_language() == "ko"
    app.set_language("en")
    assert i18n.current_language() == "en" and app.settings["language"] == "en"
    assert any(getattr(v, "title", "") == "Refresh now" for v in app.menu.values())
    app.set_language("ko")
    assert i18n.current_language() == "ko"
    assert any(getattr(v, "title", "") == "지금 새로고침" for v in app.menu.values())
