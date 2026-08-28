"""
메뉴 막대 제목 — 순수 함수만 (AppKit 없이 테스트한다).

runs = [(text, pct|None), ...]  — pct 가 있으면 그 조각을 초록(<50) / 노랑(50~79) / 빨강(80+) 으로 칠한다.

  항목 1개:            5h 23% · 7d 66%                (라벨 켜면  work 5h 23% · 7d 66%)
  항목 여럿(동시에):    C 23%/66% · X 4%/12%           (라벨 켜면  work 23%/66% · home 4%/12%)
  조회 전:             …      오류:  ⚠      계정 없음:  AI —
"""
from providers import color_for

INITIALS = {"claude_code": "C", "codex": "X"}      # 라벨을 끈 채 항목이 여럿일 때 서비스 머리글자
DOTS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def tier(pct):
    r, g, b = color_for(pct)
    return "red" if r == 220 else "yellow" if r == 230 else "green"


def pick_visible(entries, mode, cur, fixed_key, key_of):
    """표시 방식에 따라 지금 제목에 넣을 항목들. (cur 는 click/slide 의 현재 인덱스)"""
    if not entries:
        return []
    if mode == "fixed":
        for e in entries:
            if key_of(e) == fixed_key:
                return [e]
        return [entries[0]]
    if mode in ("click", "slide"):
        return [entries[cur % len(entries)]]
    return list(entries)


def entry_windows(e, usage):
    return [w for w in usage["windows"] if e["windows"].get(w["key"], True)]


def entry_runs(e, d, prefix, single, show_scoped):
    """항목 하나의 조각들. d = {"usage", "error", ...} (없으면 조회 전)."""
    runs = []
    if prefix:
        runs.append((prefix + " ", None))
    usage = (d or {}).get("usage")
    if not usage:
        runs.append(("⚠" if (d or {}).get("error") else "…", None))
        return runs
    wins = entry_windows(e, usage)
    if not wins:
        runs.append(("—", None))
    elif single:
        for i, w in enumerate(wins):
            runs.append((("" if i == 0 else " · ") + w["key"] + " ", None))
            runs.append((f"{w['pct']:.0f}%", w["pct"]))
        if show_scoped:
            for s in usage.get("scoped") or []:
                runs.append((f" · {s['model']} ", None))
                runs.append((f"{s['pct']:.0f}%", s["pct"]))
    else:
        for i, w in enumerate(wins):
            if i:
                runs.append(("/", None))
            runs.append((f"{w['pct']:.0f}%", w["pct"]))
    if (d or {}).get("error"):
        runs.append((" ⚠", None))
    return runs


def build_runs(visible, data, key_of, show_label, show_scoped, no_entries_text="AI —"):
    if not visible:
        return [(no_entries_text, None)]
    single = len(visible) == 1
    runs = []
    for i, e in enumerate(visible):
        if i:
            runs.append((" · ", None))
        prefix = e["label"] if show_label else ("" if single else INITIALS.get(e["provider"], e["provider"][:1].upper()))
        runs += entry_runs(e, data.get(key_of(e)), prefix, single, show_scoped)
    return runs


def plain(runs):
    return "".join(t for t, _ in runs)


def with_dots(runs):
    """색을 못 입힐 때의 폴백 — 퍼센트 앞에 ●색 이모지."""
    return "".join((DOTS[tier(p)] + t) if p is not None else t for t, p in runs)
