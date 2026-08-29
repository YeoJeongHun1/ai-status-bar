"""
AppKit 그리기 — 메뉴 막대 제목(NSAttributedString), 미리보기 이미지, 메뉴 상단 «항목 카드» 이미지.

- build_attributed(runs): 조각마다 색(초록/노랑/빨강) + Bars 조각은 NSTextAttachment(미니 막대 PNG) — 상태 항목 버튼과 미리보기가 같은 함수를 쓴다.
- runs_image(runs): 미리보기·프리셋 카드용 — 어두운 둥근 배경 위에 제목을 그대로 그린다 (Windows 미리보기와 같은 팔레트).
- card_image(...): 메뉴 상단 카드 — 서비스 칩 · 라벨 · 창별 미니 막대와 % · 리셋 · 모델별 칩 · 플랜 칩 · 조회/오류 (Windows 툴팁 카드와 같은 구성).
"""
from AppKit import (NSAttributedString, NSBezierPath, NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName,
                    NSImage, NSMutableAttributedString, NSTextAttachment)
from Foundation import NSData, NSMakeRect

from i18n import t, tr_error
from providers import color_for, fmt_reset, get as get_provider
from . import title as T

COLORS = {"green": "systemGreenColor", "yellow": "systemYellowColor", "red": "systemRedColor"}
PROVIDER_COLOR = {"claude_code": (0xD9, 0x77, 0x57), "codex": (0x10, 0xA3, 0x7F)}
PREVIEW_BG = (32, 32, 32)
CARD_W = 300


def rgb(c, a=1.0):
    r, g, b = c[:3]
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def tier_color(pct):
    return getattr(NSColor, COLORS[T.tier(pct)])()


def menu_font():
    return NSFont.monospacedDigitSystemFontOfSize_weight_(NSFont.menuBarFontOfSize_(0).pointSize(), 0.0)


def bars_image(values):
    """title.bar_png → NSImage (포인트 크기 지정, 템플릿 아님 = 색 유지)."""
    png = T.bar_png(values)
    img = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(png, len(png)))
    if img is None:
        raise RuntimeError("NSImage from PNG failed")
    img.setSize_(T.bar_size_pt())
    img.setTemplate_(False)
    return img


def build_attributed(runs, fg=None, label_color=None):
    """runs → NSAttributedString. fg 를 주면 기본 글자색을 그것으로(미리보기), label_color 는 라벨 조각(pct None 이고 T.LABEL 태그)."""
    font = menu_font()
    attr = NSMutableAttributedString.alloc().init()
    w_pt, h_pt = T.bar_size_pt()
    y = font.descender() + (font.ascender() - font.descender() - h_pt) / 2.0     # 글자 세로 중앙에 맞춘다
    base = fg or NSColor.labelColor()
    for s, pct in runs:
        if isinstance(s, T.Bars):
            att = NSTextAttachment.alloc().init()
            att.setImage_(bars_image(s.values))
            att.setBounds_(((0, y), (w_pt, h_pt)))
            attr.appendAttributedString_(NSAttributedString.attributedStringWithAttachment_(att))
            continue
        if isinstance(s, T.Label):
            color = label_color or base
            s = s.text
        else:
            color = tier_color(pct) if pct is not None else base
        attr.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(
            s, {NSFontAttributeName: font, NSForegroundColorAttributeName: color}))
    return attr


def describe_attributed(attr):
    """검사용: 글자 수·첨부 이미지 수와 크기."""
    n, sizes = 0, []
    s = attr.string()
    for i, ch in enumerate(s):
        if ch == "￼":
            att = attr.attribute_atIndex_effectiveRange_("NSAttachment", i, None)[0]
            img = att.image() if att is not None else None
            n += 1
            sizes.append(tuple(img.size()) if img is not None else None)
    return {"chars": len(s), "attachments": n, "image_sizes": sizes}


def width_of(runs):
    return float(build_attributed(runs).size().width)


def _image(size, draw):
    """flipped(위가 0) 좌표계로 그리는 NSImage. draw(w, h) 는 AppKit 호출로 그린다."""
    w, h = size

    def handler(rect):
        draw(w, h)
        return True
    return NSImage.imageWithSize_flipped_drawingHandler_((w, h), True, handler)


def _fill_round(x, y, w, h, r, color):
    color.setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), r, r).fill()


def _text(s, x, y, size=11, bold=False, color=None, mono=False):
    font = (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)) if not mono \
        else NSFont.monospacedDigitSystemFontOfSize_weight_(size, 0.6 if bold else 0.0)
    a = NSAttributedString.alloc().initWithString_attributes_(
        s, {NSFontAttributeName: font, NSForegroundColorAttributeName: color or NSColor.labelColor()})
    a.drawAtPoint_((x, y))
    return float(a.size().width)


def _chip(text, x, cy, bg, fg=None, size=10, pad=7):
    font = NSFont.boldSystemFontOfSize_(size)
    a = NSAttributedString.alloc().initWithString_attributes_(
        text, {NSFontAttributeName: font, NSForegroundColorAttributeName: fg or NSColor.whiteColor()})
    tw, th = a.size().width, a.size().height
    hh = th + 4
    _fill_round(x, cy - hh / 2, tw + 2 * pad, hh, hh / 2, bg)
    a.drawAtPoint_((x + pad, cy - th / 2))
    return x + tw + 2 * pad


def runs_image(runs, min_w=120, pad_x=8, pad_y=4, bg=PREVIEW_BG, label_color=None):
    """제목 조각을 어두운 둥근 배경에 그린 이미지 (미리보기·프리셋 카드). 크기는 내용에 맞춘다."""
    attr = build_attributed(runs, fg=rgb((240, 240, 240)), label_color=label_color)
    size = attr.size()
    w, h = max(min_w, float(size.width) + 2 * pad_x), float(size.height) + 2 * pad_y

    def draw(W, H):
        _fill_round(0, 0, W, H, 6, rgb(bg))
        attr.drawAtPoint_((pad_x, pad_y))
    return _image((w, h), draw)


def card_image(entry, d, plan, show_scoped, official, highlighted=False, width=CARD_W):
    """메뉴 상단 항목 카드. d = {"usage","error","next_try","saved_at","last_ok"} (없으면 조회 전)."""
    from datetime import datetime
    p = get_provider(entry["provider"])
    d = d or {}
    u = d.get("usage")
    pad, line = 10, 20
    wins = T.entry_windows(entry, u) if u else []
    rows = 1 + (len(wins) if u else 1) + (1 if u and u.get("scoped") and show_scoped else 0) + 1
    H = pad * 2 + rows * line

    def draw(W, H_):
        if highlighted:
            _fill_round(0, 0, W, H_, 8, NSColor.controlAccentColor().colorWithAlphaComponent_(0.18))
        y = pad + line / 2
        x = _chip(p.name, pad, y, rgb(PROVIDER_COLOR.get(p.id, (85, 85, 85))))
        label = entry["label"] if len(entry["label"]) <= 18 else entry["label"][:18] + "…"
        _text(label, x + 8, y - 8, 12, bold=True)
        y += line
        if u:
            for w in wins:
                col = tier_color(w["pct"])
                _text(w["key"], pad, y - 7, 10, color=NSColor.secondaryLabelColor())
                bx, bw, bh = pad + 26, 120, 7
                _fill_round(bx, y - bh / 2, bw, bh, bh / 2, NSColor.tertiaryLabelColor())
                fw = bw * min(w["pct"], 100) / 100
                if fw > 0:
                    _fill_round(bx, y - bh / 2, max(fw, bh), bh, bh / 2, col)
                _text(f"{w['pct']:.0f}%", bx + bw + 8, y - 8, 12, bold=True, color=col, mono=True)
                _text(t("tt_reset", t=fmt_reset(w["resets_at"]) or "—"), bx + bw + 52, y - 7, 10, color=NSColor.secondaryLabelColor())
                y += line
            if u.get("scoped") and show_scoped:
                x = pad
                for s_ in u["scoped"]:
                    x = _chip(f"{s_['model']} {s_['pct']:.0f}%", x, y, rgb((51, 51, 51)), fg=tier_color(s_["pct"])) + 6
                y += line
        else:
            msg = t("tt_error", err=tr_error(d["error"])) if d.get("error") else t("tt_loading")
            if d.get("error") and d.get("next_try"):
                msg += "  " + t("tt_next_try", time=d["next_try"].strftime("%H:%M"))
            _text(msg, pad, y - 7, 10, color=NSColor.systemOrangeColor() if d.get("error") else NSColor.secondaryLabelColor())
            y += line
        x = pad
        if plan:
            x = _chip(str(plan), x, y, rgb((47, 59, 82)), fg=rgb((207, 224, 255))) + 8
        if d.get("error") and u:
            msg = t("tt_error", err=tr_error(d["error"]))
            if d.get("next_try"):
                msg += "  " + t("tt_next_try", time=d["next_try"].strftime("%H:%M"))
            _text(msg, x, y - 7, 10, color=NSColor.systemOrangeColor())
        elif official and d.get("saved_at"):
            age = int((datetime.now() - d["saved_at"]).total_seconds() // 60)
            _text(t("tt_official_ago", m=age) if age >= 1 else t("tt_official"), x, y - 7, 10, color=NSColor.secondaryLabelColor())
        elif d.get("last_ok"):
            _text(t("tt_fetched_only", time=d["last_ok"].strftime("%H:%M:%S")), x, y - 7, 10, color=NSColor.secondaryLabelColor())
    return _image((width, H), draw)


def color_from_hex(hexv):
    try:
        r, g, b = int(hexv[1:3], 16), int(hexv[3:5], 16), int(hexv[5:7], 16)
        return rgb((r, g, b))
    except Exception:
        return None


def hex_from_color(color):
    try:
        from AppKit import NSColorSpace
        c = color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
        return "#%02x%02x%02x" % (round(c.redComponent() * 255), round(c.greenComponent() * 255), round(c.blueComponent() * 255))
    except Exception:
        return ""
