"""
AI Status Bar — Windows 작업 표시줄의 **빈 공간**에 AI 구독 사용량(5시간 / 주간 한도)을 상시 표시한다.
제공자: Claude Code · Codex (ChatGPT). 제공자 = providers/ 의 모듈 하나, 계정 = 그 CLI 의 로그인 폴더 하나.

    Claude work   5h ▬▬▬░░░░░ 23% ↺12:09   │  Codex work   5h ▬░░░░░░░ 4% ↺17:10
                  7d ▬▬▬▬▬░░░ 66% ↺09/01     │               7d ▬▬░░░░░░ 12% ↺09/03

- 배경 투명(글자·막대만 그려지고 나머지는 클릭도 아래로 통과). 빈 공간을 실측해 가장 왼쪽 빈 곳에 놓는다.
- 우리 창은 캡처에서 제외(WDA_EXCLUDEFROMCAPTURE)돼 재측정 때 숨기지 않는다 → 깜빡이지 않는다.
- 전체화면 앱이 앞에 있으면 숨긴다. 트레이 '^' 안에 아이콘(설정·새로고침·종료). 작업 표시줄 버튼은 없다.
- 항목(entry) = 제공자 × 계정. 표시 방식: 모두 동시에 / 클릭으로 전환 / 자동 슬라이드 / 하나 고정.
- 바에는 «필요한 정보만»: 5h/7d 막대·%·리셋 시각. 서비스·계정·플랜·마지막 조회는 **마우스를 올리면 툴팁** 으로.
- 스타일: 계정 라벨 on/off(기본 off), 막대 «자동/막대+숫자/숫자만», 라벨 색. 설정 창에 라이브 미리보기 + 프리셋.
- 데이터 원본: 비공식 API (5분마다) / 공식 모드 (Claude Code 상태줄 데이터만, 네트워크 0).
- 다국어: ko · en · ja · pt-BR · es (i18n.py). 설정은 %LOCALAPPDATA%\\AIStatusBar\\settings.json.

실행:  pythonw ai_status_bar.py        필요 패키지: pillow · pystray · pywin32 (exe 는 아무것도 필요 없음)
"""
import json
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import colorchooser, filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taskbar as tb                                                      # noqa: E402
from i18n import LANG_NAMES, SUPPORTED, set_language, t, tr_error         # noqa: E402
from providers import all_providers, color_for, draw_icon, fmt_reset, get as get_provider, summary  # noqa: E402
from providers import claude_code as cc                                   # noqa: E402

__version__ = "1.1.0"
APP_TITLE = "AI Status Bar"
APP_NAME = "AIStatusBar"                          # exe 이름 · 설정 폴더 이름
REPO_URL = "https://github.com/YeoJeongHun1/ai-status-bar"
README_URL = REPO_URL + "#readme"
SUPPORT_URL = "https://github.com/sponsors/YeoJeongHun1"

POLL_SEC = int(os.environ.get("AI_STATUS_BAR_POLL_SEC", "300"))   # API 모드 조회 주기
OFFICIAL_POLL_SEC = 30                                            # 공식 모드는 로컬 파일만 읽으므로 자주 봐도 된다
ALERT_STEPS = (80, 95)
MARGIN = 16             # 빈 구간 양끝에서 띄우는 여백(px, DPI 배율 전 기준)
REMEASURE_SEC = 120     # 아무 변화 없어도 이 주기로 다시 잰다
POPUP_SEC = 12          # 상세 팝업 자동 닫힘

FROZEN = getattr(sys, "frozen", False)
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(BASE_DIR, "app.ico")
PS1_PATH = os.path.join(BASE_DIR, "statusline_export.ps1")
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
CONFIG_DIR = os.path.join(LOCALAPPDATA, APP_NAME)
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
OLD_SETTINGS_PATH = os.path.join(LOCALAPPDATA, "ClaudeStatusBar", "settings.json")   # 이전 이름(Claude Status Bar)에서 이전
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_LNK = os.path.join(STARTUP_DIR, "AI Status Bar.lnk")
OLD_STARTUP_LNK = os.path.join(STARTUP_DIR, "Claude Status Bar.lnk")
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))   # 풀어 둔 그 자리
MODES = ("all", "click", "slide", "fixed")
BAR_STYLES = ("auto", "bars", "numbers")
DEFAULT_SETTINGS = {
    "entries": [],               # [{"provider", "path", "label", "enabled", "windows": {"5h": True, "7d": True}}]
    "display_mode": "all",       # all = 모두 동시에 / click = 클릭으로 전환 / slide = 자동 슬라이드 / fixed = 하나 고정
    "slide_sec": 30,
    "fixed_entry": "",           # "provider|path"
    "show_scoped": True,         # 모델별 한도 (Claude: Fable 등)
    "style": {"label": False, "bars": "auto", "label_color": ""},
    "language": "auto",
    "data_source": "api",        # api = 비공식 API / official = 상태줄 데이터만 (네트워크 0)
    "official_hide_unsupported": True,
    "seen_providers": [],        # 자동 탐색을 한 번 돌린 제공자 — 새 제공자가 추가되면 그것만 한 번 더 탐색한다
}
PROVIDERS = all_providers()


def entry_key(e):
    return f"{e['provider']}|{e['path']}"


# ---------- 설정 ----------

def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    raw = None
    for path in (SETTINGS_PATH, OLD_SETTINGS_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            break
        except Exception:
            continue
    if not raw:
        return s
    if raw.get("display_mode") in MODES:
        s["display_mode"] = raw["display_mode"]
    elif raw.get("display_mode") == "cycle":                 # 이전 이름의 «한 계정씩»
        s["display_mode"] = "slide" if raw.get("cycle_on") else "click"
    for src in ("slide_sec", "cycle_sec"):
        if isinstance(raw.get(src), (int, float)):
            s["slide_sec"] = max(5, min(3600, int(raw[src])))
            break
    if isinstance(raw.get("fixed_entry"), str):
        s["fixed_entry"] = raw["fixed_entry"]
    if "show_scoped" in raw:
        s["show_scoped"] = bool(raw["show_scoped"])
    st = raw.get("style") or {}
    s["style"]["label"] = bool(st.get("label", False))          # v1.0 의 badge/mark 키는 버린다 (마크는 더 쓰지 않는다)
    if st.get("bars") in BAR_STYLES:
        s["style"]["bars"] = st["bars"]
    v = st.get("label_color") or ""
    s["style"]["label_color"] = v if isinstance(v, str) and v.startswith("#") and len(v) == 7 else ""
    if raw.get("language") in ("auto",) + SUPPORTED:
        s["language"] = raw["language"]
    if raw.get("data_source") in ("api", "official"):
        s["data_source"] = raw["data_source"]
    if "official_hide_unsupported" in raw:
        s["official_hide_unsupported"] = bool(raw["official_hide_unsupported"])
    s["seen_providers"] = [x for x in (raw.get("seen_providers") or []) if isinstance(x, str)]
    entries = []
    old_windows = {"5h": bool(raw.get("show_5h", True)), "7d": bool(raw.get("show_7d", True))}
    for a in raw.get("entries") or []:
        if isinstance(a, dict) and a.get("path") and get_provider(a.get("provider", "")):
            wins = a.get("windows") if isinstance(a.get("windows"), dict) else {}
            entries.append({"provider": a["provider"], "path": str(a["path"]),
                            "label": str(a.get("label") or get_provider(a["provider"]).label(a["path"])),
                            "enabled": bool(a.get("enabled", True)),
                            "windows": {k: bool(v) for k, v in wins.items()}})
    for a in raw.get("accounts") or []:                      # 이전 이름의 계정 목록 → Claude Code 항목
        if isinstance(a, dict) and a.get("path"):
            entries.append({"provider": "claude_code", "path": str(a["path"]),
                            "label": str(a.get("label") or get_provider("claude_code").label(a["path"])),
                            "enabled": bool(a.get("enabled", True)), "windows": dict(old_windows)})
    s["entries"] = entries
    return s


def save_settings(s):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def merge_discovered(entries, providers=None):
    """제공자들을 자동 탐색해 목록에 없는 계정을 뒤에 붙인다. 새로 붙은 개수를 돌려준다."""
    known = {(e["provider"], os.path.normcase(os.path.abspath(e["path"]))) for e in entries}
    added = 0
    for p in providers or PROVIDERS:
        for d in p.discover():
            if (p.id, os.path.normcase(d)) not in known:
                entries.append({"provider": p.id, "path": d, "label": p.label(d), "enabled": True, "windows": {}})
                added += 1
    return added


def migrate_old_shortcut():
    """이전 이름의 시작프로그램 바로가기가 있으면 지우고 새 이름으로 다시 건다."""
    if os.path.exists(OLD_STARTUP_LNK):
        try:
            os.remove(OLD_STARTUP_LNK)
            set_autostart(True)
        except Exception:
            pass


# ---------- 위젯 ----------

class StatusBar:
    def __init__(self, install_mode=False):
        self.scale = tb.make_dpi_aware()
        self.settings = load_settings()
        set_language(self.settings["language"])
        # 처음 보는 제공자만 자동 탐색한다 (사용자가 지운 계정을 매번 되살리지 않도록)
        new_providers = [p for p in PROVIDERS if p.id not in self.settings["seen_providers"]]
        if new_providers:
            merge_discovered(self.settings["entries"], new_providers)
            self.settings["seen_providers"] = [p.id for p in PROVIDERS]
            save_settings(self.settings)
        migrate_old_shortcut()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-toolwindow", True)     # 작업 표시줄 버튼("tk")을 만들지 않는다
        self.root.tk.call("tk", "scaling", self.scale * 96 / 72)
        self.data = {}                                # entry key -> {"usage", "error", "last_ok", "saved_at"}
        self.cur = 0                                  # click/slide 모드에서 지금 보이는 항목 번호
        self.cycle_job = None
        self.alerted = {}
        self.popup = None
        self.settings_win = None
        self.help_win = None
        self._ov = None                               # 미리보기용 오버라이드 {"settings","entries","data"}
        self.mode = "full"
        self.signature = None
        self.gap = (0, 0)
        self.gaps = []
        self.was_locked = False
        self.hidden_fullscreen = False
        self.bg = (32, 32, 32)
        self.set_palette(self.bg)
        self.calls = queue.Queue()                   # 다른 스레드(조회·트레이) → 메인 루프로 넘기는 일감

        _, top, _, bottom = tb.win_rect(tb.taskbar())
        self.h = bottom - top
        self.canvas = tk.Canvas(self.root, width=10, height=self.h, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_left)
        self.canvas.bind("<Button-3>", self.on_right)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)
        self.tooltip = None
        self.tooltip_job = None
        self.tooltip_entry = None
        self.entry_spans = []                          # [(x0, x1, entry)] — 툴팁 히트 테스트용
        self._tags = ()
        self.menu = self.build_menu()

        self.root.withdraw()
        self.root.update_idletasks()
        self.hwnd = tb.user32.GetParent(self.root.winfo_id())
        tb.make_toolwindow(self.hwnd)
        self.capture_excluded = tb.exclude_from_capture(self.hwnd)

        self.tray = None
        self.started = False
        self.start_tray()
        self.root.after(200, self.pump)
        if install_mode:
            self.open_settings(install_mode=True)
        else:
            self.start()

    def start(self):
        self.started = True
        self.relayout(force=True)
        self.refresh_async()
        self.schedule_cycle()
        self.root.after(2000, self.watch)
        self.root.after(self.poll_ms(), self.tick)
        self.root.after(REMEASURE_SEC * 1000, self.periodic_measure)

    def cfg(self):
        """그리기에 쓰는 설정 — 미리보기 중이면 폼의 임시 설정."""
        return self._ov["settings"] if self._ov else self.settings

    def official(self):
        return self.cfg()["data_source"] == "official"

    def poll_ms(self):
        return (OFFICIAL_POLL_SEC if self.official() else POLL_SEC) * 1000

    def build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=t("menu_settings"), command=self.open_settings)
        m.add_command(label=t("menu_next"), command=self.next_entry)
        m.add_command(label=t("menu_refresh"), command=self.refresh_async)
        m.add_command(label=t("menu_remeasure"), command=lambda: self.relayout(force=True))
        for p in PROVIDERS:
            m.add_command(label=t("menu_usage_page", name=p.name), command=lambda p=p: webbrowser.open(p.usage_page))
        m.add_separator()
        m.add_command(label=t("menu_readme"), command=lambda: webbrowser.open(README_URL))
        m.add_command(label=t("menu_support"), command=lambda: webbrowser.open(SUPPORT_URL))
        m.add_separator()
        m.add_command(label=t("menu_quit"), command=self.quit)
        return m

    # --- 항목 ---
    def enabled_entries(self):
        out = []
        S = self.cfg()
        for e in (self._ov["entries"] if self._ov else S["entries"]):
            if not e["enabled"]:
                continue
            p = get_provider(e["provider"])
            if not p:
                continue
            if self.official() and not p.supports_official and S["official_hide_unsupported"]:
                continue
            out.append(e)
        return out

    def visible_entries(self):
        """지금 바에 그릴 항목들."""
        ents = self.enabled_entries()
        if not ents:
            return []
        S = self.cfg()
        mode = S["display_mode"]
        if mode == "fixed":
            for e in ents:
                if entry_key(e) == S["fixed_entry"]:
                    return [e]
            return [ents[0]]
        if mode in ("click", "slide"):
            if self._ov:
                return [ents[0]]
            self.cur %= len(ents)
            return [ents[self.cur]]
        return ents

    def switchable(self):
        return self.cfg()["display_mode"] in ("click", "slide") and len(self.enabled_entries()) > 1

    def next_entry(self):
        if self.switchable():
            self.cur = (self.cur + 1) % len(self.enabled_entries())
            self.relayout()
        self.schedule_cycle()

    def schedule_cycle(self):
        if self.cycle_job:
            self.root.after_cancel(self.cycle_job)
            self.cycle_job = None
        if self.settings["display_mode"] == "slide" and len(self.enabled_entries()) > 1:
            self.cycle_job = self.root.after(self.settings["slide_sec"] * 1000, self.next_entry)

    # --- 다른 스레드에서 온 일감을 메인 루프에서 처리 ---
    def call_soon(self, fn):
        self.calls.put(fn)

    def pump(self):
        try:
            while True:
                self.calls.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    # --- 트레이 아이콘 ('^' 안) ---
    def start_tray(self):
        try:
            import pystray
        except ImportError:
            return
        M = pystray.MenuItem
        menu = pystray.Menu(
            M(lambda _: self.tray_status(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            M(lambda _: t("menu_settings"), lambda: self.call_soon(self.open_settings), default=True),
            M(lambda _: t("menu_next"), lambda: self.call_soon(self.next_entry)),
            M(lambda _: t("menu_refresh"), lambda: self.call_soon(self.refresh_async)),
            M(lambda _: t("menu_readme"), lambda: webbrowser.open(README_URL)),
            pystray.Menu.SEPARATOR,
            M(lambda _: t("menu_quit"), lambda: self.call_soon(self.quit)),
        )
        self.tray = pystray.Icon("ai-status-bar", draw_icon(None), APP_TITLE, menu=menu)
        self.tray.run_detached()

    def tray_status(self):
        ents = self.enabled_entries()
        if not ents:
            return t("tray_no_entries")
        parts = []
        for e in ents:
            d = self.data.get(entry_key(e)) or {}
            name = f"{get_provider(e['provider']).short} {e['label']}"
            if d.get("error"):
                parts.append(f"{name}: ⚠ {tr_error(d['error'])[:40]}")
            elif d.get("usage"):
                parts.append(f"{name}: {summary(d['usage'])}")
            else:
                parts.append(f"{name}: {t('bar_loading')}")
        return " | ".join(parts)

    def update_tray(self):
        if not self.tray:
            return
        try:
            first = self.visible_entries()[:1]
            d = self.data.get(entry_key(first[0])) if first else None
            self.tray.icon = draw_icon(d and d.get("usage"), error=bool(d and d.get("error")))
            self.tray.title = f"{APP_TITLE} — {self.tray_status()}"[:127]
            self.tray.update_menu()
        except Exception:
            pass

    # --- 색: 배경 밝기에 따라 글자색을 고른다 (다크/라이트 작업 표시줄 둘 다) ---
    def set_palette(self, bg):
        self.bg = bg
        self.key = "#%02x%02x%02x" % bg
        dark = sum(bg) / 3 < 128
        self.fg = "#f0f0f0" if dark else "#101010"
        self.dim = "#a0a0a0" if dark else "#606060"
        self.track = "#404040" if dark else "#c8c8c8"
        self.line = "#505050" if dark else "#b0b0b0"

    # --- 배치 ---
    def tiers(self, settings=None):
        return {"auto": ("full", "compact", "collapsed"), "bars": ("full", "collapsed"),
                "numbers": ("compact", "collapsed")}[(settings or self.settings)["style"]["bars"]]

    def relayout(self, force=False):
        """빈 공간을 (필요하면 다시) 재고, 들어가는 가장 큰 모드로 그린 뒤 그 자리에 놓는다."""
        if tb.session_locked():
            self.was_locked = True
            return
        if self.hidden_fullscreen:
            return
        sig = tb.taskbar_signature()
        m = int(MARGIN * self.scale)
        if force or sig != self.signature:
            self.signature = sig
            if not self.capture_excluded:            # 옛 Windows: 잠깐 숨겨야 우리 자신이 안 찍힌다
                self.root.withdraw()
                self.root.update()
                self.root.after(60)
            gaps, bg = tb.measure_free_gaps(min_width=self.px(24) + 2 * m)
            self.gaps = [(x0 + m, x1 - m) for x0, x1 in gaps]
            self.set_palette(bg)
            self.canvas.configure(bg=self.key)
            self.root.configure(bg=self.key)
            self.root.attributes("-transparentcolor", self.key)
        need = self.px(24)
        self.gap = self.gaps[0] if self.gaps else (m, m + need)
        for mode in self.tiers():
            self.mode = mode
            need = self.draw()
            fits = [g for g in self.gaps if g[1] - g[0] >= need]
            if fits:
                self.gap = fits[0]
                break
        self.canvas.configure(width=need)
        _, top, _, _ = tb.win_rect(tb.taskbar())
        tb.place(self.hwnd, self.gap[0], top, need, self.h)
        self.root.deiconify()

    def watch(self):
        """2초마다: 잠금·전체화면·작업 표시줄 변화를 보고 필요한 만큼만 손댄다."""
        try:
            if tb.session_locked():
                self.was_locked = True
            elif tb.fullscreen_app_active():
                if not self.hidden_fullscreen:
                    self.hidden_fullscreen = True
                    self.root.withdraw()
            elif self.hidden_fullscreen or self.was_locked:
                self.hidden_fullscreen = self.was_locked = False
                self.relayout(force=True)
            elif tb.taskbar_signature() != self.signature:
                self.relayout()
            else:
                tb.raise_topmost(self.hwnd)
        except Exception:
            pass
        self.root.after(2000, self.watch)

    def periodic_measure(self):
        if not self.hidden_fullscreen:
            self.relayout(force=True)
        self.root.after(REMEASURE_SEC * 1000, self.periodic_measure)

    # --- 데이터 ---
    def tick(self):
        self.refresh_async()
        self.root.after(self.poll_ms(), self.tick)

    def refresh_async(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        official = self.official()          # 공식 모드는 네트워크 코드를 한 줄도 타지 않는다 (fetch 미호출)
        for e in list(self.enabled_entries()):
            p = get_provider(e["provider"])
            d = self.data.setdefault(entry_key(e), {"usage": None, "error": None, "last_ok": None, "saved_at": None})
            try:
                if official:
                    d["usage"], d["saved_at"] = p.fetch_official(e["path"])
                else:
                    d["usage"] = p.fetch(e["path"])
                    d["saved_at"] = None
                d["error"] = None
                d["last_ok"] = d["usage"]["fetched_at"]
            except Exception as ex:
                d["error"] = str(ex)[:80]
        self.call_soon(self.after_refresh)

    def after_refresh(self):
        self.relayout()
        self.update_tray()
        self.check_alerts()
        if self.settings_win:
            self.fill_status()

    # --- 그리기: 필요한 폭(px)을 돌려준다 ---
    def px(self, v):
        return int(v * self.scale)

    def font(self, size, bold=False):
        return ("Segoe UI Semibold" if bold else "Segoe UI", size)

    def text(self, c, x, y, s, fill, font, gap=5, tags=()):
        item = c.create_text(x, y, text=s, fill=fill, font=font, anchor="w", tags=tags or self._tags)
        return c.bbox(item)[2] + self.px(gap)

    def entry_windows(self, e, usage):
        return [w for w in usage["windows"] if e["windows"].get(w["key"], True)]

    def draw(self, canvas=None, mode=None, height=None, entries=None):
        c = canvas or self.canvas
        mode = mode or self.mode
        h = height or self.h
        c.delete("all")
        if mode == "collapsed":
            c.create_text(self.px(12), h // 2, text="›", fill=self.fg, font=self.font(14, True))
            return self.px(24)
        ents = entries if entries is not None else self.visible_entries()
        if not ents:
            return self.text(c, self.px(4), h // 2, t("bar_no_entries"), self.dim, self.font(9))
        st = self.cfg()["style"]
        spans = []
        x = self.px(4)
        for i, e in enumerate(ents):
            if i:
                c.create_line(x, self.px(8), x, h - self.px(8), fill=self.line)
                x += self.px(10)
            self._tags = (f"entry:{i}",)
            x0 = x
            if st["label"]:
                x = self.text(c, x, h // 2, e["label"], st["label_color"] or self.fg, self.font(9, True), gap=7)
            x = self.draw_entry(c, x, h, e, mode)
            spans.append((x0, x, e))
            x += self.px(6)
        self._tags = ()
        if c is self.canvas and self._ov is None:
            self.entry_spans = spans
        if self.switchable():
            x = self.text(c, x, h // 2, "⇄", self.dim, self.font(13, True), gap=4, tags=("switch",))
        return x

    def draw_entry(self, c, x, h, e, mode):
        d = (self._ov["data"] if self._ov else self.data).get(entry_key(e)) or {}
        u = d.get("usage")
        if not u:
            msg = f"⚠ {tr_error(d['error'])}" if d.get("error") else t("bar_loading")
            return self.text(c, x, h // 2, msg, self.dim, self.font(9))
        stale_min = None
        if self.official() and d.get("saved_at"):
            age = (datetime.now() - d["saved_at"]).total_seconds()
            if age > cc.STALE_AFTER_SEC:
                stale_min = int(age // 60)
        wins = self.entry_windows(e, u)
        if not wins and not (self.cfg()["show_scoped"] and u["scoped"]):
            return self.text(c, x, h // 2, t("bar_pick_items"), self.dim, self.font(9))
        ys = [h // 2] if len(wins) == 1 else [int(h * 0.28), int(h * 0.72)]
        right = x
        for w, y in zip(wins[:2], ys):
            right = max(right, self.draw_line(c, x, y, w, mode, stale=stale_min is not None))
        x = right + self.px(8) if wins else x
        if stale_min is not None:
            x = self.text(c, x, h // 2, t("stale_ago", m=stale_min), self.dim, self.font(9))
        if self.cfg()["show_scoped"]:
            for s in u["scoped"]:
                x = self.text(c, x, h // 2, s["model"], self.dim, self.font(9), gap=3)
                x = self.text(c, x, h // 2, f"{s['pct']:.0f}%", self.rgb(color_for(s["pct"])), self.font(11, True))
        if d.get("error"):
            x = self.text(c, x, h // 2, "⚠", "#e0a030", self.font(9))
        return x

    def draw_line(self, c, x, y, w, mode, stale=False):
        col = self.dim if stale else self.rgb(color_for(w["pct"]))
        x = self.text(c, x, y, w["key"], self.dim, self.font(9), gap=4)
        if mode == "full":
            bar_w, bar_h = self.px(90), self.px(7)
            c.create_rectangle(x, y - bar_h // 2, x + bar_w, y + bar_h // 2, fill=self.track, outline="", tags=self._tags)
            fill_w = int(bar_w * min(w["pct"], 100) / 100)
            if fill_w:
                c.create_rectangle(x, y - bar_h // 2, x + fill_w, y + bar_h // 2, fill=col, outline="", tags=self._tags)
            x += bar_w + self.px(6)
        x = self.text(c, x, y, f"{w['pct']:.0f}%", col, self.font(11, True), gap=6)
        return self.text(c, x, y, f"↺{fmt_reset(w['resets_at'])}", self.dim, self.font(9), gap=0)

    @staticmethod
    def rgb(t):
        return "#%02x%02x%02x" % t

    # --- 상세 팝업 (좁을 때 '›' 를 누르면 위로) ---
    def toggle_popup(self):
        if self.popup:
            self.close_popup()
            return
        h = self.px(56)
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg="#444444")
        c = tk.Canvas(p, width=10, height=h, bg="#202020", highlightthickness=0, bd=0)
        c.pack(padx=1, pady=1)
        saved = (self.fg, self.dim, self.track, self.line, self.mode)
        self.fg, self.dim, self.track, self.line = "#f0f0f0", "#a0a0a0", "#404040", "#505050"
        need = self.draw(c, "full", h, entries=self.enabled_entries()) + self.px(8)
        self.fg, self.dim, self.track, self.line, self.mode = saved
        c.configure(width=need)
        _, top, _, bottom = tb.win_rect(tb.taskbar())
        y = top - h - self.px(10) if top > 0 else bottom + self.px(4)
        p.geometry(f"+{self.gap[0]}+{y}")
        c.bind("<Button-1>", lambda e: self.close_popup())
        self.popup = p
        self.root.after(POPUP_SEC * 1000, self.close_popup)

    def close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def on_left(self, e):
        if "switch" in self.canvas.gettags("current"):
            self.next_entry()
        elif self.mode == "collapsed":
            self.toggle_popup()
        elif self.switchable():
            self.next_entry()
        elif self.mode == "full":
            self.refresh_async()
        else:
            self.toggle_popup()

    def on_right(self, e):
        self.hide_tooltip()
        self.menu.tk_popup(e.x_root, e.y_root)

    # --- 호버 툴팁: 서비스 · 계정 · 폴더 · 창별 값과 리셋 · 모델별 · 플랜/조회 ---
    def entry_at(self, x):
        for x0, x1, e in self.entry_spans:
            if x0 <= x <= x1:
                return e
        return None

    def on_motion(self, ev):
        e = self.entry_at(ev.x)
        if e is not self.tooltip_entry:
            self.hide_tooltip()
            self.tooltip_entry = e
            if e is not None:
                self.tooltip_job = self.root.after(400, lambda: self.show_tooltip(e, ev.x_root))
        elif self.tooltip and e is not None:
            self.place_tooltip(ev.x_root)

    def on_leave(self, ev=None):
        self.hide_tooltip()
        self.tooltip_entry = None

    def tooltip_text(self, e):
        p = get_provider(e["provider"])
        d = self.data.get(entry_key(e)) or {}
        lines = [f"{p.name} · {e['label']}", e["path"]]
        u = d.get("usage")
        if u:
            for w in u["windows"]:
                lines.append(f"{w['key']} {w['pct']:.0f}% · " + t("tt_reset", t=fmt_reset(w["resets_at"])))
            for s_ in u.get("scoped") or []:
                lines.append(f"{s_['model']} {s_['pct']:.0f}% " + t("tt_scoped"))
        if d.get("error"):
            lines.append(t("tt_error", err=tr_error(d["error"])))
        elif self.official() and d.get("saved_at"):
            age = int((datetime.now() - d["saved_at"]).total_seconds() // 60)
            lines.append(t("tt_official_ago", m=age) if age >= 1 else t("tt_official"))
        elif d.get("last_ok"):
            try:
                plan = p.info(e["path"]).get("plan") or "?"
            except Exception:
                plan = "?"
            lines.append(t("tt_fetched", plan=plan, time=d["last_ok"].strftime("%H:%M:%S")))
        elif not u:
            lines.append(t("tt_loading"))
        return "\n".join(lines)

    def show_tooltip(self, e, x_root):
        self.tooltip_job = None
        if self.tooltip or self.tooltip_entry is not e:
            return
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg="#3a3a3a")
        tk.Label(tip, text=self.tooltip_text(e), justify="left", bg="#202020", fg="#f0f0f0",
                 font=("Segoe UI", 9), padx=10, pady=7).pack(padx=1, pady=1)
        self.tooltip = tip
        self.place_tooltip(x_root)

    def place_tooltip(self, x_root):
        if not self.tooltip:
            return
        self.tooltip.update_idletasks()
        tw, th = self.tooltip.winfo_reqwidth(), self.tooltip.winfo_reqheight()
        _, top, _, bottom = tb.win_rect(tb.taskbar())
        sw = self.root.winfo_screenwidth()
        x = max(0, min(int(x_root - tw / 2), sw - tw))
        y = top - th - self.px(8) if top > 0 else bottom + self.px(6)
        self.tooltip.geometry(f"+{x}+{y}")

    def hide_tooltip(self):
        if self.tooltip_job:
            self.root.after_cancel(self.tooltip_job)
            self.tooltip_job = None
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def check_alerts(self):
        for e in self.enabled_entries():
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
        if self.tray:
            try:
                self.tray.notify(msg, APP_TITLE)
                return
            except Exception:
                pass
        threading.Thread(target=lambda: tb.message_box(msg, APP_TITLE, 0x40 | 0x10000), daemon=True).start()

    # ======================================================================
    # 설정 창 — 상단 «미리보기» + 탭(항목 / 표시·스타일 / 데이터 / 시작·언어 / 정보)
    # 어떤 컨트롤을 바꿔도 미리보기가 즉시 다시 그려지고, «저장» 은 적용만 하고 창은 남긴다.
    # ======================================================================
    PRESETS = (
        ("default", {"display_mode": "all", "show_scoped": False, "style": {"label": False, "bars": "bars"}}),
        ("minimal", {"display_mode": "all", "show_scoped": False, "style": {"label": False, "bars": "numbers"}}),
        ("labels", {"display_mode": "all", "show_scoped": False, "style": {"label": True, "bars": "bars"}}),
        ("full", {"display_mode": "all", "show_scoped": True, "style": {"label": False, "bars": "bars"}}),
        ("slide", {"display_mode": "slide", "show_scoped": False, "style": {"label": True, "bars": "auto"}}),
        ("pinned", {"display_mode": "fixed", "show_scoped": True, "style": {"label": False, "bars": "auto"}}),
    )
    SAMPLE = {   # 실제 값이 없을 때 미리보기에 쓰는 예시
        "claude_code": {"windows": [{"key": "5h", "pct": 42.0}, {"key": "7d", "pct": 71.0}], "scoped": [{"model": "Fable", "pct": 56.0}]},
        "codex": {"windows": [{"key": "5h", "pct": 18.0}, {"key": "7d", "pct": 33.0}], "scoped": []},
    }

    # --- 폼 ↔ 설정 ---
    def form_settings(self):
        """설정 창의 현재 컨트롤 값을 설정 dict 로."""
        entries = []
        for r in self.rows:
            p = get_provider(r["provider"])
            entries.append({"provider": r["provider"], "path": r["path"],
                            "label": r["label"].get().strip() or p.label(r["path"]),
                            "enabled": r["enabled"].get(),
                            "windows": {"5h": r["w5h"].get(), "7d": r["w7d"].get()}})
        try:
            slide_sec = max(5, min(3600, int(self.v_slide_sec.get())))
        except Exception:
            slide_sec = 30
        names = [t("lang_auto")] + [LANG_NAMES[c] for c in SUPPORTED]
        language = self.lang_codes[names.index(self.v_lang.get())] if self.v_lang.get() in names else "auto"
        fixed = next((k for k, n in self.fixed_choices() if n == self.v_fixed.get()), "")
        return {
            "entries": entries, "display_mode": self.v_mode.get(), "slide_sec": slide_sec, "fixed_entry": fixed,
            "show_scoped": self.v_scoped.get(),
            "style": {"label": self.v_label.get(), "bars": self.v_bars.get(), "label_color": self.v_label_color.get()},
            "language": language, "data_source": self.v_ds.get(),
            "official_hide_unsupported": self.v_hide.get(),
            "seen_providers": [p.id for p in PROVIDERS],
        }

    def fixed_choices(self):
        return [(entry_key(r), f"{get_provider(r['provider']).short} · {r['label'].get().strip() or get_provider(r['provider']).label(r['path'])}")
                for r in self.rows]

    def snapshot(self):
        return json.dumps(self.form_settings(), sort_keys=True, ensure_ascii=False) + f"|auto={self.v_auto.get()}"

    def is_dirty(self):
        try:
            return self.snapshot() != self._baseline
        except Exception:
            return False

    def watch_var(self, var):
        var.trace_add("write", lambda *a: self.preview_dirty())
        return var

    def preview_dirty(self):
        if self.settings_win and not getattr(self, "_preview_job", None):
            self._preview_job = self.root.after_idle(self.refresh_preview)

    # --- 미리보기 ---
    def preview_data(self, entries):
        """실제 값이 있으면 실제, 없으면 예시값."""
        out = {}
        now = datetime.now()
        for e in entries:
            k = entry_key(e)
            real = self.data.get(k) or {}
            if real.get("usage"):
                out[k] = {"usage": real["usage"], "error": None, "saved_at": None}
                continue
            sm = self.SAMPLE.get(e["provider"]) or self.SAMPLE["codex"]
            wins = [{"key": w["key"], "pct": w["pct"], "resets_at": now.replace(microsecond=0)} for w in sm["windows"]]
            out[k] = {"usage": {"windows": wins, "scoped": list(sm["scoped"]), "fetched_at": now}, "error": None, "saved_at": None}
        return out

    def render_preview(self, canvas, settings, height, mode=None, entries=None):
        """폼 설정으로 캔버스에 바를 그린다 (다크 팔레트 고정). 필요한 폭을 돌려준다."""
        ents = entries if entries is not None else [e for e in settings["entries"] if e["enabled"]]
        saved = (self.fg, self.dim, self.track, self.line, self.bg, self.mode)
        self.bg, self.fg, self.dim, self.track, self.line = (32, 32, 32), "#f0f0f0", "#a0a0a0", "#404040", "#505050"
        self._ov = {"settings": settings, "entries": ents, "data": self.preview_data(ents)}
        try:
            vis = self.visible_entries()
            if mode is None:
                mode = self.tiers(settings)[0]
            need = self.draw(canvas, mode, height, entries=vis)
        finally:
            self._ov = None
            self.fg, self.dim, self.track, self.line, self.bg, self.mode = saved
        return need

    def refresh_preview(self):
        self._preview_job = None
        if not self.settings_win:
            return
        try:
            S = self.form_settings()
        except Exception:
            return
        c = self.preview_canvas
        h = self.h
        # 지금 빈 공간에서 실제로 잡힐 단계
        gap_w = (self.gaps[0][1] - self.gaps[0][0]) if self.gaps else 0
        tier, need = None, 0
        for m in self.tiers(S):
            need = self.render_preview(c, S, h, mode=m)
            if gap_w and need <= gap_w:
                tier = m
                break
        if tier is None:                       # 못 잰 상태거나 아무것도 안 맞으면 가장 큰 단계로 보여준다
            tier = self.tiers(S)[0]
            need = self.render_preview(c, S, h, mode=tier)
        c.configure(width=min(max(need + self.px(8), self.px(120)), self.px(700)))
        if gap_w:
            self.preview_hint.configure(text=t("preview_hint", n=gap_w, tier=t(f"tier_{tier}")))
        else:
            self.preview_hint.configure(text=t("preview_hint_nogap"))
        self.highlight_presets(S)

    # --- 프리셋 ---
    def preset_matches(self, S, values):
        if S["display_mode"] != values["display_mode"] or S["show_scoped"] != values["show_scoped"]:
            return False
        return all(S["style"][k] == v for k, v in values["style"].items())

    def apply_preset(self, values):
        self.v_mode.set(values["display_mode"])
        self.v_scoped.set(values["show_scoped"])
        self.v_label.set(values["style"]["label"])
        self.v_bars.set(values["style"]["bars"])
        self.preview_dirty()

    def highlight_presets(self, S):
        for key, values, frame in self.preset_cards:
            on = self.preset_matches(S, values)
            frame.configure(highlightbackground="#3b82f6" if on else "#d0d0d0", highlightthickness=2 if on else 1)

    def draw_preset_card(self, canvas, values):
        """카드 안 미리보기: 예시 항목 2개(Claude·Codex)를 그 프리셋으로."""
        S = json.loads(json.dumps(DEFAULT_SETTINGS))
        S.update({k: v for k, v in values.items() if k != "style"})
        S["style"].update(values["style"])
        sample = [{"provider": "claude_code", "path": "sample-claude", "label": "work", "enabled": True, "windows": {}},
                  {"provider": "codex", "path": "sample-codex", "label": "home", "enabled": True, "windows": {}}]
        S["entries"] = sample
        S["fixed_entry"] = entry_key(sample[0])
        h = int(canvas["height"])
        self.render_preview(canvas, S, h, entries=sample)

    # --- 창 ---
    def section(self, parent, key, row, hint=None):
        """굵은 제목 + 얇은 구분선 (+ 회색 설명 한 줄)."""
        ttk.Label(parent, text=t(key), font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Separator(parent, orient="horizontal").grid(row=row + 1, column=0, columnspan=4, sticky="ew", pady=(2, 3))
        if hint:
            ttk.Label(parent, text=t(hint), foreground="#808080", font=("Segoe UI", 8), wraplength=self.px(690), justify="left").grid(
                row=row + 2, column=0, columnspan=4, sticky="w", pady=(0, 6))
            return row + 3
        return row + 2

    def open_settings(self, install_mode=False, tab=0):
        if self.settings_win:
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        w = tk.Toplevel(self.root)
        self.settings_win = w
        self.install_mode = install_mode
        self.fixed_combo = None                       # 탭이 만들어지기 전에는 없다 (이전 창의 것을 만지지 않게)
        w.title(f"{APP_TITLE} {t('win_setup') if install_mode else t('win_settings')}")
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.configure(bg="#f3f3f3")
        try:
            w.iconbitmap(ICON_PATH)
        except Exception:
            pass
        style = ttk.Style(w)
        for theme in ("vista", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TNotebook", padding=(4, 4))
        style.configure("TNotebook.Tab", padding=(12, 4), font=("Segoe UI", 9))

        # 상단: 제목 줄 + 미리보기
        top = ttk.Frame(w, padding=(18, 10, 18, 4))
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"v{__version__}  ·  " + t("preview_title"), foreground="#808080").grid(row=0, column=1, sticky="e")
        top.columnconfigure(0, weight=1)
        pv = tk.Frame(top, bg="#202020", bd=0, highlightthickness=1, highlightbackground="#c8c8c8")
        pv.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.preview_canvas = tk.Canvas(pv, width=self.px(400), height=self.h, bg="#202020", highlightthickness=0, bd=0)
        self.preview_canvas.bind("<Motion>", lambda ev: None)
        self.preview_canvas.pack(padx=self.px(6), pady=self.px(2))
        self.preview_hint = ttk.Label(top, text="", foreground="#404040", font=("Segoe UI", 9))
        self.preview_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(top, text=t("preview_note"), foreground="#808080", font=("Segoe UI", 8), wraplength=self.px(700), justify="left").grid(
            row=4, column=0, columnspan=2, sticky="w")

        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        self.nb = nb
        tabs = [ttk.Frame(nb, padding=(14, 8, 14, 12)) for _ in range(5)]
        for fr, key in zip(tabs, ("tab_entries", "tab_display", "tab_data", "tab_startup", "tab_about")):
            nb.add(fr, text=t(key))
        self.build_tab_entries(tabs[0])
        self.build_tab_display(tabs[1])
        self.build_tab_data(tabs[2])
        self.build_tab_startup(tabs[3], install_mode)
        self.build_tab_about(tabs[4])

        # 하단 버튼
        bt = ttk.Frame(w, padding=(18, 8, 18, 12))
        bt.pack(fill="x")
        self.saved_label = ttk.Label(bt, text="", foreground="#1a7f37", font=("Segoe UI", 9, "bold"))
        self.saved_label.pack(side="left")
        if install_mode:
            ttk.Button(bt, text=t("btn_start"), command=lambda: self.apply_settings(close=True)).pack(side="right")
        else:
            ttk.Button(bt, text=t("btn_close"), command=self.close_settings).pack(side="right")
            ttk.Button(bt, text=t("btn_save"), command=self.apply_settings).pack(side="right", padx=(0, 6))
        w.protocol("WM_DELETE_WINDOW", (lambda: self.apply_settings(close=True)) if install_mode else self.close_settings)

        self._baseline = self.snapshot()
        self._preview_job = None
        self.refresh_preview()
        try:
            nb.select(tab)
        except Exception:
            pass
        w.update_idletasks()
        sw_, sh_ = w.winfo_screenwidth(), w.winfo_screenheight()
        width, height = min(w.winfo_reqwidth(), self.px(800)), min(w.winfo_reqheight(), sh_ - 80)
        w.geometry(f"{width}x{height}+{(sw_ - width) // 2}+{max(0, (sh_ - height) // 2 - 30)}")
        w.focus_force()

    # --- 탭 1: 항목 ---
    def build_tab_entries(self, f):
        row = self.section(f, "sec_entries", 0, hint="hint_autodiscover")
        self.rows_frame = ttk.Frame(f)
        self.rows_frame.grid(row=row, column=0, columnspan=4, sticky="ew")
        self.rows = []
        for e in self.settings["entries"]:
            self.rows.append(self.make_row(e["provider"], e["path"], e["label"], e["enabled"], e["windows"]))
        self.rebuild_rows()
        btns = ttk.Frame(f)
        btns.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(btns, text=t("btn_add_folder"), command=self.add_folder_dialog).pack(side="left")
        ttk.Button(btns, text=t("btn_rescan"), command=self.rescan).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text=t("btn_why_missing"), command=self.open_help).pack(side="left", padx=(6, 0))
        self.rescan_label = ttk.Label(f, text="", foreground="#404040", font=("Segoe UI", 9))
        self.rescan_label.grid(row=row + 2, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def make_row(self, provider, path, label, enabled, windows):
        r = {"provider": provider, "path": path,
             "enabled": self.watch_var(tk.BooleanVar(value=enabled)),
             "label": self.watch_var(tk.StringVar(value=label)),
             "w5h": self.watch_var(tk.BooleanVar(value=windows.get("5h", True))),
             "w7d": self.watch_var(tk.BooleanVar(value=windows.get("7d", True)))}
        return r

    def row_status(self, r):
        """(색, 짧은 글)  — 연결됨 / 오류 / 미확인"""
        p = get_provider(r["provider"])
        d = self.data.get(f"{r['provider']}|{r['path']}") or {}
        try:
            info = p.info(r["path"])
        except Exception:
            info = {"connected": False}
        if d.get("error") or not info.get("connected"):
            return "#d23f31", t("st_err")
        if d.get("usage") or info.get("connected"):
            return "#1a7f37", t("st_ok")
        return "#9a9a9a", t("st_unknown")

    def rebuild_rows(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        if not self.rows:
            ttk.Label(self.rows_frame, text=t("no_entries_row"), foreground="#a05020", wraplength=self.px(680), justify="left").grid(row=0, column=0, sticky="w")
            self.preview_dirty()
            return
        for i, r in enumerate(self.rows):
            p = get_provider(r["provider"])
            card = tk.Frame(self.rows_frame, bg="#ffffff", highlightthickness=1, highlightbackground="#dcdcdc", padx=10, pady=6)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 6))
            self.rows_frame.columnconfigure(0, weight=1)
            ttk.Checkbutton(card, variable=r["enabled"]).grid(row=0, column=0, rowspan=2, padx=(0, 6))
            tk.Label(card, text=p.name, bg="#ffffff", fg="#808080", font=("Segoe UI", 8), anchor="w", width=16).grid(row=0, column=2, sticky="w")
            tk.Label(card, text=r["path"], bg="#ffffff", fg="#707070", font=("Segoe UI", 8), anchor="w").grid(row=1, column=2, columnspan=4, sticky="w")
            ttk.Entry(card, textvariable=r["label"], width=13).grid(row=0, column=3, sticky="w", padx=(6, 10))
            wf = tk.Frame(card, bg="#ffffff")
            wf.grid(row=0, column=4, sticky="w")
            ttk.Checkbutton(wf, text="5h", variable=r["w5h"]).pack(side="left")
            ttk.Checkbutton(wf, text="7d", variable=r["w7d"]).pack(side="left", padx=(4, 0))
            col, txt = self.row_status(r)
            sf = tk.Frame(card, bg="#ffffff")
            sf.grid(row=0, column=5, sticky="w", padx=(12, 0))
            tk.Canvas(sf, width=10, height=10, bg="#ffffff", highlightthickness=0).pack(side="left")
            sf.winfo_children()[0].create_oval(1, 1, 9, 9, fill=col, outline=col)
            tk.Label(sf, text=txt, bg="#ffffff", fg=col, font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))
            right = tk.Frame(card, bg="#ffffff")
            right.grid(row=0, column=6, rowspan=2, sticky="e", padx=(12, 0))
            card.columnconfigure(6, weight=1)
            if p.supports_official:
                linked = cc.statusline_installed(r["path"])
                ttk.Button(right, text=t("btn_statusline_uninstall" if linked else "btn_statusline_install"), width=14,
                           command=lambda r=r: self.toggle_statusline(r)).pack(side="left", padx=(0, 8))
            ttk.Button(right, text="▲", width=2, command=lambda r=r: self.move_row(r, -1)).pack(side="left")
            ttk.Button(right, text="▼", width=2, command=lambda r=r: self.move_row(r, 1)).pack(side="left")
            ttk.Button(right, text="✕", width=2, command=lambda r=r: (self.rows.remove(r), self.rebuild_rows())).pack(side="left", padx=(4, 0))
        self.refresh_fixed_combo()
        self.preview_dirty()

    def move_row(self, r, delta):
        i = self.rows.index(r)
        j = i + delta
        if 0 <= j < len(self.rows):
            self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
            self.rebuild_rows()

    def refresh_fixed_combo(self):
        if not getattr(self, "fixed_combo", None) or not self.fixed_combo.winfo_exists():
            return
        names = [n for _, n in self.fixed_choices()]
        self.fixed_combo.configure(values=names)
        if self.v_fixed.get() not in names:
            self.v_fixed.set(names[0] if names else "")

    # --- 탭 2: 표시 · 스타일 ---
    def build_tab_display(self, f):
        st = self.settings["style"]
        self.v_mode = self.watch_var(tk.StringVar(value=self.settings["display_mode"]))
        self.v_slide_sec = self.watch_var(tk.IntVar(value=self.settings["slide_sec"]))
        self.v_label = self.watch_var(tk.BooleanVar(value=st["label"]))
        self.v_scoped = self.watch_var(tk.BooleanVar(value=self.settings["show_scoped"]))
        self.v_bars = self.watch_var(tk.StringVar(value=st["bars"]))
        self.v_label_color = self.watch_var(tk.StringVar(value=st["label_color"]))
        names = [n for _, n in self.fixed_choices()]
        cur = next((n for k, n in self.fixed_choices() if k == self.settings["fixed_entry"]), names[0] if names else "")
        self.v_fixed = self.watch_var(tk.StringVar(value=cur))

        # 프리셋 카드
        row = self.section(f, "presets_title", 0, hint="presets_hint")
        grid = ttk.Frame(f)
        grid.grid(row=row, column=0, columnspan=4, sticky="ew")
        self.preset_cards = []
        for i, (key, values) in enumerate(self.PRESETS):
            card = tk.Frame(grid, bg="#ffffff", highlightthickness=1, highlightbackground="#d0d0d0", cursor="hand2", padx=8, pady=6)
            card.grid(row=i // 3, column=i % 3, padx=(0, 8) if i % 3 < 2 else 0, pady=(0, 8), sticky="nsew")
            grid.columnconfigure(i % 3, weight=1)
            cv = tk.Canvas(card, width=self.px(214), height=self.px(28), bg="#202020", highlightthickness=0, bd=0)
            cv.pack(anchor="w")
            self.draw_preset_card(cv, values)
            row_ = tk.Frame(card, bg="#ffffff")
            row_.pack(anchor="w", fill="x", pady=(3, 0))
            tk.Label(row_, text=t(f"preset_{key}"), bg="#ffffff", font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left")
            tk.Label(row_, text="  " + t(f"preset_{key}_desc"), bg="#ffffff", fg="#707070", font=("Segoe UI", 8), anchor="w").pack(side="left")
            for wdg in (card, cv, row_, *row_.winfo_children()):
                wdg.bind("<Button-1>", lambda e, v=values: self.apply_preset(v))
            self.preset_cards.append((key, values, card))

        # 표시 방식
        row = self.section(f, "sec_mode", row + 1)
        mf = ttk.Frame(f)
        mf.grid(row=row, column=0, columnspan=4, sticky="ew")
        for i, mode in enumerate(MODES):
            tk.Radiobutton(mf, text=t(f"mode_{mode}"), variable=self.v_mode, value=mode, anchor="w", justify="left",
                           wraplength=self.px(320)).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 14))
        sub = ttk.Frame(f)
        sub.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(sub, text=t("slide_hint_pre")).pack(side="left")
        ttk.Spinbox(sub, from_=5, to=3600, increment=5, width=6, textvariable=self.v_slide_sec).pack(side="left", padx=(6, 4))
        ttk.Label(sub, text=t("slide_hint"), foreground="#808080", font=("Segoe UI", 8)).pack(side="left", padx=(0, 18))
        ttk.Label(sub, text=t("fixed_hint")).pack(side="left")
        self.fixed_combo = ttk.Combobox(sub, textvariable=self.v_fixed, values=names, state="readonly", width=24)
        self.fixed_combo.pack(side="left", padx=(6, 0))

        # 모양
        row = self.section(f, "sec_look", row + 2)
        lf = ttk.Frame(f)
        lf.grid(row=row, column=0, columnspan=4, sticky="ew")
        ttk.Checkbutton(lf, text=t("style_label"), variable=self.v_label).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(lf, text=t("item_scoped"), variable=self.v_scoped).grid(row=1, column=0, sticky="w", pady=(2, 0))
        brow = ttk.Frame(f)
        brow.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(brow, text=t("style_bars")).pack(side="left")
        for val in BAR_STYLES:
            ttk.Radiobutton(brow, text=t(f"style_bars_{val}"), variable=self.v_bars, value=val).pack(side="left", padx=(10, 0))
        crow = ttk.Frame(f)
        crow.grid(row=row + 2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(crow, text=t("style_colors")).pack(side="left")
        for key, var in (("style_label_color", self.v_label_color),):
            ttk.Label(crow, text=t(key)).pack(side="left", padx=(10, 4))
            chip = tk.Label(crow, width=3, relief="solid", bd=1, bg=var.get() or "#e0e0e0")
            chip.pack(side="left")
            var.trace_add("write", lambda *a, v=var, c=chip: c.configure(bg=v.get() or "#e0e0e0"))
            ttk.Button(crow, text=t("style_pick"), width=7, command=lambda v=var: self.pick_color(v)).pack(side="left", padx=(4, 0))
            ttk.Button(crow, text=t("style_reset"), width=5, command=lambda v=var: v.set("")).pack(side="left", padx=(2, 0))

    def pick_color(self, var):
        rgb, hexv = colorchooser.askcolor(color=var.get() or None, parent=self.settings_win)
        if hexv:
            var.set(hexv)

    # --- 탭 3: 데이터 ---
    def build_tab_data(self, f):
        row = self.section(f, "sec_data_source", 0)
        self.v_ds = self.watch_var(tk.StringVar(value=self.settings["data_source"]))
        self.v_hide = self.watch_var(tk.BooleanVar(value=self.settings["official_hide_unsupported"]))
        for i, (val, key) in enumerate((("api", "ds_api"), ("official", "ds_official"))):
            tk.Radiobutton(f, text=t(key), variable=self.v_ds, value=val, anchor="w", justify="left",
                           wraplength=self.px(660)).grid(row=row + i, column=0, columnspan=4, sticky="w", pady=1)
        ttk.Checkbutton(f, text=t("ds_hide_unsupported"), variable=self.v_hide).grid(row=row + 2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        row = self.section(f, "sec_status", row + 3)
        self.status_label = ttk.Label(f, text="", justify="left", foreground="#404040", font=("Segoe UI", 9), wraplength=self.px(680))
        self.status_label.grid(row=row, column=0, columnspan=4, sticky="w")
        ttk.Button(f, text=t("btn_recheck"), command=self.refresh_async).grid(row=row + 1, column=0, sticky="w", pady=(8, 0))
        self.fill_status()
        ttk.Label(f, text=t("unofficial_note"), foreground="#808080", font=("Segoe UI", 8), justify="left", wraplength=self.px(690)).grid(
            row=row + 2, column=0, columnspan=4, sticky="w", pady=(14, 0))

    # --- 탭 4: 시작 · 언어 ---
    def build_tab_startup(self, f, install_mode):
        row = self.section(f, "sec_startup", 0)
        self.v_auto = tk.BooleanVar(value=True if install_mode else os.path.exists(STARTUP_LNK))
        ttk.Checkbutton(f, text=t("autostart"), variable=self.v_auto).grid(row=row, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text=t("run_location", dir=APP_DIR), foreground="#808080", font=("Segoe UI", 8), justify="left", wraplength=self.px(690)).grid(
            row=row + 1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        row = self.section(f, "sec_language", row + 2)
        self.lang_codes = ["auto"] + list(SUPPORTED)
        names = [t("lang_auto")] + [LANG_NAMES[c] for c in SUPPORTED]
        self.v_lang = self.watch_var(tk.StringVar(value=names[self.lang_codes.index(self.settings["language"])]))
        ttk.Combobox(f, textvariable=self.v_lang, values=names, state="readonly", width=20).grid(row=row, column=0, sticky="w")

    # --- 탭 5: 정보 ---
    def build_tab_about(self, f):
        ttk.Label(f, text=f"{APP_TITLE}  v{__version__}", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(f, text=t("app_desc"), foreground="#606060", wraplength=self.px(690), justify="left").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Label(f, text=" · ".join(p.name for p in PROVIDERS), foreground="#808080", font=("Segoe UI", 9)).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        row = self.section(f, "about_transparency", 3)
        for i, key in enumerate(("about_reads", "about_sends", "about_stores")):
            ttk.Label(f, text="•  " + t(key), wraplength=self.px(690), justify="left").grid(row=row + i, column=0, columnspan=4, sticky="w", pady=(0, 3))
        links = ttk.Frame(f)
        links.grid(row=row + 3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        for key, url in (("link_readme", README_URL), ("menu_support", SUPPORT_URL)):
            lk = ttk.Label(links, text=t(key), foreground="#0a66c2", cursor="hand2")
            lk.pack(anchor="w", pady=(0, 3))
            lk.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ttk.Button(f, text=t("btn_why_missing"), command=self.open_help).grid(row=row + 4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(f, text=t("unofficial_note"), foreground="#808080", font=("Segoe UI", 8), justify="left", wraplength=self.px(690)).grid(
            row=row + 5, column=0, columnspan=4, sticky="w", pady=(14, 0))
        ttk.Label(f, text=t("trademark_note"), foreground="#808080", font=("Segoe UI", 8), justify="left", wraplength=self.px(690)).grid(
            row=row + 6, column=0, columnspan=4, sticky="w", pady=(4, 0))

    # --- 항목 조작 ---
    def toggle_statusline(self, r):
        """그 계정 폴더의 settings.json 에 statusLine 내보내기를 설치/해제한다 — 반드시 확인 대화상자 뒤에."""
        path = r["path"]
        sp, bp = cc.settings_path(path), cc.backup_path(path)
        try:
            if cc.statusline_installed(path):
                if not messagebox.askyesno(APP_TITLE, t("statusline_confirm_uninstall", path=sp), parent=self.settings_win):
                    return
                cc.statusline_uninstall(path)
                messagebox.showinfo(APP_TITLE, t("statusline_done_uninstall"), parent=self.settings_win)
            else:
                if not messagebox.askyesno(APP_TITLE, t("statusline_confirm_install", path=sp, backup=bp), parent=self.settings_win):
                    return
                backup = cc.statusline_install(path, PS1_PATH)
                messagebox.showinfo(APP_TITLE, t("statusline_done_install", backup=backup), parent=self.settings_win)
        except Exception as e:
            messagebox.showerror(APP_TITLE, t("statusline_failed", e=e), parent=self.settings_win)
        self.rebuild_rows()
        self.fill_status()

    def add_folder_dialog(self):
        p = self.pick_provider()
        if not p:
            return
        d = filedialog.askdirectory(parent=self.settings_win, title=t("dialog_pick_folder", name=p.name, file=p.cred_file),
                                    initialdir=os.path.expanduser("~"))
        if not d:
            return
        d = os.path.abspath(d)
        if any(r["provider"] == p.id and os.path.normcase(r["path"]) == os.path.normcase(d) for r in self.rows):
            messagebox.showinfo(APP_TITLE, t("dup_folder"), parent=self.settings_win)
            return
        if not os.path.isfile(os.path.join(d, p.cred_file)):
            if not messagebox.askyesno(APP_TITLE, t("no_cred_confirm", file=p.cred_file, name=p.name), parent=self.settings_win):
                return
        self.rows.append(self.make_row(p.id, d, p.label(d), True, {}))
        self.rebuild_rows()

    def pick_provider(self):
        """«폴더 추가…» 앞에 어느 서비스인지 고르는 작은 대화상자."""
        dlg = tk.Toplevel(self.settings_win)
        dlg.title(t("pick_provider_title"))
        dlg.transient(self.settings_win)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        fr = ttk.Frame(dlg, padding=16)
        fr.pack()
        ttk.Label(fr, text=t("pick_provider_body")).pack(anchor="w", pady=(0, 8))
        v = tk.StringVar(value=PROVIDERS[0].id)
        for p in PROVIDERS:
            ttk.Radiobutton(fr, text=f"{p.name}  ({p.cred_file})", variable=v, value=p.id).pack(anchor="w")
        result = {"ok": False}
        bt = ttk.Frame(fr)
        bt.pack(anchor="e", pady=(12, 0))
        ttk.Button(bt, text=t("btn_ok"), command=lambda: (result.update(ok=True), dlg.destroy())).pack(side="left", padx=(0, 6))
        ttk.Button(bt, text=t("btn_cancel"), command=dlg.destroy).pack(side="left")
        dlg.update_idletasks()
        dlg.geometry(f"+{self.settings_win.winfo_rootx() + 60}+{self.settings_win.winfo_rooty() + 80}")
        dlg.grab_set()
        self.settings_win.wait_window(dlg)
        return get_provider(v.get()) if result["ok"] else None

    def rescan(self):
        known = {(r["provider"], os.path.normcase(r["path"])) for r in self.rows}
        added = 0
        for p in PROVIDERS:
            for d in p.discover():
                if (p.id, os.path.normcase(d)) not in known:
                    self.rows.append(self.make_row(p.id, d, p.label(d), True, {}))
                    added += 1
        self.rebuild_rows()
        self.rescan_label.configure(text=t("rescan_found", n=added) if added else t("rescan_none"))

    def fill_status(self):
        if not self.settings_win or not hasattr(self, "status_label"):
            return
        lines = []
        for e in self.settings["entries"]:
            p = get_provider(e["provider"])
            info = p.info(e["path"])
            d = self.data.get(entry_key(e)) or {}
            if info["connected"]:
                s = t("status_connected", label=e["label"], name=p.name, plan=info["plan"] or "?",
                      exp=info["expires_at"].strftime("%m/%d %H:%M") if info["expires_at"] else "?")
            else:
                s = t("status_disconnected", label=e["label"], name=p.name, reason=tr_error(info["reason"]))
            if d.get("error"):
                s += t("status_error", err=tr_error(d["error"]))
            elif d.get("last_ok"):
                s += t("status_last_ok", time=d["last_ok"].strftime("%H:%M:%S"))
            if p.supports_official and cc.statusline_installed(e["path"]):
                s += t("status_statusline_on")
            lines.append(s)
        self.status_label.configure(text="\n".join(lines) if lines else "")

    # --- 저장 / 닫기 ---
    def apply_settings(self, close=False):
        """저장 + 바에 즉시 반영. close=False 면 창은 그대로 두고 «저장됨 ✓» 만 잠깐 보여준다."""
        new = self.form_settings()
        lang_changed = new["language"] != self.settings["language"]
        self.settings = new
        save_settings(self.settings)
        try:
            set_autostart(self.v_auto.get())
        except Exception as e:
            tb.message_box(t("autostart_failed", e=e), APP_TITLE, 0x30)
        self._baseline = self.snapshot()
        first = not self.started
        if lang_changed:
            set_language(new["language"])
            self.menu = self.build_menu()
            self.update_tray()
        if first:
            self.close_settings(force=True)
            self.close_help()
            self.start()
            return
        self.cur = 0
        self.data = {k: v for k, v in self.data.items()}   # 값은 유지, 원본이 바뀌었으면 다음 조회가 덮어쓴다
        self.schedule_cycle()
        self.refresh_async()
        self.relayout(force=True)
        if lang_changed:                                   # 바뀐 언어로 설정 창을 다시 연다
            tab = self.nb.index(self.nb.select()) if self.settings_win else 0
            self.close_settings(force=True)
            self.close_help()
            self.root.after(100, lambda: self.open_settings(tab=tab))
            return
        if close:
            self.close_settings(force=True)
            return
        self.fill_status()
        self.saved_label.configure(text=t("btn_saved"))
        self.root.after(2000, lambda: self.saved_label.configure(text="") if self.settings_win else None)

    def close_settings(self, force=False):
        if not self.settings_win:
            return
        if not force and not getattr(self, "install_mode", False) and self.is_dirty():
            r = messagebox.askyesnocancel(APP_TITLE, t("unsaved_prompt"), parent=self.settings_win)
            if r is None:
                return
            if r:
                self.apply_settings(close=True)
                return
        self.settings_win.destroy()
        self.settings_win = None

    # --- «계정이 안 보여요?» 안내 창 ---
    def open_help(self):
        if self.help_win:
            self.help_win.lift()
            self.help_win.focus_force()
            return
        w = tk.Toplevel(self.root)
        self.help_win = w
        w.title(f"{APP_TITLE} — {t('help_title')}")
        w.resizable(False, False)
        w.attributes("-topmost", True)
        try:
            w.iconbitmap(ICON_PATH)
        except Exception:
            pass
        f = ttk.Frame(w, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=t("help_title"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(f, text=t("help_intro"), justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        for p in PROVIDERS:
            ttk.Label(f, text=f"■ {p.name}", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
            ttk.Label(f, text=t(p.help_key), justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(f, text=f"■ {t('help_multi_title')}", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        ttk.Label(f, text=t("help_multi_body"), justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Button(f, text=t("btn_close"), command=self.close_help).pack(anchor="e", pady=(14, 0))
        w.protocol("WM_DELETE_WINDOW", self.close_help)
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"+{(sw - w.winfo_width()) // 2}+{max(0, (sh - w.winfo_height()) // 2)}")
        w.focus_force()

    def close_help(self):
        if self.help_win:
            self.help_win.destroy()
            self.help_win = None

    def quit(self):
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def single_instance():
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ai-status-bar")
    return ctypes.windll.kernel32.GetLastError() != 183


# ---------- 자동 시작 (시작프로그램 폴더 바로가기, 프로세스 안 COM — 외부 프로세스를 띄우지 않는다) ----------

def set_autostart(on):
    """시작프로그램 폴더에 바로가기를 만들거나 지운다. 관리자 권한·레지스트리·자기 복사 없음."""
    if not on:
        if os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        return
    import pythoncom
    from win32com.shell import shell
    if FROZEN:
        target, args = sys.executable, ""
    else:
        target, args = sys.executable, f'"{os.path.abspath(__file__)}"'
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(target)
    link.SetArguments(args)
    link.SetWorkingDirectory(os.path.dirname(target))
    link.SetDescription(APP_TITLE)
    if os.path.exists(ICON_PATH):
        link.SetIconLocation(ICON_PATH, 0)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(STARTUP_LNK, 0)


def first_run():
    """설정 파일이 아직 없으면 (처음 실행) 시작 설정 창을 먼저 보여준다. 이전 이름의 설정이 있으면 조용히 이전한다."""
    if os.path.exists(SETTINGS_PATH):
        return False
    if os.path.exists(OLD_SETTINGS_PATH):
        try:
            save_settings(load_settings())
            return False
        except Exception:
            pass
    return True


if __name__ == "__main__":
    if "--autostart" in sys.argv:      # 조용히 자동 시작만 켜고 끝 (배포 스크립트용)
        set_autostart(True)
        sys.exit(0)
    if "--no-autostart" in sys.argv:
        set_autostart(False)
        sys.exit(0)
    if not single_instance():
        sys.exit(0)
    StatusBar(install_mode=first_run() or "--setup" in sys.argv).run()
