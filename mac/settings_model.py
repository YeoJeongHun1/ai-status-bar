"""
설정 창·넘침 처리의 **순수 로직** — AppKit 없이 pytest 로 검증한다 (tests/test_mac_settings_model.py).

- 폼 ↔ 설정 dict (Windows 의 form_settings/snapshot 과 같은 규칙), 프리셋 6종(Windows 와 같은 값), 예시 데이터.
- 항목 행 조작: 이동·삭제·폴더 추가(중복/자격증명 파일 없음 판정)·다시 탐색.
- 넘침(overflow): Windows 의 3단계(막대+숫자 → 숫자만 → ›)와 정책(한 항목씩 슬라이드 / 숫자만+오른쪽 잘라 … / 접기 ›),
  복귀 히스테리시스(여유 OVERFLOW_SLACK pt), 알림 10분 간격. 폭 측정·화면은 호출자가 넣는다.
- 캐러셀 전환 표시: 점 ● ○ ○ / ⇄ / 없음 → 제목 앞 글리프.
"""
import json
import os
from datetime import datetime, timedelta

from providers import get as get_provider

from .settings import BAR_STYLES, DEFAULT_SETTINGS, INDICATORS, MODES, OVERFLOW_POLICIES, PLACEMENTS, PROVIDERS, entry_key

OVERFLOW_SLACK_PT = 40           # «모두 동시에» 로 복귀하려면 이만큼(pt) 여유가 있어야 한다 (경계 진동 방지)
OVERFLOW_NOTIFY_GAP_SEC = 600    # 자동 조절 알림은 마지막 알림 후 10분 안엔 다시 띄우지 않는다
OVERFLOW_PROBE_SEC = 60          # 자동 조절 중일 때 원래 단계로 돌아갈 수 있는지 다시 재보는 주기

PRESETS = (
    ("default", {"display_mode": "all", "show_scoped": False, "style": {"label": False, "bars": "bars"}}),
    ("minimal", {"display_mode": "all", "show_scoped": False, "style": {"label": False, "bars": "numbers"}}),
    ("click", {"display_mode": "click", "show_scoped": False, "style": {"label": False, "bars": "auto"}}),
    ("full", {"display_mode": "all", "show_scoped": True, "style": {"label": False, "bars": "bars"}}),
    ("slide", {"display_mode": "slide", "show_scoped": False, "style": {"label": True, "bars": "auto"}}),
    ("pinned", {"display_mode": "fixed", "show_scoped": True, "style": {"label": False, "bars": "auto"}}),
)
SAMPLE = {   # 실제 값이 없을 때 미리보기에 쓰는 예시 (Windows 와 같다)
    "claude_code": {"windows": [{"key": "5h", "pct": 42.0}, {"key": "7d", "pct": 71.0}], "scoped": [{"model": "Fable", "pct": 56.0}]},
    "codex": {"windows": [{"key": "5h", "pct": 18.0}, {"key": "7d", "pct": 33.0}], "scoped": []},
}
SAMPLE_ENTRIES = [{"provider": "claude_code", "path": "sample-claude", "label": "work", "enabled": True, "windows": {}},
                  {"provider": "codex", "path": "sample-codex", "label": "home", "enabled": True, "windows": {}}]


# ---------- 폼 ----------

def new_row(provider, path, label, enabled=True, windows=None):
    windows = windows or {}
    return {"provider": provider, "path": path, "label": label, "enabled": bool(enabled),
            "w5h": bool(windows.get("5h", True)), "w7d": bool(windows.get("7d", True))}


def rows_from_settings(settings):
    return [new_row(e["provider"], e["path"], e["label"], e["enabled"], e["windows"]) for e in settings["entries"]]


def form_from_settings(settings):
    st = settings["style"]
    return {"display_mode": settings["display_mode"], "slide_sec": settings["slide_sec"], "fixed_entry": settings["fixed_entry"],
            "show_scoped": settings["show_scoped"], "label": st["label"], "bars": st["bars"], "label_color": st["label_color"],
            "placement": settings["placement"], "overflow_policy": settings["overflow_policy"],
            "switch_indicator": settings["switch_indicator"], "language": settings["language"],
            "data_source": settings["data_source"], "official_hide_unsupported": settings["official_hide_unsupported"],
            "max_width_pt": settings.get("max_width_pt", 0), "autostart": None}


def clamp_slide(v):
    try:
        return max(5, min(3600, int(v)))
    except Exception:
        return 30


def form_to_settings(form, rows):
    """폼 값 + 항목 행 → 저장할 설정 dict (화이트리스트 밖 값은 기본값)."""
    entries = []
    for r in rows:
        p = get_provider(r["provider"])
        entries.append({"provider": r["provider"], "path": r["path"],
                        "label": (r["label"] or "").strip() or p.label(r["path"]),
                        "enabled": bool(r["enabled"]), "windows": {"5h": bool(r["w5h"]), "7d": bool(r["w7d"])}})
    keys = {entry_key(e) for e in entries}
    fixed = form.get("fixed_entry") or ""
    if fixed not in keys:
        fixed = next(iter(keys), "") if entries else ""
    d = json.loads(json.dumps(DEFAULT_SETTINGS))
    d.update({
        "entries": entries,
        "display_mode": form["display_mode"] if form["display_mode"] in MODES else "all",
        "slide_sec": clamp_slide(form["slide_sec"]),
        "fixed_entry": fixed,
        "show_scoped": bool(form["show_scoped"]),
        "style": {"label": bool(form["label"]), "bars": form["bars"] if form["bars"] in BAR_STYLES else "auto",
                  "label_color": form["label_color"] if _is_hex(form.get("label_color")) else ""},
        "placement": form["placement"] if form["placement"] in PLACEMENTS else "left",
        "overflow_policy": form["overflow_policy"] if form["overflow_policy"] in OVERFLOW_POLICIES else "slide",
        "switch_indicator": form["switch_indicator"] if form["switch_indicator"] in INDICATORS else "dots",
        "language": form["language"],
        "data_source": form["data_source"] if form["data_source"] in ("api", "official") else "api",
        "official_hide_unsupported": bool(form["official_hide_unsupported"]),
        "max_width_pt": max(0, min(2000, int(form.get("max_width_pt") or 0))),
        "seen_providers": [p.id for p in PROVIDERS],
    })
    return d


def _is_hex(v):
    return isinstance(v, str) and len(v) == 7 and v.startswith("#")


def snapshot(form, rows):
    return json.dumps(form_to_settings(form, rows), sort_keys=True, ensure_ascii=False) + f"|auto={form.get('autostart')}"


def fixed_choices(rows):
    out = []
    for r in rows:
        p = get_provider(r["provider"])
        out.append((f"{r['provider']}|{r['path']}", f"{p.short} · {(r['label'] or '').strip() or p.label(r['path'])}"))
    return out


# ---------- 프리셋 ----------

def preset_matches(settings, values):
    if settings["display_mode"] != values["display_mode"] or settings["show_scoped"] != values["show_scoped"]:
        return False
    return all(settings["style"][k] == v for k, v in values["style"].items())


def apply_preset(form, values):
    form["display_mode"] = values["display_mode"]
    form["show_scoped"] = values["show_scoped"]
    form["label"] = values["style"]["label"]
    form["bars"] = values["style"]["bars"]
    return form


def preset_settings(values):
    """프리셋 카드 미리보기용 설정 — 예시 항목 2개(Claude·Codex)."""
    S = json.loads(json.dumps(DEFAULT_SETTINGS))
    S.update({k: v for k, v in values.items() if k != "style"})
    S["style"].update(values["style"])
    S["entries"] = json.loads(json.dumps(SAMPLE_ENTRIES))
    S["fixed_entry"] = entry_key(S["entries"][0])
    return S


def preview_data(entries, data, now=None):
    """실제 값이 있으면 실제, 없으면 예시값."""
    now = now or datetime.now()
    out = {}
    for e in entries:
        k = entry_key(e)
        real = data.get(k) or {}
        if real.get("usage"):
            out[k] = {"usage": real["usage"], "error": None, "saved_at": None}
            continue
        sm = SAMPLE.get(e["provider"]) or SAMPLE["codex"]
        wins = [{"key": w["key"], "pct": w["pct"], "resets_at": now.replace(microsecond=0)} for w in sm["windows"]]
        out[k] = {"usage": {"windows": wins, "scoped": list(sm["scoped"]), "fetched_at": now}, "error": None, "saved_at": None}
    return out


# ---------- 항목 행 조작 ----------

def move_row(rows, i, delta):
    j = i + delta
    if 0 <= i < len(rows) and 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
        return j
    return i


def add_folder(rows, provider, path):
    """→ ("dup" | "nocred" | "ok", row|None). nocred 여도 호출자가 확인 뒤 append 할 수 있게 행을 돌려준다."""
    path = os.path.abspath(path)
    if any(r["provider"] == provider.id and os.path.normcase(r["path"]) == os.path.normcase(path) for r in rows):
        return "dup", None
    row = new_row(provider.id, path, provider.label(path), True, {})
    if not os.path.isfile(os.path.join(path, provider.cred_file)):
        return "nocred", row
    rows.append(row)
    return "ok", row


def rescan(rows, providers=None):
    known = {(r["provider"], os.path.normcase(r["path"])) for r in rows}
    added = 0
    for p in providers or PROVIDERS:
        for d in p.discover():
            if (p.id, os.path.normcase(d)) not in known:
                rows.append(new_row(p.id, d, p.label(d), True, {}))
                known.add((p.id, os.path.normcase(d)))
                added += 1
    return added


# ---------- 캐러셀 전환 표시 ----------

def indicator_prefix(kind, cur, n):
    """click/slide 모드에서 제목 앞 글리프. dots: ● ○ ○ (현재 항목만 채움) / arrow: ⇄ / none: 없음."""
    if n <= 1:
        return ""
    if kind == "dots":
        return "".join("●" if i == cur % n else "○" for i in range(n)) + " "
    if kind == "arrow":
        return "⇄ "
    return ""


# ---------- 넘침 ----------

def tiers(bars_style):
    return {"auto": ("full", "compact", "collapsed"), "bars": ("full", "collapsed"),
            "numbers": ("compact", "collapsed")}.get(bars_style, ("full", "compact", "collapsed"))


class Overflow:
    """메뉴 막대 폭 넘침 상태 기계 (Windows 의 place_and_draw 와 같은 규칙).

    decide(width_of, available, settings, n_entries, now) → (tier, adjusted, notify)
      width_of(tier) : 그 단계로 그렸을 때 필요한 폭(pt) — 호출자가 잰다 (mode=all 기준)
      available      : 쓸 수 있는 폭(pt). None 이면 «알 수 없음» — 설정대로 둔다 (자동 조절 없음)
      tier           : 이번에 그릴 단계 (full / compact / collapsed)
      adjusted       : None(정상) / "slide" / "numbers" / "collapse" — 임시 조절 중인 정책
      notify         : 이번 호출에서 알림을 띄워야 하면 True (조절 시작 + 10분 간격)
    """

    def __init__(self, slack=OVERFLOW_SLACK_PT, notify_gap_sec=OVERFLOW_NOTIFY_GAP_SEC):
        self.slack, self.notify_gap = slack, timedelta(seconds=notify_gap_sec)
        self.adjusted = None
        self.tier = "full"
        self.last_notified = None

    def decide(self, width_of, available, settings, n_entries, now=None):
        now = now or datetime.now()
        order = tiers(settings["style"]["bars"])
        shrink = [x for x in order if x != "collapsed"]
        before = self.adjusted
        if available is None:
            self.adjusted, self.tier = None, shrink[0]
            return self.tier, None, False
        need_slack = self.slack if before else 0
        for tier in shrink:
            if width_of(tier) + need_slack <= available:
                self.adjusted, self.tier = None, tier
                return tier, None, False
        # 안 들어간다 → 정책대로
        policy = settings["overflow_policy"]
        if settings["display_mode"] != "all" or n_entries <= 1:
            policy = "numbers" if policy == "slide" else policy      # 한 항목뿐이면 슬라이드할 게 없다
        self.adjusted = policy
        self.tier = {"slide": shrink[-1], "numbers": shrink[-1], "collapse": "collapsed"}[policy]
        notify = before != policy and (self.last_notified is None or now - self.last_notified >= self.notify_gap)
        if notify:
            self.last_notified = now
        return self.tier, policy, notify


def clip_runs(runs, width_of, available, ellipsis="…"):
    """숫자만+오른쪽 잘라 … 정책: 조각을 뒤에서부터 떼어 available 안에 들어가는 만큼만 남기고 … 을 붙인다.
    width_of(runs) 는 호출자가 잰다. 최소한 첫 조각은 남긴다."""
    if width_of(runs) <= available:
        return runs
    kept = list(runs)
    while len(kept) > 1:
        kept.pop()
        cand = kept + [(ellipsis, None)]
        if width_of(cand) <= available:
            return cand
    return kept[:1] + [(ellipsis, None)]
