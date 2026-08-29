"""설정 창(AppKit)을 실제로 만들어 프리셋 클릭 → 미리보기 → 저장 경로를 돌려본다 (이벤트 루프 없이, 가짜 앱 객체로). macOS + pyobjc 에서만."""
import json
import sys
from datetime import datetime

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS AppKit 필요")
AppKit = pytest.importorskip("AppKit")

from mac import render as R, settings_model as M, title as T     # noqa: E402
from mac.settings import DEFAULT_SETTINGS, entry_key                # noqa: E402


class FakeApp:
    def __init__(self):
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.settings["entries"] = json.loads(json.dumps(M.SAMPLE_ENTRIES))
        self.settings["seen_providers"] = ["claude_code", "codex"]
        self.data = {}
        self.applied = []
        self.overflow = M.Overflow()

    def runs_for(self, S, entries, data, tier, cur, mode=None):
        vis = T.pick_visible(entries, mode or S["display_mode"], cur, S["fixed_entry"], entry_key)
        prefix = M.indicator_prefix(S["switch_indicator"], cur, len(entries)) if S["display_mode"] in ("click", "slide") else ""
        return T.build_runs(vis, data, entry_key, S["style"]["label"], S["show_scoped"], "AI —",
                            bars=T.want_bars(S["style"]["bars"]), tier=tier, prefix=prefix)

    def measure(self, runs):
        return R.width_of(runs)

    def available_width(self, S=None):
        return None

    def apply_settings(self, new, autostart=None):
        self.applied.append((new, autostart))
        self.settings = new

    def refresh_async(self, manual=False):
        return True

    def info_for(self, e):
        return {"connected": False, "reason": "", "plan": None, "expires_at": None, "unchecked": True}

    def toggle_statusline(self, path):
        pass

    def open_help(self):
        pass

    def open_folder(self, p):
        pass


class Sender:
    def __init__(self, tag):
        self._tag = tag

    def tag(self):
        return self._tag


@pytest.fixture
def ctl(monkeypatch):
    from mac import settings_window as SW
    monkeypatch.setattr(SW.launchagent, "is_enabled", lambda: False)
    AppKit.NSApplication.sharedApplication()
    app = FakeApp()
    c = SW.SettingsController.alloc().initWithApp_(app)
    c.show(install_mode=False, tab=1)
    yield c, app
    c.close(force=True)


def test_window_builds_with_five_tabs_and_preview(ctl):
    c, app = ctl
    assert c.window is not None and c.tabview.numberOfTabViewItems() == 5
    assert c.window.title().startswith("AI Status Bar")
    c.refresh_preview()
    assert c.preview.image() is not None and c.preview.image().size().width >= 120
    assert "pt" in c.preview_hint.stringValue()
    assert len(c.preset_cards) == 6 and len(c.rows) == 2


def test_preset_click_changes_form_and_preview_then_save_applies(ctl):
    c, app = ctl
    c.preset_(Sender(1))                                  # «미니멀» = 숫자만
    f = c.read_form()
    assert f["bars"] == "numbers" and f["display_mode"] == "all" and f["show_scoped"] is False
    c.refresh_preview()
    S = c.current_settings()
    assert M.preset_matches(S, dict(M.PRESETS)["minimal"])
    runs = app.runs_for(S, S["entries"], M.preview_data(S["entries"], {}), "full", 0)
    assert not any(isinstance(r[0], T.Bars) for r in runs)                     # 숫자만 → 막대 없음
    assert c.is_dirty()
    c.preset_(Sender(4))                                  # «슬라이드» = 라벨 on + auto 막대 + slide
    c.save_(None)
    assert app.applied and app.applied[-1][0]["display_mode"] == "slide" and app.applied[-1][0]["style"]["label"] is True
    assert app.applied[-1][1] is False                    # 자동 시작 체크박스 값이 함께 전달된다
    assert not c.is_dirty() and c.saved_label.stringValue() != ""
    assert c.window is not None                           # «저장» 은 창을 닫지 않는다


def test_row_ops_and_fixed_popup(ctl):
    c, app = ctl
    c.moveDown_(Sender(0))
    assert [r["label"] for r in c.rows] == ["home", "work"]
    assert c.c["fixed_entry"].numberOfItems() == 2
    c.removeRow_(Sender(1))
    assert [r["label"] for r in c.rows] == ["home"] and c.c["fixed_entry"].numberOfItems() == 1
    c.c["row_label_0"].setStringValue_("renamed")
    c.controlTextDidChange_(None)
    assert c.current_settings()["entries"][0]["label"] == "renamed"


def test_color_and_reset(ctl):
    c, app = ctl
    class Panel:
        def color(self):
            return R.color_from_hex("#ff8800")
    c.colorChanged_(Panel())
    assert c.current_settings()["style"]["label_color"] == "#ff8800"
    c.resetColor_(None)
    assert c.current_settings()["style"]["label_color"] == ""


def test_card_and_preview_images_render():
    e = M.SAMPLE_ENTRIES[0]
    d = M.preview_data([e], {})[entry_key(e)]
    d["last_ok"] = datetime.now()
    img = R.card_image(e, d, "Max (20x)", True, False, highlighted=True)
    assert img.size().width == R.CARD_W and img.size().height > 60
    err = R.card_image(e, {"usage": None, "error": "err_keychain_prompt"}, None, False, False)
    assert err.size().height > 40
