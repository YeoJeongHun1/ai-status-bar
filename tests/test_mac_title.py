"""macOS 메뉴 막대 제목 조립 — AppKit 없이 순수 함수만."""
from datetime import datetime

from mac import title as T


def E(provider, label, path=None, windows=None):
    return {"provider": provider, "path": path or f"/p/{label}", "label": label, "enabled": True, "windows": windows or {}}


def U(p5, p7, scoped=None):
    return {"usage": {"windows": [{"key": "5h", "pct": p5, "resets_at": None}, {"key": "7d", "pct": p7, "resets_at": None}],
                      "scoped": scoped or [], "fetched_at": datetime.now()}, "error": None}


def key(e):
    return f"{e['provider']}|{e['path']}"


def test_single_entry_compact():
    e = E("claude_code", "work")
    runs = T.build_runs([e], {key(e): U(23, 66)}, key, show_label=False, show_scoped=False)
    assert T.plain(runs) == "5h 23% · 7d 66%"
    assert [p for _, p in runs if p is not None] == [23, 66]


def test_single_entry_with_label_and_scoped():
    e = E("claude_code", "work")
    runs = T.build_runs([e], {key(e): U(23, 66, [{"model": "Fable", "pct": 81}])}, key, show_label=True, show_scoped=True)
    assert T.plain(runs) == "work 5h 23% · 7d 66% · Fable 81%"


def test_multiple_entries_use_initials():
    a, b = E("claude_code", "work"), E("codex", "home")
    runs = T.build_runs([a, b], {key(a): U(23, 66), key(b): U(4, 12)}, key, show_label=False, show_scoped=True)
    assert T.plain(runs) == "C 23%/66% · X 4%/12%"


def test_multiple_entries_with_labels():
    a, b = E("claude_code", "work"), E("codex", "home")
    runs = T.build_runs([a, b], {key(a): U(23, 66), key(b): U(4, 12)}, key, show_label=True, show_scoped=False)
    assert T.plain(runs) == "work 23%/66% · home 4%/12%"


def test_loading_error_and_no_entries():
    a = E("claude_code", "work")
    assert T.plain(T.build_runs([a], {}, key, False, False)) == "…"
    assert T.plain(T.build_runs([a], {key(a): {"usage": None, "error": "err_keychain_prompt"}}, key, False, False)) == "⚠"
    stale = U(50, 90)
    stale["error"] = "err_network"                       # 값은 있는데 이번 조회가 실패 → 값 + ⚠
    assert T.plain(T.build_runs([a], {key(a): stale}, key, False, False)) == "5h 50% · 7d 90% ⚠"
    assert T.plain(T.build_runs([], {}, key, False, False, "AI —")) == "AI —"


def test_window_filter_respects_entry_windows():
    a = E("claude_code", "work", windows={"5h": False, "7d": True})
    assert T.plain(T.build_runs([a], {key(a): U(23, 66)}, key, False, False)) == "7d 66%"


def test_pick_visible_modes():
    a, b, c = E("claude_code", "a"), E("codex", "b"), E("claude_code", "c", path="/p/c2")
    ents = [a, b, c]
    assert T.pick_visible(ents, "all", 0, "", key) == ents
    assert T.pick_visible(ents, "click", 4, "", key) == [b]
    assert T.pick_visible(ents, "slide", 2, "", key) == [c]
    assert T.pick_visible(ents, "fixed", 0, key(c), key) == [c]
    assert T.pick_visible(ents, "fixed", 0, "missing", key) == [a]
    assert T.pick_visible([], "all", 0, "", key) == []


def test_tier_and_dot_fallback():
    assert (T.tier(0), T.tier(49.9), T.tier(50), T.tier(79.9), T.tier(80), T.tier(100)) == \
        ("green", "green", "yellow", "yellow", "red", "red")
    e = E("claude_code", "w")
    runs = T.build_runs([e], {key(e): U(23, 85)}, key, False, False)
    assert T.with_dots(runs) == "5h 🟢23% · 7d 🔴85%"


def test_label_runs_and_tiers():
    e = E("claude_code", "work")
    runs = T.build_runs([e], {key(e): U(23, 66)}, key, True, False, bars=True)
    assert runs[0] == (T.Label("work "), None) and isinstance(runs[1][0], T.Bars)
    assert T.plain(runs) == "work  5h 23% · 7d 66%"
    assert T.plain(T.build_runs([e], {key(e): U(23, 66)}, key, False, False, bars=True, tier="compact")) == "5h 23% · 7d 66%"
    assert T.build_runs([e], {key(e): U(23, 66)}, key, False, False, tier="collapsed", prefix="●○ ") == [("●○ ›", None)]
    assert T.plain(T.build_runs([e], {key(e): U(23, 66)}, key, False, False, prefix="⇄ ")) == "⇄ 5h 23% · 7d 66%"
