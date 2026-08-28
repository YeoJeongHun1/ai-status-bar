"""
설정 파일 — ~/Library/Application Support/AIStatusBar/settings.json.

Windows 판(ai_status_bar.py 의 load_settings)과 **같은 스키마·같은 화이트리스트**라 파일을 서로 옮겨도 읽힌다.
Windows 쪽 함수는 tkinter 를 import 하는 파일 안에 있어 여기서 재사용하지 못하고, 순수 부분만 옮겨 적었다.
(이전 이름 «Claude Status Bar» 의 설정 이전은 Windows 에만 있던 것이라 없다.)
"""
import json
import os

from i18n import SUPPORTED
from providers import all_providers, get as get_provider

from .paths import APP_SUPPORT, SETTINGS_PATH

MODES = ("all", "click", "slide", "fixed")
BAR_STYLES = ("auto", "bars", "numbers")
PLACEMENTS = ("left", "auto")
OVERFLOW_POLICIES = ("slide", "numbers", "collapse")
INDICATORS = ("dots", "arrow", "none")
SLIDE_CHOICES = (10, 30, 60, 300)
DEFAULT_SETTINGS = {
    "entries": [],               # [{"provider", "path", "label", "enabled", "windows": {"5h": True, "7d": True}}]
    "display_mode": "all",       # all / click / slide / fixed
    "slide_sec": 30,
    "fixed_entry": "",           # "provider|path"
    "show_scoped": True,
    "style": {"label": False, "bars": "auto", "label_color": ""},
    "placement": "left",         # Windows 전용 키 — 호환을 위해 보존만 한다
    "overflow_policy": "slide",
    "switch_indicator": "dots",
    "language": "auto",
    "data_source": "api",        # api / official
    "official_hide_unsupported": True,
    "seen_providers": [],
}
PROVIDERS = all_providers()


def entry_key(e):
    return f"{e['provider']}|{e['path']}"


def load_settings(path=None):
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(path or SETTINGS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return s
    if not isinstance(raw, dict):
        return s
    if raw.get("display_mode") in MODES:
        s["display_mode"] = raw["display_mode"]
    if isinstance(raw.get("slide_sec"), (int, float)):
        s["slide_sec"] = max(5, min(3600, int(raw["slide_sec"])))
    if isinstance(raw.get("fixed_entry"), str):
        s["fixed_entry"] = raw["fixed_entry"]
    if "show_scoped" in raw:
        s["show_scoped"] = bool(raw["show_scoped"])
    st = raw.get("style") if isinstance(raw.get("style"), dict) else {}
    s["style"]["label"] = bool(st.get("label", False))
    if st.get("bars") in BAR_STYLES:
        s["style"]["bars"] = st["bars"]
    v = st.get("label_color") or ""
    s["style"]["label_color"] = v if isinstance(v, str) and v.startswith("#") and len(v) == 7 else ""
    if raw.get("placement") in PLACEMENTS:
        s["placement"] = raw["placement"]
    if raw.get("overflow_policy") in OVERFLOW_POLICIES:
        s["overflow_policy"] = raw["overflow_policy"]
    if raw.get("switch_indicator") in INDICATORS:
        s["switch_indicator"] = raw["switch_indicator"]
    if raw.get("language") in ("auto",) + SUPPORTED:
        s["language"] = raw["language"]
    if raw.get("data_source") in ("api", "official"):
        s["data_source"] = raw["data_source"]
    if "official_hide_unsupported" in raw:
        s["official_hide_unsupported"] = bool(raw["official_hide_unsupported"])
    s["seen_providers"] = [x for x in (raw.get("seen_providers") or []) if isinstance(x, str)]
    entries = []
    for a in raw.get("entries") or []:
        if isinstance(a, dict) and a.get("path") and get_provider(a.get("provider", "")):
            wins = a.get("windows") if isinstance(a.get("windows"), dict) else {}
            entries.append({"provider": a["provider"], "path": str(a["path"]),
                            "label": str(a.get("label") or get_provider(a["provider"]).label(a["path"])),
                            "enabled": bool(a.get("enabled", True)),
                            "windows": {k: bool(v) for k, v in wins.items()}})
    s["entries"] = entries
    return s


def save_settings(s, path=None):
    """원자적으로 쓴다(tmp → replace)."""
    path = path or SETTINGS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def enabled_entries_of(settings):
    """켜진 항목. 공식 모드에서는 공식 데이터가 없는 제공자(Codex)를 숨긴다(설정 시)."""
    out = []
    official = settings["data_source"] == "official"
    for e in settings["entries"]:
        if not e["enabled"]:
            continue
        p = get_provider(e["provider"])
        if not p:
            continue
        if official and not p.supports_official and settings["official_hide_unsupported"]:
            continue
        out.append(e)
    return out


def merge_discovered(entries, providers=None):
    """제공자들을 자동 탐색해 목록에 없는 계정을 뒤에 붙인다. 새로 붙은 개수."""
    known = {(e["provider"], os.path.normcase(os.path.abspath(e["path"]))) for e in entries}
    added = 0
    for p in providers or PROVIDERS:
        for d in p.discover():
            if (p.id, os.path.normcase(d)) not in known:
                entries.append({"provider": p.id, "path": d, "label": p.label(d), "enabled": True, "windows": {}})
                known.add((p.id, os.path.normcase(d)))
                added += 1
    return added


def ensure_discovered(s):
    """처음 실행 또는 새 제공자가 추가됐을 때만 자동 탐색 (Windows 판의 seen_providers 규칙과 같다). 바뀌었으면 True."""
    new = [p for p in PROVIDERS if p.id not in s["seen_providers"]]
    if not new:
        return False
    merge_discovered(s["entries"], new)
    s["seen_providers"] = sorted(set(s["seen_providers"]) | {p.id for p in new})
    return True


__all__ = ["APP_SUPPORT", "DEFAULT_SETTINGS", "MODES", "SLIDE_CHOICES", "entry_key", "load_settings", "save_settings",
           "enabled_entries_of", "merge_discovered", "ensure_discovered"]
