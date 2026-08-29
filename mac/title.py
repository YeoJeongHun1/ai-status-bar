"""
메뉴 막대 제목 — 순수 함수만 (AppKit 없이 테스트한다).

runs = [(text, pct|None), ...]  — pct 가 있으면 그 조각을 초록(<50) / 노랑(50~79) / 빨강(80+) 으로 칠한다.
       막대 모드에서는 (Bars, None) 조각이 끼어든다 — 앱이 그 자리에 NSTextAttachment(미니 막대 이미지)를 넣는다.

  항목 1개:            [▬▬░░] 5h 23% · 7d 66%          (라벨 켜면  work [▬▬░░] 5h 23% · 7d 66%)
  항목 여럿(동시에):    C [▬▬░░] 23%/66% · X [▬░░░] 4%/12%
  숫자만:              5h 23% · 7d 66%
  조회 전:             …      오류:  ⚠      계정 없음:  AI —

막대 이미지(bar_png)는 Pillow 로 2x(레티나) 투명 PNG — 위 5h / 아래 7d, 트랙은 반투명 회색(다크·라이트 메뉴 막대 양쪽에서
보임), 채움은 Windows 와 같은 색 규칙. 값이 없으면 빈 트랙.
"""
import io

from providers import color_for

BAR_W_PT, BAR_LINE_PT, BAR_GAP_PT, BAR_SCALE = 36, 5, 2, 2
TRACK_RGBA = (128, 128, 128, 110)


class Bars:
    """제목 안의 막대 자리 — values = 창 순서대로 pct 또는 None (최대 2개: 5h, 7d)."""
    __slots__ = ("values",)

    def __init__(self, values):
        self.values = tuple(values)

    def __eq__(self, other):
        return isinstance(other, Bars) and other.values == self.values

    def __repr__(self):
        return f"Bars({list(self.values)})"


def bar_size_pt(lines=2):
    return BAR_W_PT, lines * BAR_LINE_PT + (lines - 1) * BAR_GAP_PT


def bar_png(values, scale=BAR_SCALE, lines=2):
    """values → 투명 PNG bytes (scale 배 픽셀). 항상 lines 줄을 그린다(값이 모자라면 빈 트랙)."""
    from PIL import Image, ImageDraw
    w_pt, h_pt = bar_size_pt(lines)
    W, H = w_pt * scale, h_pt * scale
    lh, gap = BAR_LINE_PT * scale, BAR_GAP_PT * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    vals = (list(values) + [None] * lines)[:lines]
    for i, pct in enumerate(vals):
        y0 = i * (lh + gap)
        y1 = y0 + lh - 1
        d.rounded_rectangle((0, y0, W - 1, y1), radius=lh // 2, fill=TRACK_RGBA)
        if pct is not None:
            fill_w = max(lh, round(W * max(0.0, min(100.0, float(pct))) / 100))
            d.rounded_rectangle((0, y0, fill_w - 1, y1), radius=lh // 2, fill=color_for(pct) + (255,))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

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


def entry_runs(e, d, prefix, single, show_scoped, bars=False):
    """항목 하나의 조각들. d = {"usage", "error", ...} (없으면 조회 전). bars=True 면 숫자 앞에 (Bars, None)."""
    runs = []
    if prefix:
        runs.append((prefix + " ", None))
    usage = (d or {}).get("usage")
    if not usage:
        if bars:
            runs.append((Bars([None, None]), None))
            runs.append((" ", None))
        runs.append(("⚠" if (d or {}).get("error") else "…", None))
        return runs
    wins = entry_windows(e, usage)
    if bars:
        runs.append((Bars([w["pct"] for w in wins][:2]), None))
        runs.append((" ", None))
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


def build_runs(visible, data, key_of, show_label, show_scoped, no_entries_text="AI —", bars=False):
    if not visible:
        return [(no_entries_text, None)]
    single = len(visible) == 1
    runs = []
    for i, e in enumerate(visible):
        if i:
            runs.append((" · ", None))
        prefix = e["label"] if show_label else ("" if single else INITIALS.get(e["provider"], e["provider"][:1].upper()))
        runs += entry_runs(e, data.get(key_of(e)), prefix, single, show_scoped, bars)
    return runs


def want_bars(bars_style):
    """설정 style.bars — Windows 와 같은 값(auto / bars / numbers). 메뉴 막대엔 폭 측정이 없어 auto = 막대 + 숫자."""
    return bars_style != "numbers"


def plain(runs):
    return "".join(t for t, _ in runs if not isinstance(t, Bars))


def with_dots(runs):
    """색을 못 입힐 때의 폴백 — 퍼센트 앞에 ●색 이모지 (막대 자리는 뺀다)."""
    return "".join((DOTS[tier(p)] + t) if p is not None else t for t, p in runs if not isinstance(t, Bars))
