"""
설정 창 — 네이티브 AppKit (NSWindow + NSTabView 5탭). Windows 판 설정 창과 같은 항목·같은 동작:
상단 라이브 미리보기 / 항목 · 표시·스타일(프리셋 카드 6종) · 데이터 · 시작·언어 · 정보 / «저장» 은 적용하고 창 유지(«저장됨 ✓»),
저장 안 하고 닫으면 저장/버리기/취소. 로직은 settings_model.py (순수), 여기는 뷰·이벤트만.
"""
import os
import webbrowser

import objc
try:
    import Quartz  # noqa: F401  — CGColorRef 타입 등록 (없어도 동작, 경고만)
except Exception:
    pass
import rumps
from AppKit import (NSApp, NSBackingStoreBuffered, NSButton, NSColor, NSColorPanel, NSFont, NSImageView, NSOpenPanel,
                    NSPopUpButton, NSScrollView, NSTabView, NSTabViewItem, NSTextField, NSView, NSWindow)
from Foundation import NSMakeRect, NSObject
from PyObjCTools import AppHelper

import applog
from i18n import LANG_NAMES, SUPPORTED, t, tr_error
from providers import claude_code as cc, get as get_provider
from version import __version__

from . import launchagent, render as R, settings_model as M, title as T
from .paths import APP_TITLE, LOG_DIR, README_URL, RELEASES_URL, ROOT_DIR, SUPPORT_URL
from .settings import BAR_STYLES, INDICATORS, MODES, OVERFLOW_POLICIES, PLACEMENTS, PROVIDERS, entry_key

W, H = 780, 640
CONTENT_W = W - 2 * 18
TAB_W = W - 2 * 14
DOC_W = TAB_W - 28
SWITCH, RADIO, PUSH = 3, 4, 7           # NSButtonType
ROUNDED = 1                             # NSBezelStyle


class FlippedView(NSView):
    def isFlipped(self):
        return True


# ---------- 작은 위젯 도우미 ----------

def label(text, x, y, w, size=12, bold=False, color=None, wrap=True):
    tf = NSTextField.wrappingLabelWithString_(text) if wrap else NSTextField.labelWithString_(text)
    tf.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if color is not None:
        tf.setTextColor_(color)
    tf.setSelectable_(False)
    h = tf.cell().cellSizeForBounds_(NSMakeRect(0, 0, w, 100000)).height if wrap else tf.intrinsicContentSize().height
    tf.setFrame_(NSMakeRect(x, y, w, h))
    return tf, h


def button(title, x, y, w, target, action, tag=0, kind=PUSH, h=24):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setButtonType_(kind)
    if kind == PUSH:
        b.setBezelStyle_(ROUNDED)
    b.setTitle_(title)
    b.setTarget_(target)
    b.setAction_(action)
    b.setTag_(tag)
    return b


def link(title, x, y, w, target, action, tag):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 20))
    b.setBordered_(False)
    b.setButtonType_(7)
    from AppKit import NSAttributedString, NSFontAttributeName, NSForegroundColorAttributeName
    b.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
        title, {NSFontAttributeName: NSFont.systemFontOfSize_(12), NSForegroundColorAttributeName: NSColor.linkColor()}))
    b.setAlignment_(0)
    b.setTarget_(target)
    b.setAction_(action)
    b.setTag_(tag)
    return b


def popup(x, y, w, titles, selected, target, action, tag=0):
    p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(x, y, w, 26), False)
    p.addItemsWithTitles_(titles)
    p.selectItemAtIndex_(max(0, selected))
    p.setTarget_(target)
    p.setAction_(action)
    p.setTag_(tag)
    return p


def field(x, y, w, value, target, tag=0):
    f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, 22))
    f.setStringValue_(str(value))
    f.setDelegate_(target)
    f.setTag_(tag)
    return f


def scroll_tab(tabview, key, content_h):
    """탭 하나 = 스크롤 뷰 + flipped 문서 뷰. 문서 뷰를 돌려준다 (실제 높이는 나중에 fit_doc 로 맞춘다)."""
    item = NSTabViewItem.alloc().initWithIdentifier_(key)
    item.setLabel_(t(key))
    sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, TAB_W, 100))
    sv.setHasVerticalScroller_(True)
    sv.setBorderType_(0)
    sv.setDrawsBackground_(False)
    doc = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, DOC_W + 8, content_h))
    sv.setDocumentView_(doc)
    item.setView_(sv)
    tabview.addTabViewItem_(item)
    return doc


def fit_doc(doc, h):
    doc.setFrame_(NSMakeRect(0, 0, doc.frame().size.width, max(h + 12, 100)))


def section(doc, key, y, hint=None):
    tf, h = label(t(key).strip(), 14, y, DOC_W - 28, 12, bold=True)
    doc.addSubview_(tf)
    y += h + 2
    line = NSView.alloc().initWithFrame_(NSMakeRect(14, y, DOC_W - 28, 1))
    line.setWantsLayer_(True)
    line.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
    doc.addSubview_(line)
    y += 6
    if hint:
        tf, h = label(t(hint), 14, y, DOC_W - 28, 10, color=NSColor.secondaryLabelColor())
        doc.addSubview_(tf)
        y += h + 8
    return y


class SettingsController(NSObject):
    """창 하나. app 은 MacStatusBar — settings / data / runs_for / measure / apply_settings / refresh_async / toggle_statusline / open_help."""

    def initWithApp_(self, app):
        self = objc.super(SettingsController, self).init()
        self.app = app
        self.window = None
        self.install_mode = False
        self.form = None
        self.rows = []
        self.c = {}
        self.radio = {}
        self.preset_cards = []
        self._baseline = ""
        self._preview_job = False
        return self

    # ---------- 열기 / 닫기 ----------
    def show(self, install_mode=False, tab=0):
        if self.window is not None:
            self.window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            try:
                self.tabview.selectTabViewItemAtIndex_(tab)
            except Exception:
                pass
            return
        self.install_mode = install_mode
        self.form = M.form_from_settings(self.app.settings)
        self.form["autostart"] = True if install_mode else launchagent.is_enabled()
        self.rows = M.rows_from_settings(self.app.settings)
        self.c, self.radio, self.preset_cards = {}, {}, []
        self.build()
        self._baseline = M.snapshot(self.form, self.rows)
        self.refresh_preview()
        try:
            self.tabview.selectTabViewItemAtIndex_(tab)
        except Exception:
            pass
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def close(self, force=False):
        if self.window is None:
            return True
        if not force and not self.install_mode and self.is_dirty():
            r = rumps.alert(APP_TITLE, t("unsaved_prompt"), ok=t("btn_save"), cancel=t("btn_close"), other=t("btn_cancel"))
            if r == -1:
                return False
            if r == 1:
                self.apply(close=True)
                return True
        w, self.window = self.window, None
        try:
            NSColorPanel.sharedColorPanel().orderOut_(None)
        except Exception:
            pass
        w.setDelegate_(None)
        w.orderOut_(None)
        w.close()
        return True

    def windowShouldClose_(self, sender):
        if self.install_mode:
            self.apply(close=True)
            return False
        return self.close()

    def is_dirty(self):
        try:
            return M.snapshot(self.form, self.rows) != self._baseline
        except Exception:
            return False

    # ---------- 창 만들기 ----------
    def build(self):
        style = 1 | 2 | 4                                    # titled | closable | miniaturizable
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0, 0, W, H), style, NSBackingStoreBuffered, False)
        win.setTitle_(f"{APP_TITLE} {t('win_setup') if self.install_mode else t('win_settings')}")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        win.setLevel_(3)                                     # 항상 위 (Windows 판 -topmost)
        root = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        win.setContentView_(root)
        self.window = win
        y = 12
        tf, h = label(APP_TITLE, 18, y, 300, 15, bold=True, wrap=False)
        root.addSubview_(tf)
        tf2, _ = label(f"v{__version__}  ·  " + t("preview_title"), W - 18 - 260, y + 2, 260, 11, color=NSColor.secondaryLabelColor(), wrap=False)
        tf2.setAlignment_(2)
        root.addSubview_(tf2)
        y += h + 8
        self.preview = NSImageView.alloc().initWithFrame_(NSMakeRect(18, y, CONTENT_W, 28))
        self.preview.setImageScaling_(0)                     # 실제 크기
        self.preview.setImageAlignment_(4)                   # 왼쪽 (NSImageAlignLeft)
        root.addSubview_(self.preview)
        y += 32
        self.preview_hint, h = label("", 18, y, CONTENT_W, 11)
        root.addSubview_(self.preview_hint)
        y += 18
        tf, h = label(t("preview_note"), 18, y, CONTENT_W, 10, color=NSColor.secondaryLabelColor())
        root.addSubview_(tf)
        y += h + 2
        if self.install_mode:
            tf, h = label(t("tos_note"), 18, y, CONTENT_W, 10, color=NSColor.systemOrangeColor())
            root.addSubview_(tf)
            y += h + 2
        # 탭
        bottom_h = 48
        self.tabview = NSTabView.alloc().initWithFrame_(NSMakeRect(14, y, TAB_W, H - y - bottom_h))
        root.addSubview_(self.tabview)
        self.build_tab_entries()
        self.build_tab_display()
        self.build_tab_data()
        self.build_tab_startup()
        self.build_tab_about()
        # 하단
        by = H - bottom_h + 12
        self.saved_label, _ = label("", 18, by + 4, 200, 12, bold=True, color=NSColor.systemGreenColor(), wrap=False)
        root.addSubview_(self.saved_label)
        if self.install_mode:
            root.addSubview_(button(t("btn_start"), W - 18 - 100, by, 100, self, "start:"))
        else:
            root.addSubview_(button(t("btn_close"), W - 18 - 90, by, 90, self, "closeClicked:"))
            root.addSubview_(button(t("btn_save"), W - 18 - 90 - 96, by, 90, self, "save:"))

    # ----- 탭 1: 항목 -----
    def build_tab_entries(self):
        doc = scroll_tab(self.tabview, "tab_entries", 400)
        self.entries_doc = doc
        y = section(doc, "sec_entries", 10, hint="hint_autodiscover")
        self.rows_top = y
        self.rows_container = FlippedView.alloc().initWithFrame_(NSMakeRect(14, y, DOC_W - 28, 10))
        doc.addSubview_(self.rows_container)
        self.rows_buttons = FlippedView.alloc().initWithFrame_(NSMakeRect(14, y, DOC_W - 28, 30))
        doc.addSubview_(self.rows_buttons)
        self.rows_buttons.addSubview_(button(t("btn_add_folder"), 0, 0, 120, self, "addFolder:"))
        self.rows_buttons.addSubview_(button(t("btn_rescan"), 126, 0, 100, self, "rescan:"))
        self.rows_buttons.addSubview_(button(t("btn_why_missing"), 232, 0, 160, self, "help:"))
        self.rescan_label, _ = label("", 400, 4, DOC_W - 28 - 400, 11, wrap=False)
        self.rows_buttons.addSubview_(self.rescan_label)
        self.rebuild_rows()

    def rebuild_rows(self):
        cont = self.rows_container
        for v in list(cont.subviews()):
            v.removeFromSuperview()
        y = 0
        if not self.rows:
            tf, h = label(t("no_entries_row"), 0, 0, DOC_W - 28, 11, color=NSColor.systemOrangeColor())
            cont.addSubview_(tf)
            y = h + 6
        for i, r in enumerate(self.rows):
            p = get_provider(r["provider"])
            card = FlippedView.alloc().initWithFrame_(NSMakeRect(0, y, DOC_W - 28, 50))
            card.setWantsLayer_(True)
            card.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
            card.layer().setBorderColor_(NSColor.separatorColor().CGColor())
            card.layer().setBorderWidth_(1)
            card.layer().setCornerRadius_(6)
            cb = button("", 8, 15, 20, self, "rowChanged:", tag=i, kind=SWITCH, h=20)
            cb.setState_(1 if r["enabled"] else 0)
            card.addSubview_(cb)
            self.c[f"row_enabled_{i}"] = cb
            tf, _ = label(p.name, 34, 6, 120, 10, color=NSColor.secondaryLabelColor(), wrap=False)
            card.addSubview_(tf)
            tf, _ = label(r["path"], 34, 27, 420, 10, color=NSColor.tertiaryLabelColor(), wrap=False)
            tf.setLineBreakMode_(5)                           # 가운데 …
            card.addSubview_(tf)
            f = field(160, 5, 130, r["label"], self, tag=i)
            f.setFont_(NSFont.systemFontOfSize_(11))
            card.addSubview_(f)
            self.c[f"row_label_{i}"] = f
            for j, (key, kx) in enumerate((("w5h", 300), ("w7d", 350))):
                b = button(key[1:], kx, 6, 48, self, "rowChanged:", tag=i, kind=SWITCH, h=20)
                b.setState_(1 if r[key] else 0)
                card.addSubview_(b)
                self.c[f"row_{key}_{i}"] = b
            col, txt = self.row_status(r)
            tf, _ = label("● " + txt, 404, 7, 90, 10, color=col, wrap=False)
            card.addSubview_(tf)
            x = DOC_W - 28 - 8
            for title, action, wdt in (("✕", "removeRow:", 28), ("▼", "moveDown:", 28), ("▲", "moveUp:", 28)):
                x -= wdt + 2
                card.addSubview_(button(title, x, 5, wdt, self, action, tag=i, h=22))
            if p.supports_official:
                linked = cc.statusline_installed(r["path"])
                x -= 150
                card.addSubview_(button(t("btn_statusline_uninstall" if linked else "btn_statusline_install"), x, 5, 144, self, "toggleLink:", tag=i, h=22))
            cont.addSubview_(card)
            y += 56
        cont.setFrame_(NSMakeRect(14, self.rows_top, DOC_W - 28, max(y, 10)))
        self.rows_buttons.setFrame_(NSMakeRect(14, self.rows_top + max(y, 10) + 8, DOC_W - 28, 30))
        fit_doc(self.entries_doc, self.rows_top + max(y, 10) + 8 + 36)
        self.refresh_fixed_popup()
        self.preview_dirty()

    def row_status(self, r):
        p = get_provider(r["provider"])
        d = self.app.data.get(f"{r['provider']}|{r['path']}") or {}
        try:
            info = p.info(r["path"])
        except Exception:
            info = {"connected": False}
        if d.get("error") or not info.get("connected"):
            return NSColor.systemRedColor(), t("st_err")
        if d.get("usage") or info.get("connected"):
            return NSColor.systemGreenColor(), t("st_ok")
        return NSColor.secondaryLabelColor(), t("st_unknown")

    # ----- 탭 2: 표시 · 스타일 -----
    def build_tab_display(self):
        doc = scroll_tab(self.tabview, "tab_display", 700)
        f = self.form
        y = section(doc, "presets_title", 10, hint="presets_hint")
        cw, ch = (DOC_W - 28 - 16) / 3, 66
        for i, (key, values) in enumerate(M.PRESETS):
            cx, cy = 14 + (i % 3) * (cw + 8), y + (i // 3) * (ch + 8)
            card = FlippedView.alloc().initWithFrame_(NSMakeRect(cx, cy, cw, ch))
            card.setWantsLayer_(True)
            card.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
            card.layer().setBorderWidth_(1)
            card.layer().setCornerRadius_(6)
            iv = NSImageView.alloc().initWithFrame_(NSMakeRect(6, 6, cw - 12, 24))
            iv.setImageScaling_(3)                            # 비율 유지 축소 (NSImageScaleProportionallyDown)
            iv.setImageAlignment_(4)
            iv.setImage_(self.preset_image(values, cw - 12))
            card.addSubview_(iv)
            tf, _ = label(t(f"preset_{key}"), 6, 36, cw - 12, 11, bold=True, wrap=False)
            card.addSubview_(tf)
            tf, _ = label(t(f"preset_{key}_desc"), 6, 50, cw - 12, 10, color=NSColor.secondaryLabelColor(), wrap=False)
            card.addSubview_(tf)
            ov = button("", 0, 0, cw, self, "preset:", tag=i, kind=7, h=ch)
            ov.setBordered_(False)
            ov.setTransparent_(True)
            card.addSubview_(ov)
            doc.addSubview_(card)
            self.preset_cards.append((key, values, card))
        y += 2 * (ch + 8) + 4
        # 표시 방식 (라디오 4개 — 같은 컨테이너·같은 action 이라 AppKit 이 한 그룹으로 묶는다)
        y = section(doc, "sec_mode", y)
        grp = FlippedView.alloc().initWithFrame_(NSMakeRect(14, y, DOC_W - 28, 4 * 22))
        for i, mode in enumerate(MODES):
            b = button(t(f"mode_{mode}"), 0, i * 22, DOC_W - 28, self, "radio:", tag=i, kind=RADIO, h=20)
            b.setState_(1 if f["display_mode"] == mode else 0)
            grp.addSubview_(b)
        doc.addSubview_(grp)
        self.radio["display_mode"] = (grp, list(MODES))
        y += 4 * 22 + 6
        tf, _ = label(t("slide_hint_pre"), 14, y + 4, 100, 11, wrap=False)
        doc.addSubview_(tf)
        self.c["slide_sec"] = field(118, y, 60, f["slide_sec"], self, tag=100)
        doc.addSubview_(self.c["slide_sec"])
        tf, _ = label(t("slide_hint"), 184, y + 4, 200, 10, color=NSColor.secondaryLabelColor(), wrap=False)
        doc.addSubview_(tf)
        tf, _ = label(t("fixed_hint"), 390, y + 4, 90, 11, wrap=False)
        doc.addSubview_(tf)
        self.c["fixed_entry"] = popup(484, y - 2, DOC_W - 28 - 484 + 14, [""], 0, self, "changed:")
        doc.addSubview_(self.c["fixed_entry"])
        self.refresh_fixed_popup()
        y += 30
        for key, opts, values, tkey in (("placement", "placement_", PLACEMENTS, "placement_label"),
                                        ("overflow_policy", "policy_", OVERFLOW_POLICIES, "overflow_label"),
                                        ("switch_indicator", "indicator_", INDICATORS, "indicator_label")):
            tf, _ = label(t(tkey), 14, y + 5, 150, 11, wrap=False)
            doc.addSubview_(tf)
            self.c[key] = popup(168, y, DOC_W - 28 - 168 + 14, [t(opts + v) for v in values], list(values).index(f[key]), self, "changed:")
            doc.addSubview_(self.c[key])
            y += 30
        tf, _ = label(t("mac_max_width"), 14, y + 4, 300, 11, wrap=False)
        doc.addSubview_(tf)
        self.c["max_width_pt"] = field(318, y, 70, f["max_width_pt"], self, tag=101)
        doc.addSubview_(self.c["max_width_pt"])
        y += 30
        # 모양
        y = section(doc, "sec_look", y)
        for key, tkey in (("label", "style_label"), ("show_scoped", "item_scoped")):
            b = button(t(tkey), 14, y, DOC_W - 28, self, "changed:", kind=SWITCH, h=20)
            b.setState_(1 if f[key] else 0)
            doc.addSubview_(b)
            self.c[key] = b
            y += 24
        tf, _ = label(t("style_bars"), 14, y + 5, 60, 11, wrap=False)
        doc.addSubview_(tf)
        self.c["bars"] = popup(78, y, 200, [t("mac_bars_auto") if v == "auto" else t(f"style_bars_{v}") for v in BAR_STYLES],
                               list(BAR_STYLES).index(f["bars"]), self, "changed:")
        doc.addSubview_(self.c["bars"])
        tf, _ = label(t("style_colors") + " " + t("style_label_color"), 300, y + 5, 150, 11, wrap=False)
        doc.addSubview_(tf)
        chip = NSTextField.labelWithString_("")
        chip.setFrame_(NSMakeRect(456, y + 2, 28, 22))
        chip.setDrawsBackground_(True)
        chip.setBezeled_(True)
        chip.setBackgroundColor_(R.color_from_hex(f["label_color"]) or NSColor.controlColor())
        doc.addSubview_(chip)
        self.c["label_color_chip"] = chip
        doc.addSubview_(button(t("style_pick"), 490, y, 80, self, "pickColor:"))
        doc.addSubview_(button(t("style_reset"), 574, y, 70, self, "resetColor:"))
        y += 34
        fit_doc(doc, y)

    def preset_image(self, values, width):
        S = M.preset_settings(values)
        runs = self.app.runs_for(S, S["entries"], M.preview_data(S["entries"], {}), "full", 0)
        return R.runs_image(runs, min_w=int(width))

    # ----- 탭 3: 데이터 -----
    def build_tab_data(self):
        doc = scroll_tab(self.tabview, "tab_data", 400)
        f = self.form
        y = section(doc, "sec_data_source", 10)
        grp = FlippedView.alloc().initWithFrame_(NSMakeRect(14, y, DOC_W - 28, 100))
        gy = 0
        for i, (val, key) in enumerate((("api", "ds_api"), ("official", "ds_official"))):
            b = button("", 0, gy, DOC_W - 28, self, "radio:", tag=i, kind=RADIO, h=20)
            b.setState_(1 if f["data_source"] == val else 0)
            grp.addSubview_(b)
            tf, h = label(t(key), 22, gy + 2, DOC_W - 28 - 22, 11)
            grp.addSubview_(tf)
            gy += max(22, h + 6)
        grp.setFrame_(NSMakeRect(14, y, DOC_W - 28, gy))
        doc.addSubview_(grp)
        self.radio["data_source"] = (grp, ["api", "official"])
        y += gy + 4
        b = button(t("ds_hide_unsupported"), 14, y, DOC_W - 28, self, "changed:", kind=SWITCH, h=20)
        b.setState_(1 if f["official_hide_unsupported"] else 0)
        doc.addSubview_(b)
        self.c["official_hide_unsupported"] = b
        y += 30
        y = section(doc, "sec_status", y)
        self.status_label, h = label("", 14, y, DOC_W - 28, 11)
        doc.addSubview_(self.status_label)
        self.status_y = y
        y += 80
        self.recheck_btn = button(t("btn_recheck"), 14, y, 160, self, "recheck:")
        doc.addSubview_(self.recheck_btn)
        y += 34
        self.note_label, h = label(t("unofficial_note"), 14, y, DOC_W - 28, 10, color=NSColor.secondaryLabelColor())
        doc.addSubview_(self.note_label)
        self.data_doc = doc
        self.fill_status()

    def fill_status(self):
        if self.window is None:
            return
        lines = []
        for e in self.app.settings["entries"]:
            p = get_provider(e["provider"])
            try:
                info = p.info(e["path"])
            except Exception as ex:
                info = {"connected": False, "reason": f"err_token_read {ex}", "plan": None, "expires_at": None}
            d = self.app.data.get(entry_key(e)) or {}
            if info["connected"]:
                s = t("status_connected", label=e["label"], name=p.name, plan=info["plan"] or "?",
                      exp=info["expires_at"].strftime("%m/%d %H:%M") if info["expires_at"] else "?")
            else:
                s = t("status_disconnected", label=e["label"], name=p.name, reason=tr_error(info["reason"]))
            if d.get("error"):
                s += t("status_error", err=tr_error(d["error"]))
                if d.get("next_try"):
                    s += " " + t("tt_next_try", time=d["next_try"].strftime("%H:%M"))
            elif d.get("last_ok"):
                s += t("status_last_ok", time=d["last_ok"].strftime("%H:%M:%S"))
            if p.supports_official and cc.statusline_installed(e["path"]):
                s += t("status_statusline_on")
            lines.append(s)
        self.status_label.setStringValue_("\n".join(lines))
        h = self.status_label.cell().cellSizeForBounds_(NSMakeRect(0, 0, DOC_W - 28, 100000)).height
        self.status_label.setFrame_(NSMakeRect(14, self.status_y, DOC_W - 28, h))
        y = self.status_y + h + 10
        self.recheck_btn.setFrameOrigin_((14, y))
        y += 34
        nh = self.note_label.frame().size.height
        self.note_label.setFrameOrigin_((14, y))
        fit_doc(self.data_doc, y + nh)

    # ----- 탭 4: 시작 · 언어 -----
    def build_tab_startup(self):
        doc = scroll_tab(self.tabview, "tab_startup", 300)
        y = section(doc, "sec_startup", 10)
        b = button(t("mac_menu_autostart"), 14, y, DOC_W - 28, self, "changed:", kind=SWITCH, h=20)
        b.setState_(1 if self.form["autostart"] else 0)
        doc.addSubview_(b)
        self.c["autostart"] = b
        y += 26
        tf, h = label(t("run_location", dir=ROOT_DIR) + "\n" + t("mac_about_remove"), 14, y, DOC_W - 28, 10, color=NSColor.secondaryLabelColor())
        doc.addSubview_(tf)
        y += h + 10
        y = section(doc, "sec_language", y)
        codes = ["auto"] + list(SUPPORTED)
        names = [t("lang_auto")] + [LANG_NAMES[c] for c in SUPPORTED]
        self.c["language"] = popup(14, y, 220, names, codes.index(self.form["language"]), self, "changed:")
        doc.addSubview_(self.c["language"])
        y += 34
        fit_doc(doc, y)

    # ----- 탭 5: 정보 -----
    def build_tab_about(self):
        doc = scroll_tab(self.tabview, "tab_about", 600)
        y = 12
        tf, h = label(f"{APP_TITLE}  v{__version__}  (macOS)", 14, y, DOC_W - 28, 14, bold=True, wrap=False)
        doc.addSubview_(tf)
        y += h + 4
        for key, size, color in (("app_desc", 11, NSColor.secondaryLabelColor()),):
            tf, h = label(t(key), 14, y, DOC_W - 28, size, color=color)
            doc.addSubview_(tf)
            y += h + 4
        tf, h = label(" · ".join(p.name for p in PROVIDERS), 14, y, DOC_W - 28, 10, color=NSColor.secondaryLabelColor())
        doc.addSubview_(tf)
        y += h + 8
        y = section(doc, "about_transparency", y)
        for key in ("about_reads", "mac_about_keychain", "about_sends", "about_stores"):
            tf, h = label("•  " + t(key), 14, y, DOC_W - 28, 11)
            doc.addSubview_(tf)
            y += h + 4
        y += 6
        for i, key in enumerate(("link_readme", "mac_link_releases", "menu_support")):
            doc.addSubview_(link(t(key), 14, y, DOC_W - 28, self, "openLink:", tag=i))
            y += 22
        y += 6
        doc.addSubview_(button(t("btn_why_missing"), 14, y, 160, self, "help:"))
        doc.addSubview_(button(t("btn_open_logs"), 180, y, 170, self, "openLogs:"))
        y += 36
        for key, color in (("tos_note", NSColor.systemOrangeColor()), ("mac_modclick_hint", NSColor.secondaryLabelColor()),
                           ("mac_about_remove", NSColor.secondaryLabelColor()), ("mac_gatekeeper_hint", NSColor.secondaryLabelColor()),
                           ("unofficial_note", NSColor.secondaryLabelColor()), ("trademark_note", NSColor.secondaryLabelColor())):
            tf, h = label(t(key), 14, y, DOC_W - 28, 10, color=color)
            doc.addSubview_(tf)
            y += h + 6
        fit_doc(doc, y)

    # ---------- 폼 읽기 ----------
    def read_form(self):
        f = self.form
        for key, (grp, values) in self.radio.items():
            for b in grp.subviews():
                if isinstance(b, NSButton) and b.state() == 1 and 0 <= b.tag() < len(values):
                    f[key] = values[b.tag()]
        f["slide_sec"] = M.clamp_slide(self.c["slide_sec"].stringValue())
        try:
            f["max_width_pt"] = max(0, min(2000, int(float(self.c["max_width_pt"].stringValue() or 0))))
        except Exception:
            f["max_width_pt"] = 0
        choices = M.fixed_choices(self.rows)
        idx = self.c["fixed_entry"].indexOfSelectedItem()
        f["fixed_entry"] = choices[idx][0] if 0 <= idx < len(choices) else ""
        for key, values in (("placement", PLACEMENTS), ("overflow_policy", OVERFLOW_POLICIES), ("switch_indicator", INDICATORS), ("bars", BAR_STYLES)):
            f[key] = values[max(0, self.c[key].indexOfSelectedItem())]
        for key in ("label", "show_scoped", "official_hide_unsupported", "autostart"):
            f[key] = self.c[key].state() == 1
        codes = ["auto"] + list(SUPPORTED)
        f["language"] = codes[max(0, self.c["language"].indexOfSelectedItem())]
        for i, r in enumerate(self.rows):
            r["enabled"] = self.c[f"row_enabled_{i}"].state() == 1
            r["label"] = self.c[f"row_label_{i}"].stringValue()
            r["w5h"] = self.c[f"row_w5h_{i}"].state() == 1
            r["w7d"] = self.c[f"row_w7d_{i}"].state() == 1
        return f

    def current_settings(self):
        return M.form_to_settings(self.read_form(), self.rows)

    def refresh_fixed_popup(self):
        p = self.c.get("fixed_entry")
        if p is None:
            return
        choices = M.fixed_choices(self.rows)
        cur = self.form.get("fixed_entry")
        p.removeAllItems()
        p.addItemsWithTitles_([n for _, n in choices] or [""])
        idx = next((i for i, (k, _) in enumerate(choices) if k == cur), 0)
        p.selectItemAtIndex_(idx)

    # ---------- 미리보기 ----------
    def preview_dirty(self):
        if self.window is not None and not self._preview_job:
            self._preview_job = True
            AppHelper.callLater(0.05, self.refresh_preview)

    def refresh_preview(self):
        self._preview_job = False
        if self.window is None:
            return
        try:
            S = self.current_settings()
        except Exception as e:
            applog.warn("refresh_preview", e)
            return
        ents = [e for e in S["entries"] if e["enabled"]]
        data = M.preview_data(ents, self.app.data)
        tiers = M.tiers(S["style"]["bars"])
        tier = tiers[0]
        runs = self.app.runs_for(S, ents, data, tier, 0)
        need = self.app.measure(runs)
        avail = self.app.available_width(S)
        if avail is not None:
            for tr in tiers:
                r2 = self.app.runs_for(S, ents, data, tr, 0)
                if self.app.measure(r2) <= avail:
                    tier, runs, need = tr, r2, self.app.measure(r2)
                    break
        self.preview.setImage_(R.runs_image(runs, min_w=int(CONTENT_W), label_color=R.color_from_hex(S["style"]["label_color"])))
        adj = t("preview_auto_adjusted", policy=t(f"policy_{self.app.overflow.adjusted}")) if self.app.overflow.adjusted else ""
        self.preview_hint.setStringValue_(t("mac_preview_hint", n=int(need), tier=t(f"tier_{tier}"), adj=adj))
        for key, values, card in self.preset_cards:
            on = M.preset_matches(S, values)
            card.layer().setBorderColor_((NSColor.controlAccentColor() if on else NSColor.separatorColor()).CGColor())
            card.layer().setBorderWidth_(2 if on else 1)

    # ---------- 액션 ----------
    def changed_(self, sender):
        self.read_form()
        self.preview_dirty()

    def controlTextDidChange_(self, note):
        self.read_form()
        self.refresh_fixed_popup()
        self.preview_dirty()

    def radio_(self, sender):
        for b in sender.superview().subviews():
            if isinstance(b, NSButton) and b is not sender:
                b.setState_(0)
        sender.setState_(1)
        self.changed_(sender)

    def rowChanged_(self, sender):
        self.changed_(sender)

    def preset_(self, sender):
        key, values = M.PRESETS[sender.tag()]
        self.read_form()
        M.apply_preset(self.form, values)
        grp, modes = self.radio["display_mode"]
        for b in grp.subviews():
            if isinstance(b, NSButton):
                b.setState_(1 if modes[b.tag()] == values["display_mode"] else 0)
        self.c["show_scoped"].setState_(1 if values["show_scoped"] else 0)
        self.c["label"].setState_(1 if values["style"]["label"] else 0)
        self.c["bars"].selectItemAtIndex_(list(BAR_STYLES).index(values["style"]["bars"]))
        self.preview_dirty()

    def moveUp_(self, sender):
        self.read_form()
        M.move_row(self.rows, sender.tag(), -1)
        self.rebuild_rows()

    def moveDown_(self, sender):
        self.read_form()
        M.move_row(self.rows, sender.tag(), 1)
        self.rebuild_rows()

    def removeRow_(self, sender):
        self.read_form()
        del self.rows[sender.tag()]
        self.rebuild_rows()

    def toggleLink_(self, sender):
        self.read_form()
        self.app.toggle_statusline(self.rows[sender.tag()]["path"])
        self.rebuild_rows()
        self.fill_status()

    def addFolder_(self, sender):
        self.read_form()
        r = rumps.alert(t("pick_provider_title"), t("pick_provider_body"), ok=PROVIDERS[0].name, cancel=t("btn_cancel"), other=PROVIDERS[1].name)
        if r == 0:
            return
        p = PROVIDERS[0] if r == 1 else PROVIDERS[1]
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setShowsHiddenFiles_(True)                     # ~/.claude · ~/.codex 는 숨김 폴더
        panel.setMessage_(t("dialog_pick_folder", name=p.name, file=p.cred_file))
        panel.setDirectoryURL_(__import__("Foundation").NSURL.fileURLWithPath_(os.path.expanduser("~")))
        if panel.runModal() != 1:
            return
        d = panel.URLs()[0].path()
        st, row = M.add_folder(self.rows, p, d)
        if st == "dup":
            rumps.alert(APP_TITLE, t("dup_folder"))
            return
        if st == "nocred":
            if rumps.alert(APP_TITLE, t("no_cred_confirm", file=p.cred_file, name=p.name), ok=t("btn_ok"), cancel=t("btn_cancel")) != 1:
                return
            self.rows.append(row)
        self.rebuild_rows()

    def rescan_(self, sender):
        self.read_form()
        added = M.rescan(self.rows)
        self.rebuild_rows()
        self.rescan_label.setStringValue_(t("rescan_found", n=added) if added else t("rescan_none"))

    def help_(self, sender):
        self.app.open_help()

    def recheck_(self, sender):
        self.app.refresh_async(manual=True)

    def openLogs_(self, sender):
        self.app.open_folder(LOG_DIR)

    def openLink_(self, sender):
        webbrowser.open((README_URL, RELEASES_URL, SUPPORT_URL)[sender.tag()])

    def pickColor_(self, sender):
        panel = NSColorPanel.sharedColorPanel()
        cur = R.color_from_hex(self.form.get("label_color"))
        if cur is not None:
            panel.setColor_(cur)
        panel.setTarget_(self)
        panel.setAction_("colorChanged:")
        panel.setContinuous_(True)
        panel.orderFront_(None)

    def colorChanged_(self, sender):
        hexv = R.hex_from_color(sender.color())
        if hexv:
            self.form["label_color"] = hexv
            self.c["label_color_chip"].setBackgroundColor_(sender.color())
            self.preview_dirty()

    def resetColor_(self, sender):
        self.form["label_color"] = ""
        self.c["label_color_chip"].setBackgroundColor_(NSColor.controlColor())
        self.preview_dirty()

    def save_(self, sender):
        self.apply(close=False)

    def start_(self, sender):
        self.apply(close=True)

    def closeClicked_(self, sender):
        self.close()

    # ---------- 저장 ----------
    def apply(self, close=False):
        form = self.read_form()
        new = M.form_to_settings(form, self.rows)
        lang_changed = new["language"] != self.app.settings["language"]
        try:
            self.app.apply_settings(new, autostart=form["autostart"])
        except Exception as e:
            applog.warn("apply_settings", e)
        self._baseline = M.snapshot(form, self.rows)
        if lang_changed:                                     # 바뀐 언어로 설정 창을 다시 연다
            tab = self.tabview.indexOfTabViewItem_(self.tabview.selectedTabViewItem()) if self.window else 0
            self.close(force=True)
            if not close:
                AppHelper.callLater(0.1, lambda: self.show(tab=tab))
            return
        if close:
            self.close(force=True)
            return
        self.fill_status()
        self.saved_label.setStringValue_(t("btn_saved"))
        AppHelper.callLater(2.0, lambda: self.saved_label.setStringValue_("") if self.window else None)

    def on_data_refreshed(self):
        if self.window is None:
            return
        self.fill_status()
        self.rebuild_rows()
