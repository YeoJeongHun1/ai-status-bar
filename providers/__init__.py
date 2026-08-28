"""
제공자(provider) 플러그인 — AI 서비스 하나 = 모듈 하나.

공통 규약
- 계정 = 그 서비스의 CLI 가 로그인 정보를 저장하는 **폴더 하나** (Claude Code: .credentials.json, Codex: auth.json).
- fetch(path) 가 돌려주는 usage 는 서비스와 무관하게 같은 모양:
      {"windows": [{"key": "5h", "pct": 23.0, "resets_at": datetime|None}, {"key": "7d", ...}],
       "scoped":  [{"model": "Fable", "pct": 45.0}],          # 모델별 한도 (없으면 [])
       "fetched_at": datetime}
- 오류는 RuntimeError("i18n_key [인자]") 로 던진다 — UI 가 i18n.tr_error() 로 번역한다.
- 네트워크는 fetch() 안에서만. 토큰은 갱신하지 않고, 어디에도 저장하지 않는다.
"""
from datetime import datetime

from PIL import Image, ImageDraw


class Provider:
    id = ""                 # 설정 파일에 저장되는 식별자
    name = ""               # 표시 이름 (예: "Claude Code")
    short = ""              # 짧은 이름 (툴팁·알림용, 예: "Claude")
    cred_file = ""          # 계정 폴더 안의 로그인 파일 이름
    usage_page = ""         # «사용량 페이지 열기» 링크
    supports_official = False
    help_key = ""           # «계정이 안 보여요?» 안내의 제공자 절 키

    def discover(self):                 # -> [config_dir, ...]
        return []

    def label(self, path):              # -> 표시용 이름
        import os
        return os.path.basename(os.path.normpath(path))

    def info(self, path):               # -> {"connected", "reason", "plan", "expires_at", "path"}
        raise NotImplementedError

    def fetch(self, path):              # -> usage (네트워크)
        raise NotImplementedError

    def fetch_official(self, path):     # -> (usage, saved_at)   supports_official 일 때만
        raise RuntimeError("err_official_unsupported")


# ---------- 공통 표시 도우미 ----------

def window_label(key):
    """창 키(5h·7d·"12h"·"30d"…)를 그대로 라벨로 쓴다."""
    return key


def color_for(pct):
    if pct >= 80:
        return (220, 50, 50)
    if pct >= 50:
        return (230, 170, 30)
    return (60, 180, 90)


def fmt_reset(dt):
    if not dt:
        return ""
    if dt.date() == datetime.now().date():
        return dt.strftime("%H:%M")
    return dt.strftime("%m/%d %H:%M")


def draw_icon(usage, error=False):
    """트레이 아이콘: 막대 2개 (첫 두 창). usage 가 없으면 회색, error 면 주황 테두리."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    wins = (usage or {}).get("windows") or []
    bars = (wins + [None, None])[:2]
    bar_h, gap, top = 24, 8, 4
    if error:
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=10, outline=(230, 150, 30), width=4)
    for i, w in enumerate(bars):
        y0 = top + i * (bar_h + gap)
        y1 = y0 + bar_h
        d.rounded_rectangle((2, y0, size - 2, y1), radius=6, fill=(70, 70, 70))
        if w:
            fill_w = max(6, int((size - 4) * min(w["pct"], 100) / 100))
            d.rounded_rectangle((2, y0, 2 + fill_w, y1), radius=6, fill=color_for(w["pct"]))
    return img


def summary(usage):
    """툴팁용 한 줄: 5h 20% · 7d 65% · Fable 45%"""
    parts = [f"{w['key']} {w['pct']:.0f}%" for w in usage.get("windows") or []]
    parts += [f"{s['model']} {s['pct']:.0f}%" for s in usage.get("scoped") or []]
    return " · ".join(parts)


# ---------- 레지스트리 ----------

def all_providers():
    from . import claude_code, codex
    return [claude_code.ClaudeCode(), codex.Codex()]


def get(provider_id):
    for p in all_providers():
        if p.id == provider_id:
            return p
    return None
