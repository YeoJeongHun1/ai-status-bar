"""
rumps 앱 — 메뉴 막대 상태 항목 하나. Windows 판 StatusBar 와 같은 기능을 macOS 식으로:

- 제목 = [캐러셀 글리프][라벨][미니 막대][5h xx% · 7d xx%] … NSAttributedString (render.build_attributed).
- 3단계(막대+숫자 → 숫자만 → ›)와 넘침 정책(한 항목씩 슬라이드 / 숫자만+오른쪽 잘라 … / 접기 ›)은 settings_model.Overflow.
  쓸 수 있는 폭: 설정 max_width_pt 가 있으면 그것, 없으면 «자동» — 상태 항목의 창이 화면 왼쪽 밖(x<0)으로 밀리면 넘침으로 본다
  (macOS 는 메뉴 막대가 차면 왼쪽 항목부터 숨긴다). 조절 중엔 60초마다 원래 단계로 돌아갈 수 있는지 다시 재본다.
- 클릭 = 메뉴(상단에 항목 카드 = Windows 의 호버 카드) · ⌥클릭 = 다음 항목/새로고침(Windows 왼쪽 클릭) · ⌘클릭 = 새로고침 · ⇧클릭 = 설정.
- 조회는 백그라운드 스레드(polling.run_refresh), 결과 반영은 AppHelper.callAfter 로 메인 스레드에서.
- 80% / 95% 알림 1회, 넘침 조절 시작 알림(10분 간격). 설정 창은 settings_window.SettingsController.
"""
import os
import subprocess
import threading
import webbrowser
from datetime import datetime, timedelta

import objc
import rumps
from AppKit import NSApplication, NSEvent, NSObject, NSScreen
from Foundation import NSDistributedNotificationCenter, NSTimer
from PyObjCTools import AppHelper

import applog
import polling
from i18n import LANG_NAMES, SUPPORTED, current_language, set_language, t, tr_error
from providers import fmt_reset, get as get_provider
from providers import claude_code as cc
from version import __version__

from . import launchagent, render as R, settings_model as M, title as T
from .paths import APP_TITLE, LOG_DIR, OPEN_SETTINGS_NOTE, README_URL, SETTINGS_PATH, STATUSLINE_SH, SUPPORT_URL
from .settings import (BAR_STYLES, MODES, SLIDE_CHOICES, enabled_entries_of, ensure_discovered, entry_key,
                       load_settings, merge_discovered, save_settings)

POLL_SEC = polling.clamp_poll_sec(os.environ.get("AI_STATUS_BAR_POLL_SEC"))
OFFICIAL_POLL_SEC = 30
ALERT_STEPS = (80, 95)
WATCH_SEC = 5
NSApplicationActivationPolicyAccessory = 1
MOD_OPTION, MOD_COMMAND, MOD_SHIFT = 1 << 19, 1 << 20, 1 << 17


class _Delegate(NSObject):
    """메뉴 델리게이트(열릴 때 다시 만들기, 수식키 클릭) + 분산 알림(--setup) 수신."""

    def initWithApp_(self, app):
        self = objc.super(_Delegate, self).init()
        self.app = app
        return self

    def menuNeedsUpdate_(self, _menu):
        try:
            self.app.build_menu()
        except Exception as e:
            applog.warn("build_menu", e)

    def menuWillOpen_(self, menu):
        self.app.menu_open = True
        flags = NSEvent.modifierFlags()
        action = None
        if flags & MOD_SHIFT:
            action = lambda: self.app.open_settings()
        elif flags & MOD_COMMAND:
            action = lambda: self.app.refresh_async(manual=True)
        elif flags & MOD_OPTION:                          # Windows 왼쪽 클릭: 전환 모드면 다음 항목, 아니면 새로고침
            action = lambda: (self.app.next_entry() if self.app.switchable() else self.app.refresh_async(manual=True))
        if action:
            AppHelper.callAfter(menu.cancelTracking)
            AppHelper.callLater(0.05, action)

    def menuDidClose_(self, _menu):
        self.app.menu_open = False

    def openSettingsNote_(self, _note):
        self.app.open_settings()


class _Ticker(NSObject):
    """폴링 타이머 — rumps.Timer 는 start() 하자마자 한 번 발화하므로(설정 변경 때마다 즉시 조회 = 디바운스 우회) NSTimer 를 직접 쓴다.
    첫 발화는 interval 뒤. 즉시 조회가 필요하면 호출자가 refresh_async(manual=True) 를 부른다."""

    def initWithCallback_(self, cb):
        self = objc.super(_Ticker, self).init()
        self.cb = cb
        self.timer = None
        self.interval = None
        return self

    def fire_(self, _timer):
        try:
            self.cb()
        except Exception as e:
            applog.warn("ticker", e)

    @objc.python_method
    def start(self, interval):
        self.stop()
        self.interval = interval
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(interval, self, "fire:", None, True)

    @objc.python_method
    def stop(self):
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None


class MacStatusBar(rumps.App):
    def __init__(self, install_mode=False):
        super().__init__(APP_TITLE, title="…", quit_button=None)
        self.settings = load_settings()
        set_language(self.settings["language"])
        if ensure_discovered(self.settings):
            save_settings(self.settings)
        self.install_mode = install_mode
        self.data = {}
        self.info_cache = {}                   # entry_key → provider.info() — 폴링 스레드에서만 갱신 (키체인 -w 는 메인 스레드에서 부르지 않는다)
        self.backoff = polling.Backoff()
        self.debounce = polling.Debounce()
        self._lock = threading.Lock()
        self.cur = 0
        self.alerted = {}
        self.menu_open = False
        self.overflow = M.Overflow()
        self.clip_w = None
        self._auto_available = None            # 자동 감지로 잰 «쓸 수 있는 폭» (None = 아직 넘친 적 없음)
        self._last_probe = None
        self.settings_ctl = None
        self._delegate = _Delegate.alloc().initWithApp_(self)
        self._menu._menu.setDelegate_(self._delegate)
        self.poll_timer = _Ticker.alloc().initWithCallback_(self._on_poll)
        self.slide_timer = rumps.Timer(self._on_slide, self.settings["slide_sec"])
        self.watch_timer = rumps.Timer(self._on_watch, WATCH_SEC)
        self.build_menu()
        self.update_title()

    # ---------- 실행 ----------
    def run(self, **options):
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)   # Dock 아이콘 없음
        NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self._delegate, "openSettingsNote:", OPEN_SETTINGS_NOTE, None)
        self.poll_timer.start(self.poll_sec())
        self.refresh_async()              # 첫 조회
        self.watch_timer.start()
        self.sync_slide_timer()
        if self.install_mode:
            AppHelper.callLater(0.5, lambda: self.open_settings(install_mode=True))
        super().run(**options)

    def official(self):
        return self.settings["data_source"] == "official"

    def poll_sec(self):
        return OFFICIAL_POLL_SEC if self.official() else POLL_SEC

    def entries(self, settings=None):
        return enabled_entries_of(settings or self.settings)

    def effective_mode(self, settings=None):
        """실제 표시 모드 — 넘쳐서 임시 슬라이드 중이면 slide."""
        S = settings or self.settings
        if S is self.settings and self.overflow.adjusted == "slide" and S["display_mode"] == "all":
            return "slide"
        return S["display_mode"]

    def visible(self):
        return T.pick_visible(self.entries(), self.effective_mode(), self.cur, self.settings["fixed_entry"], entry_key)

    def switchable(self):
        return self.effective_mode() in ("click", "slide") and len(self.entries()) > 1

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
            for d in self.data.values():                       # 오류 문자열에 토큰·경로가 섞여도 화면·로그엔 가린 것만
                if d.get("error"):
                    d["error"] = applog.mask(d["error"])
            for e in entries:                                  # 연결 상태(플랜·만료) — 백오프 중이면 키체인을 다시 두드리지 않는다
                k = entry_key(e)
                if self.backoff.blocked(k):
                    continue
                try:
                    self.info_cache[k] = get_provider(e["provider"]).info(e["path"])
                except Exception as ex:
                    self.info_cache[k] = {"connected": False, "reason": f"err_token_read {applog.mask(ex)}", "plan": None, "expires_at": None}
        except Exception as ex:
            applog.warn("_refresh", ex)
        finally:
            self._lock.release()
        AppHelper.callAfter(self.after_refresh)

    UNCHECKED = {"connected": False, "reason": "", "plan": None, "expires_at": None, "unchecked": True}

    def info_for(self, e):
        """캐시된 provider.info() — UI(메인 스레드)는 이것만 본다. 아직 없으면 «미확인»."""
        return self.info_cache.get(entry_key(e), self.UNCHECKED)

    def after_refresh(self):
        self.update_title()
        if not self.menu_open:
            self.build_menu()
        self.check_alerts()
        if self.settings_ctl is not None:
            self.settings_ctl.on_data_refreshed()

    # ---------- 제목 ----------
    def runs_for(self, settings, entries, data, tier, cur, mode=None):
        """설정·항목·데이터·단계 → 제목 조각. 설정 창 미리보기도 이 함수를 쓴다 (저장된 설정과 무관한 임시 설정으로)."""
        mode = mode or (self.effective_mode(settings) if settings is self.settings else settings["display_mode"])
        vis = T.pick_visible(entries, mode, cur, settings["fixed_entry"], entry_key)
        prefix = M.indicator_prefix(settings["switch_indicator"], cur, len(entries)) if mode in ("click", "slide") else ""
        return T.build_runs(vis, data, entry_key, settings["style"]["label"], settings["show_scoped"],
                            t("mac_title_no_entries"), bars=T.want_bars(settings["style"]["bars"]), tier=tier, prefix=prefix)

    def measure(self, runs):
        try:
            return R.width_of(runs)
        except Exception as e:
            applog.warn("measure", e)
            return float(len(T.plain(runs))) * 7.0

    def available_width(self, settings=None):
        S = settings or self.settings
        if S.get("max_width_pt"):
            return float(S["max_width_pt"])
        return self._auto_available

    def update_title(self):
        S = self.settings
        ents = self.entries()
        before = self.overflow.adjusted
        tier, adjusted, notify = self.overflow.decide(
            lambda tr: self.measure(self.runs_for(S, ents, self.data, tr, 0, mode="all" if S["display_mode"] == "all" else None)),
            self.available_width(), S, len(ents))
        if before != adjusted:
            self.cur = 0
            self.sync_slide_timer()
        runs = self.runs_for(S, ents, self.data, tier, self.cur)
        avail = self.available_width()
        if adjusted == "numbers" and avail is not None:
            runs = M.clip_runs(runs, self.measure, avail)
        text = T.plain(runs)
        self.title = text
        try:
            self._apply_attributed(runs)
        except Exception as e:
            applog.warn("attributed title", e)
            self.title = T.with_dots(runs)
        if notify:
            self.notify(t(f"notify_overflow_{adjusted}"))
        if adjusted and not before:
            self._last_probe = datetime.now()

    def _apply_attributed(self, runs):
        nsapp = getattr(self, "_nsapp", None)
        if nsapp is None:                     # run() 전 — 아직 상태 항목이 없다
            return
        attr = R.build_attributed(runs, label_color=R.color_from_hex(self.settings["style"]["label_color"]))
        nsapp.nsstatusitem.button().setAttributedTitle_(attr)
        if os.environ.get("AI_STATUS_BAR_DEBUG"):
            print("title:", T.plain(runs), "| attributed:", R.describe_attributed(attr),
                  "| tier:", self.overflow.tier, "adjusted:", self.overflow.adjusted, flush=True)

    # ---------- 넘침 감시 (Windows 의 watch/periodic_measure) ----------
    def item_frame(self):
        try:
            return self._nsapp.nsstatusitem.button().window().frame()
        except Exception:
            return None

    def _on_watch(self, _timer=None):
        if self.settings.get("max_width_pt") or getattr(self, "_nsapp", None) is None:
            return
        fr = self.item_frame()
        if fr is None:
            return
        x, w = float(fr.origin.x), float(fr.size.width)
        screen_x = float(NSScreen.screens()[0].frame().origin.x) if NSScreen.screens() else 0.0
        if x < screen_x:                                   # 화면 밖으로 밀렸다 → 지금 폭 - 넘친 만큼이 쓸 수 있는 폭
            self._auto_available = max(20.0, w - (screen_x - x) - 1)
            self.update_title()
        elif self.overflow.adjusted and self._last_probe and datetime.now() - self._last_probe >= timedelta(seconds=M.OVERFLOW_PROBE_SEC):
            self._last_probe = datetime.now()
            self._auto_available = None                    # 원래 단계로 그려 보고 0.1초 뒤 다시 확인한다
            self.update_title()
            AppHelper.callLater(0.15, self._probe_check)

    def _probe_check(self):
        fr = self.item_frame()
        if fr is None:
            return
        screen_x = float(NSScreen.screens()[0].frame().origin.x) if NSScreen.screens() else 0.0
        if float(fr.origin.x) < screen_x:
            self._auto_available = max(20.0, float(fr.size.width) - (screen_x - float(fr.origin.x)) - 1)
            self.update_title()

    # ---------- 슬라이드 ----------
    def sync_slide_timer(self):
        want = self.effective_mode() == "slide" and len(self.entries()) > 1
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
            if not self.menu_open:
                self.build_menu()

    def go_to(self, i):
        self.cur = i % max(1, len(self.entries()))
        self.update_title()

    # ---------- 메뉴 ----------
    def build_menu(self):
        m = self.menu
        _forget(m)                                # rumps 는 콜백 표를 지우지 않는다 — 다시 만들 때마다 새기 때문에 우리가 지운다
        m.clear()
        n = [0]

        def add(item, parent=m):
            n[0] += 1
            parent[f"_{n[0]}"] = item             # 제목이 같은 행이 있어도 지워지지 않게 키를 따로 준다
            return item

        def sep(parent=m):
            add(rumps.separator, parent)

        ents = self.entries()
        vis_keys = {entry_key(e) for e in self.visible()}
        if not ents:
            add(rumps.MenuItem(t("mac_no_entries"), callback=lambda _: self.open_settings(tab=0)))
        for i, e in enumerate(ents):
            item = rumps.MenuItem("", callback=lambda _, i=i: self.card_clicked(i))
            try:
                item._menuitem.setImage_(self.card_for(e, highlighted=(entry_key(e) in vis_keys and self.switchable())))
            except Exception as ex:
                applog.warn("card_image", ex)
                for line in self.detail_lines(e):
                    add(rumps.MenuItem(line))
                continue
            add(item)
        sep()
        add(rumps.MenuItem(t("menu_settings"), callback=lambda _: self.open_settings(), key=","))
        if self.switchable():
            add(rumps.MenuItem(t("menu_next"), callback=self.next_entry))
        add(rumps.MenuItem(t("menu_refresh"), callback=lambda _: self.refresh_async(manual=True), key="r"))
        add(rumps.MenuItem(t("btn_rescan"), callback=self.rescan))
        pages = add(rumps.MenuItem(t("mac_menu_usage_pages")))
        for p in (get_provider("claude_code"), get_provider("codex")):
            add(rumps.MenuItem(t("menu_usage_page", name=p.name), callback=lambda _, p=p: webbrowser.open(p.usage_page)), pages)
        sep()
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
        bars = add(rumps.MenuItem(t("mac_menu_bars")))
        for style in BAR_STYLES:
            it = add(rumps.MenuItem(t("mac_bars_auto") if style == "auto" else t(f"style_bars_{style}"),
                                    callback=lambda _, style=style: self.set_bars(style)), bars)
            it.state = 1 if self.settings["style"]["bars"] == style else 0
        it = add(rumps.MenuItem(t("mac_menu_label"), callback=lambda _: self.toggle("style.label")))
        it.state = 1 if self.settings["style"]["label"] else 0
        it = add(rumps.MenuItem(t("mac_menu_scoped"), callback=lambda _: self.toggle("show_scoped")))
        it.state = 1 if self.settings["show_scoped"] else 0
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
                                   callback=lambda _, e=e: self.toggle_statusline(e["path"])), ds)
        it = add(rumps.MenuItem(t("mac_menu_autostart"), callback=self.toggle_autostart))
        it.state = 1 if launchagent.is_enabled() else 0
        lang = add(rumps.MenuItem(t("mac_menu_language")))
        for code in ("auto",) + SUPPORTED:
            it = add(rumps.MenuItem(t("lang_auto") if code == "auto" else LANG_NAMES[code],
                                    callback=lambda _, code=code: self.set_language(code)), lang)
            it.state = 1 if self.settings["language"] == code else 0
        sep()
        add(rumps.MenuItem(t("mac_menu_about"), callback=lambda _: self.open_settings(tab=4)))
        add(rumps.MenuItem(t("btn_open_logs"), callback=lambda _: self.open_folder(LOG_DIR)))
        add(rumps.MenuItem(t("menu_readme"), callback=lambda _: webbrowser.open(README_URL)))
        add(rumps.MenuItem(t("menu_support"), callback=lambda _: webbrowser.open(SUPPORT_URL)))
        sep()
        add(rumps.MenuItem(t("menu_quit"), callback=lambda _: rumps.quit_application(), key="q"))

    def card_for(self, e, highlighted=False):
        plan = self.info_for(e).get("plan")
        return R.card_image(e, self.data.get(entry_key(e)), plan, self.settings["show_scoped"], self.official(), highlighted)

    def card_clicked(self, i):
        """카드 클릭 — 전환 모드면 그 항목으로(페이지 점 클릭), 아니면 설정 «항목» 탭."""
        if self.switchable():
            self.go_to(i)
        else:
            self.open_settings(tab=0)

    def detail_lines(self, e):
        """카드 이미지를 못 그릴 때의 글자 폴백."""
        p = get_provider(e["provider"])
        d = self.data.get(entry_key(e)) or {}
        plan = self.info_for(e).get("plan") or ""
        lines = [f"{p.name} · {e['label']}" + (f" · {plan}" if plan else "")]
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
    def apply_settings(self, new, autostart=None):
        """설정 창 «저장» / 메뉴 즉시 변경 공통: 저장 → 언어·타이머·넘침 상태 리셋 → 제목·메뉴 → 조회(10초 디바운스)."""
        self.settings = new
        try:
            save_settings(self.settings)
        except Exception as e:
            applog.warn("save_settings", e)
        if autostart is not None:
            try:
                if autostart and not launchagent.is_enabled():
                    launchagent.enable(start=False)
                elif not autostart and launchagent.is_enabled():
                    launchagent.disable(unload=False)
            except Exception as e:
                applog.warn("autostart", e)
                rumps.alert(APP_TITLE, t("autostart_failed", e=e))
        prev_lang = current_language()
        set_language(new["language"])             # 같은 dict 를 넘겨도(메뉴 즉시 변경) 실제 언어가 바뀌었는지로 판단한다
        lang_changed = current_language() != prev_lang
        self.cur = 0
        self.overflow = M.Overflow()
        self._auto_available = None
        if self.poll_timer.timer is not None and self.poll_timer.interval != self.poll_sec():
            self.poll_timer.start(self.poll_sec())          # 주기만 바꾼다 — 즉시 발화 없음
        self.sync_slide_timer()
        self.update_title()
        if not self.menu_open:
            self.build_menu()
        self.refresh_async(manual=True)           # 수동 새로고침과 같은 10초 디바운스
        return lang_changed

    def save(self):
        self.apply_settings(self.settings)

    def set_mode(self, mode):
        self.settings["display_mode"] = mode
        self.save()

    def set_slide_sec(self, sec):
        self.settings["slide_sec"] = int(sec)
        self.save()

    def set_bars(self, style):
        self.settings["style"]["bars"] = style
        self.save()

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

    def set_language(self, code):
        self.settings["language"] = code
        self.save()

    def rescan(self, _sender=None):
        added = merge_discovered(self.settings["entries"])
        self.save()
        rumps.alert(APP_TITLE, t("rescan_found", n=added) if added else t("rescan_none"))

    def toggle_autostart(self, _sender=None):
        self.apply_settings(self.settings, autostart=not launchagent.is_enabled())

    def toggle_statusline(self, path):
        """그 계정 폴더의 settings.json 에 statusLine 내보내기를 설치/해제 — 확인 대화상자 뒤에."""
        sp = cc.settings_path(path)
        try:
            if cc.statusline_installed(path):
                if rumps.alert(APP_TITLE, t("statusline_confirm_uninstall", path=sp), ok=t("btn_ok"), cancel=t("btn_cancel")) != 1:
                    return
                cc.statusline_uninstall(path)
                rumps.alert(APP_TITLE, t("statusline_done_uninstall"))
            else:
                if rumps.alert(APP_TITLE, t("statusline_confirm_install", path=sp, backup=cc.backup_path(path)),
                               ok=t("btn_ok"), cancel=t("btn_cancel")) != 1:
                    return
                backup = cc.statusline_install(path, STATUSLINE_SH)
                rumps.alert(APP_TITLE, t("statusline_done_install", backup=backup))
        except Exception as ex:
            applog.warn("statusline toggle", ex)
            rumps.alert(APP_TITLE, t("statusline_failed", e=ex))
        for e in self.settings["entries"]:
            if e["path"] == path:
                self.data.pop(entry_key(e), None)
        self.refresh_async()

    # ---------- 설정 창 / 도움말 ----------
    def open_settings(self, _sender=None, install_mode=False, tab=0):
        if self.settings_ctl is None:
            from .settings_window import SettingsController
            self.settings_ctl = SettingsController.alloc().initWithApp_(self)
        self.settings_ctl.show(install_mode=install_mode, tab=tab)

    def open_help(self):
        from .settings import PROVIDERS
        body = [t("help_intro")]
        for p in PROVIDERS:
            body.append(f"■ {p.name}\n" + t(p.help_key))
        body.append(f"■ {t('mac_help_keychain_title')}\n" + t("mac_about_keychain"))
        body.append(f"■ {t('help_multi_title')}\n" + t("help_multi_body"))
        rumps.alert(t("help_title"), "\n\n".join(body))

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


# 하위 호환(검사 스크립트): render 로 옮긴 함수들
build_attributed = R.build_attributed
describe_attributed = R.describe_attributed
