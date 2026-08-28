"""
rumps 앱 — 메뉴 막대 상태 항목 하나.

- 제목 = 사용률 글자. NSAttributedString 으로 퍼센트 조각마다 색(초록/노랑/빨강)을 입힌다 (실패하면 ●색 이모지 폴백).
- 조회는 백그라운드 스레드(polling.run_refresh — 백오프·인플라이트 락), 결과 반영은 AppHelper.callAfter 로 메인 스레드에서.
- 메뉴: 항목별 상세 · 새로고침(10초 디바운스) · 다음 항목 · 사용량 페이지 · 표시 방식 · 라벨 · 데이터 원본(공식 모드 연결) ·
        자동 시작 · 언어 · 정보 · 오류 로그 폴더 · README · 종료.
- 80% / 95% 알림 1회 (rumps.notification → 번들이 없어 실패하면 osascript display notification → 그것도 안 되면 로그만).
"""
import os
import subprocess
import threading
import webbrowser
from datetime import datetime

import rumps
from AppKit import (NSApplication, NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName,
                    NSMutableAttributedString, NSObject)
from PyObjCTools import AppHelper

import applog
import polling
from i18n import LANG_NAMES, SUPPORTED, set_language, t, tr_error
from providers import fmt_reset, get as get_provider
from providers import claude_code as cc
from version import __version__

from . import launchagent, title as T
from .paths import APP_TITLE, LOG_DIR, README_URL, SETTINGS_PATH, STATUSLINE_SH, SUPPORT_URL
from .settings import (MODES, SLIDE_CHOICES, enabled_entries_of, ensure_discovered, entry_key, load_settings,
                       merge_discovered, save_settings)

POLL_SEC = polling.clamp_poll_sec(os.environ.get("AI_STATUS_BAR_POLL_SEC"))
OFFICIAL_POLL_SEC = 30
ALERT_STEPS = (80, 95)
NSApplicationActivationPolicyAccessory = 1


class _MenuDelegate(NSObject):
    """메뉴가 열리기 직전에 내용을 다시 만든다 — 열려 있는 동안은 조회 결과가 와도 건드리지 않는다."""

    def initWithApp_(self, app):
        self = objc_super_init(self)
        self.app = app
        return self

    def menuNeedsUpdate_(self, _menu):
        try:
            self.app.build_menu()
        except Exception as e:
            applog.warn("build_menu", e)

    def menuWillOpen_(self, _menu):
        self.app.menu_open = True

    def menuDidClose_(self, _menu):
        self.app.menu_open = False


def objc_super_init(obj):
    from objc import super as objc_super
    return objc_super(_MenuDelegate, obj).init()


class MacStatusBar(rumps.App):
    def __init__(self):
        super().__init__(APP_TITLE, title="…", quit_button=None)
        self.settings = load_settings()
        set_language(self.settings["language"])
        if ensure_discovered(self.settings):
            save_settings(self.settings)
        self.data = {}
        self.backoff = polling.Backoff()
        self.debounce = polling.Debounce()
        self._lock = threading.Lock()
        self.cur = 0
        self.alerted = {}
        self.menu_open = False
        self._delegate = _MenuDelegate.alloc().initWithApp_(self)
        self._menu._menu.setDelegate_(self._delegate)
        self.poll_timer = rumps.Timer(self._on_poll, self.poll_sec())
        self.slide_timer = rumps.Timer(self._on_slide, self.settings["slide_sec"])
        self.build_menu()
        self.update_title()

    # ---------- 실행 ----------
    def run(self, **options):
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)   # Dock 아이콘 없음
        self.poll_timer.start()           # 첫 발화가 즉시라 시작하자마자 조회한다
        self.sync_slide_timer()
        super().run(**options)

    def official(self):
        return self.settings["data_source"] == "official"

    def poll_sec(self):
        return OFFICIAL_POLL_SEC if self.official() else POLL_SEC

    def entries(self):
        return enabled_entries_of(self.settings)

    def visible(self):
        return T.pick_visible(self.entries(), self.settings["display_mode"], self.cur, self.settings["fixed_entry"], entry_key)

    def switchable(self):
        return self.settings["display_mode"] in ("click", "slide") and len(self.entries()) > 1

    # ---------- 조회 ----------
    def _on_poll(self, _timer=None):
        self.refresh_async()

    def refresh_async(self, manual=False):
        if manual and not self.debounce.allow():
            return False
        if self._lock.locked():
            return False
        threading.Thread(target=self._refresh, name="refresh", daemon=True).start()
        return True

    def _refresh(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            settings = self.settings
            official = settings["data_source"] == "official"
            entries = list(enabled_entries_of(settings))

            def fetch(e):
                p = get_provider(e["provider"])
                if official:
                    return p.fetch_official(e["path"])          # 네트워크 코드를 타지 않는다
                return p.fetch(e["path"]), None

            polling.run_refresh(entries, fetch, self.data, self.backoff, key_of=entry_key)
        except Exception as ex:
            applog.warn("_refresh", ex)
        finally:
            self._lock.release()
        AppHelper.callAfter(self.after_refresh)

    def after_refresh(self):
        self.update_title()
        if not self.menu_open:
            self.build_menu()
        self.check_alerts()

    # ---------- 제목 ----------
    def update_title(self):
        runs = T.build_runs(self.visible(), self.data, entry_key, self.settings["style"]["label"],
                            self.settings["show_scoped"], t("mac_title_no_entries"))
        text = T.plain(runs)
        self.title = text
        try:
            self._apply_colors(runs, text)
        except Exception as e:
            applog.warn("attributed title", e)
            self.title = T.with_dots(runs)

    _COLORS = {"green": "systemGreenColor", "yellow": "systemYellowColor", "red": "systemRedColor"}

    def _apply_colors(self, runs, text):
        nsapp = getattr(self, "_nsapp", None)
        if nsapp is None:                     # run() 전 — 아직 상태 항목이 없다
            return
        button = nsapp.nsstatusitem.button()
        font = NSFont.monospacedDigitSystemFontOfSize_weight_(NSFont.menuBarFontOfSize_(0).pointSize(), 0.0)
        attr = NSMutableAttributedString.alloc().initWithString_(text)
        whole = (0, len(text))
        attr.addAttribute_value_range_(NSFontAttributeName, font, whole)
        attr.addAttribute_value_range_(NSForegroundColorAttributeName, NSColor.labelColor(), whole)
        pos = 0
        for s, pct in runs:
            if pct is not None:
                color = getattr(NSColor, self._COLORS[T.tier(pct)])()
                attr.addAttribute_value_range_(NSForegroundColorAttributeName, color, (pos, len(s)))
            pos += len(s)
        button.setAttributedTitle_(attr)

    # ---------- 슬라이드 ----------
    def sync_slide_timer(self):
        want = self.settings["display_mode"] == "slide" and len(self.entries()) > 1
        if self.slide_timer.is_alive():
            self.slide_timer.stop()
        if want:
            self.slide_timer.interval = self.settings["slide_sec"]
            self.slide_timer.start()

    def _on_slide(self, _timer=None):
        if self.switchable():
            self.next_entry()

    def next_entry(self, _sender=None):
        if self.switchable():
            self.cur = (self.cur + 1) % len(self.entries())
            self.update_title()
            self.build_menu()

    # ---------- 메뉴 ----------
    def build_menu(self):
        m = self.menu
        _forget(m)                                # rumps 는 콜백 표를 지우지 않는다 — 5분마다 다시 만들면 새기 때문에 우리가 지운다
        m.clear()
        n = [0]

        def add(item, parent=m):
            n[0] += 1
            parent[f"_{n[0]}"] = item             # 제목이 같은 행이 있어도 지워지지 않게 키를 따로 준다
            return item

        def sep(parent=m):
            add(rumps.separator, parent)

        ents = self.entries()
        if not ents:
            add(rumps.MenuItem(t("mac_no_entries")))
        for e in ents:
            for line in self.detail_lines(e):
                add(rumps.MenuItem(line))
        sep()
        add(rumps.MenuItem(t("menu_refresh"), callback=lambda _: self.refresh_async(manual=True)))
        if self.switchable():
            add(rumps.MenuItem(t("menu_next"), callback=self.next_entry))
        add(rumps.MenuItem(t("btn_rescan"), callback=self.rescan))
        pages = add(rumps.MenuItem(t("mac_menu_usage_pages")))
        for p in (get_provider("claude_code"), get_provider("codex")):
            add(rumps.MenuItem(t("menu_usage_page", name=p.name), callback=lambda _, p=p: webbrowser.open(p.usage_page)), pages)
        sep()
        # 표시 방식
        disp = add(rumps.MenuItem(t("mac_menu_display")))
        for mode in MODES:
            it = add(rumps.MenuItem(t(f"mac_mode_{mode}"), callback=lambda _, mode=mode: self.set_mode(mode)), disp)
            it.state = 1 if self.settings["display_mode"] == mode else 0
        sep(disp)
        slide = add(rumps.MenuItem(t("slide_hint_pre")), disp)
        for sec in SLIDE_CHOICES:
            it = add(rumps.MenuItem(t("mac_slide_sec", sec=sec), callback=lambda _, sec=sec: self.set_slide_sec(sec)), slide)
            it.state = 1 if self.settings["slide_sec"] == sec else 0
        if len(ents) > 1:
            fixed = add(rumps.MenuItem(t("fixed_hint")), disp)
            for e in ents:
                it = add(rumps.MenuItem(f"{get_provider(e['provider']).short} · {e['label']}",
                                        callback=lambda _, k=entry_key(e): self.set_fixed(k)), fixed)
                it.state = 1 if self.settings["fixed_entry"] == entry_key(e) else 0
        it = add(rumps.MenuItem(t("mac_menu_label"), callback=lambda _: self.toggle("style.label")))
        it.state = 1 if self.settings["style"]["label"] else 0
        it = add(rumps.MenuItem(t("mac_menu_scoped"), callback=lambda _: self.toggle("show_scoped")))
        it.state = 1 if self.settings["show_scoped"] else 0
        # 데이터 원본 · 공식 모드
        ds = add(rumps.MenuItem(t("mac_menu_data_source")))
        for src in ("api", "official"):
            it = add(rumps.MenuItem(t(f"mac_ds_{src}"), callback=lambda _, src=src: self.set_data_source(src)), ds)
            it.state = 1 if self.settings["data_source"] == src else 0
        claude_entries = [e for e in self.settings["entries"] if e["provider"] == "claude_code"]
        if claude_entries:
            sep(ds)
            for e in claude_entries:
                installed = cc.statusline_installed(e["path"])
                action = t("btn_statusline_uninstall" if installed else "btn_statusline_install")
                add(rumps.MenuItem(t("mac_statusline_item", label=e["label"], action=action),
                                   callback=lambda _, e=e, inst=installed: self.toggle_statusline(e, inst)), ds)
        it = add(rumps.MenuItem(t("mac_menu_autostart"), callback=self.toggle_autostart))
        it.state = 1 if launchagent.is_enabled() else 0
        lang = add(rumps.MenuItem(t("mac_menu_language")))
        for code in ("auto",) + SUPPORTED:
            it = add(rumps.MenuItem(t("lang_auto") if code == "auto" else LANG_NAMES[code],
                                    callback=lambda _, code=code: self.set_language(code)), lang)
            it.state = 1 if self.settings["language"] == code else 0
        sep()
        add(rumps.MenuItem(t("mac_menu_about"), callback=self.show_about))
        add(rumps.MenuItem(t("btn_open_logs"), callback=lambda _: self.open_folder(LOG_DIR)))
        add(rumps.MenuItem(t("menu_readme"), callback=lambda _: webbrowser.open(README_URL)))
        add(rumps.MenuItem(t("menu_support"), callback=lambda _: webbrowser.open(SUPPORT_URL)))
        sep()
        add(rumps.MenuItem(t("menu_quit"), callback=lambda _: rumps.quit_application(), key="q"))

    def detail_lines(self, e):
        """항목 상세 — 서비스 · 계정 · 플랜 / 창별 % 와 리셋 현지시각 / 마지막 조회 / 오류."""
        p = get_provider(e["provider"])
        d = self.data.get(entry_key(e)) or {}
        try:
            plan = p.info(e["path"]).get("plan") or ""
        except Exception:
            plan = ""
        head = f"{p.name} · {e['label']}" + (f" · {plan}" if plan else "")
        lines = [head]
        u = d.get("usage")
        if u:
            for w in T.entry_windows(e, u):
                lines.append(f"    {w['key']} {w['pct']:.0f}% · " + t("mac_reset", t=fmt_reset(w["resets_at"]) or "—"))
            if self.settings["show_scoped"]:
                for s in u.get("scoped") or []:
                    lines.append(f"    {s['model']} {s['pct']:.0f}% " + t("tt_scoped"))
        if d.get("error"):
            lines.append("    " + t("tt_error", err=tr_error(d["error"])))
            if d.get("next_try"):
                lines.append("    " + t("tt_next_try", time=d["next_try"].strftime("%H:%M")))
        elif self.official() and d.get("saved_at"):
            age = int((datetime.now() - d["saved_at"]).total_seconds() // 60)
            lines.append("    " + (t("tt_official_ago", m=age) if age >= 1 else t("tt_official")))
        elif d.get("last_ok"):
            lines.append("    " + t("tt_fetched_only", time=d["last_ok"].strftime("%H:%M:%S")))
        elif not u:
            lines.append("    " + t("tt_loading"))
        return lines

    # ---------- 설정 변경 ----------
    def save(self):
        try:
            save_settings(self.settings)
        except Exception as e:
            applog.warn("save_settings", e)
        self.cur = 0
        self.update_title()
        self.build_menu()

    def set_mode(self, mode):
        self.settings["display_mode"] = mode
        self.save()
        self.sync_slide_timer()

    def set_slide_sec(self, sec):
        self.settings["slide_sec"] = int(sec)
        self.save()
        self.sync_slide_timer()

    def set_fixed(self, key):
        self.settings["fixed_entry"] = key
        self.save()

    def toggle(self, dotted):
        obj, _, leaf = dotted.rpartition(".")
        target = self.settings[obj] if obj else self.settings
        target[leaf] = not target[leaf]
        self.save()

    def set_data_source(self, src):
        self.settings["data_source"] = src
        self.data.clear()
        self.backoff = polling.Backoff()
        self.save()
        self.poll_timer.stop()
        self.poll_timer.interval = self.poll_sec()
        self.poll_timer.start()

    def set_language(self, code):
        self.settings["language"] = code
        set_language(code)
        self.save()

    def rescan(self, _sender=None):
        added = merge_discovered(self.settings["entries"])
        self.save()
        rumps.alert(APP_TITLE, t("rescan_found", n=added) if added else t("rescan_none"))
        if added:
            self.refresh_async()

    def toggle_autostart(self, _sender=None):
        try:
            if launchagent.is_enabled():
                launchagent.disable(unload=False)
            else:
                launchagent.enable(start=False)
        except Exception as e:
            applog.warn("autostart", e)
            rumps.alert(APP_TITLE, t("autostart_failed", e=e))
        self.build_menu()

    def toggle_statusline(self, e, installed):
        sp = cc.settings_path(e["path"])
        if installed:
            if rumps.alert(APP_TITLE, t("statusline_confirm_uninstall", path=sp), ok=t("btn_ok"), cancel=t("btn_cancel")) != 1:
                return
            try:
                cc.statusline_uninstall(e["path"])
                rumps.alert(APP_TITLE, t("statusline_done_uninstall"))
            except Exception as ex:
                applog.warn("statusline_uninstall", ex)
                rumps.alert(APP_TITLE, t("statusline_failed", e=ex))
        else:
            if rumps.alert(APP_TITLE, t("statusline_confirm_install", path=sp, backup=cc.backup_path(e["path"])),
                           ok=t("btn_ok"), cancel=t("btn_cancel")) != 1:
                return
            try:
                backup = cc.statusline_install(e["path"], STATUSLINE_SH)
                rumps.alert(APP_TITLE, t("statusline_done_install", backup=backup))
            except Exception as ex:
                applog.warn("statusline_install", ex)
                rumps.alert(APP_TITLE, t("statusline_failed", e=ex))
        self.data.pop(entry_key(e), None)
        self.build_menu()
        self.refresh_async()

    def show_about(self, _sender=None):
        body = "\n\n".join([
            t("about_transparency"),
            t("about_reads"), t("mac_about_keychain"), t("about_sends"), t("about_stores"),
            t("tos_note"), t("unofficial_note"), t("mac_about_remove"), t("trademark_note"),
            t("mac_setup_hint", path=SETTINGS_PATH),
        ])
        rumps.alert(t("mac_about_title", version=__version__), body)

    def open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        subprocess.Popen(["/usr/bin/open", path])

    # ---------- 알림 ----------
    def check_alerts(self):
        for e in self.entries():
            u = (self.data.get(entry_key(e)) or {}).get("usage")
            if not u:
                continue
            for w in u["windows"]:
                step = max((s for s in ALERT_STEPS if w["pct"] >= s), default=0)
                k = (entry_key(e), w["key"])
                if step and self.alerted.get(k) != step:
                    self.notify(t("alert_limit", label=f"{get_provider(e['provider']).short} {e['label']}",
                                  window=w["key"], pct=f"{w['pct']:.0f}", reset=fmt_reset(w["resets_at"])))
                self.alerted[k] = step

    def notify(self, msg):
        try:
            rumps.notification(APP_TITLE, "", msg)
            return
        except Exception as e:                       # 번들(Info.plist) 없이는 NSUserNotification 을 못 쓴다
            applog.warn("rumps.notification unavailable, falling back to osascript", e)
        try:
            subprocess.run(["/usr/bin/osascript", "-e", "on run argv", "-e",
                            "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run",
                            msg, APP_TITLE], capture_output=True, timeout=10)
        except Exception as e:
            applog.warn("osascript notification", e)


def _forget(menu):
    """메뉴 트리의 NSMenuItem 들을 rumps 의 콜백 표(NSApp._ns_to_py_and_callback)에서 뺀다."""
    table = rumps.rumps.NSApp._ns_to_py_and_callback
    for item in list(menu.values()):
        if isinstance(item, rumps.MenuItem):
            _forget(item)
            table.pop(item._menuitem, None)
