"""macOS 미니 막대 PNG — 크기(2x)·트랙/채움 픽셀 색·빈 값·runs 안의 Bars 자리 (AppKit 없이 Pillow 만)."""
import io

from PIL import Image

from mac import title as T
from providers import color_for

GREEN, YELLOW, RED = color_for(10), color_for(60), color_for(90)


def png(values, **kw):
    return Image.open(io.BytesIO(T.bar_png(values, **kw))).convert("RGBA")


def test_size_is_2x_of_points():
    w_pt, h_pt = T.bar_size_pt()
    assert (w_pt, h_pt) == (36, 12)
    img = png([23, 66])
    assert img.size == (72, 24)
    assert png([23, 66], scale=3).size == (108, 36)


def test_fill_and_track_pixels():
    img = png([23, 85])
    W = img.width
    lh, gap = T.BAR_LINE_PT * 2, T.BAR_GAP_PT * 2
    y5, y7 = lh // 2, lh + gap + lh // 2                     # 위 줄(5h)·아래 줄(7d) 세로 중앙
    assert img.getpixel((4, y5))[:3] == GREEN and img.getpixel((4, y5))[3] == 255
    assert img.getpixel((round(W * 0.23) - 3, y5))[:3] == GREEN
    assert img.getpixel((round(W * 0.60), y5)) == T.TRACK_RGBA          # 23% 너머는 반투명 트랙
    assert img.getpixel((4, y7))[:3] == RED
    assert img.getpixel((round(W * 0.80), y7))[:3] == RED
    assert img.getpixel((W - 2, y7)) == T.TRACK_RGBA
    assert img.getpixel((4, lh + gap // 2)) == (0, 0, 0, 0)               # 줄 사이는 투명


def test_yellow_tier_and_clamp():
    img = png([60, 250])
    lh, gap = T.BAR_LINE_PT * 2, T.BAR_GAP_PT * 2
    assert img.getpixel((4, lh // 2))[:3] == YELLOW
    assert img.getpixel((img.width - 2, lh + gap + lh // 2))[:3] == RED   # 100% 로 잘라 끝까지 채운다


def test_missing_values_leave_empty_tracks():
    img = png([None, None])
    lh = T.BAR_LINE_PT * 2
    assert img.getpixel((4, lh // 2)) == T.TRACK_RGBA
    assert img.getpixel((4, lh // 2 + lh + T.BAR_GAP_PT * 2)) == T.TRACK_RGBA
    assert png([40]).getpixel((4, lh // 2 + lh + T.BAR_GAP_PT * 2)) == T.TRACK_RGBA   # 창이 하나면 아래는 빈 트랙
    assert png([]).size == (72, 24)


def _entry(label, provider="claude_code"):
    return {"provider": provider, "path": "/p/" + label, "label": label, "enabled": True, "windows": {}}


def _usage(p5, p7):
    return {"usage": {"windows": [{"key": "5h", "pct": p5, "resets_at": None}, {"key": "7d", "pct": p7, "resets_at": None}],
                      "scoped": []}, "error": None}


def test_runs_contain_bars_before_numbers():
    e = _entry("work")
    k = lambda x: x["path"]
    runs = T.build_runs([e], {k(e): _usage(23, 66)}, k, False, False, bars=True)
    assert runs[0] == (T.Bars([23, 66]), None) and runs[1] == (" ", None)
    assert T.plain(runs) == " 5h 23% · 7d 66%"                              # plain 은 막대 자리를 뺀다
    assert T.with_dots(runs) == " 5h 🟢23% · 7d 🟡66%"
    a, b = _entry("work"), _entry("home", "codex")
    runs = T.build_runs([a, b], {k(a): _usage(23, 66), k(b): _usage(4, 12)}, k, True, False, bars=True)
    assert [r for r in runs if isinstance(r[0], T.Bars)] == [(T.Bars([23, 66]), None), (T.Bars([4, 12]), None)]
    assert T.plain(runs) == "work  23%/66% · home  4%/12%"
    assert T.plain(T.build_runs([a], {}, k, False, False, bars=True)) == " …"
    assert T.build_runs([a], {}, k, False, False, bars=True)[0] == (T.Bars([None, None]), None)


def test_want_bars_matches_windows_values():
    assert T.want_bars("auto") and T.want_bars("bars") and not T.want_bars("numbers")
