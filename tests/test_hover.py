"""호버 카드 안전망: Leave 가 오지 않거나 무시돼도 커서가 바를 떠나면 카드가 한 주기 안에 닫히는가.

26-09-29 실입력 재현: 커서가 항목 사이 투명 픽셀(마우스가 작업 표시줄로 통과)에 올라가면 Leave 가 오지만 커서는 아직
창 사각형 안이라 «가짜 Leave» 로 무시된다. 그 뒤 창 밖으로 나갈 때는 Leave 가 다시 오지 않아 카드가 영영 남았다
(hovering 도 True 로 남아 주기 재측정·자동 슬라이드까지 멈춘다).
"""
from types import SimpleNamespace

import pytest

import ai_status_bar as B
import taskbar as tb


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def after(self, ms, fn=None):
        self.n += 1
        self.jobs[self.n] = fn
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run_pending(self):
        jobs, self.jobs = self.jobs, {}
        for fn in jobs.values():
            if fn:
                fn()


class FakeTip:
    def __init__(self):
        self.alive = True

    def destroy(self):
        self.alive = False


@pytest.fixture
def app(monkeypatch):
    cur = SimpleNamespace(over=True)
    monkeypatch.setattr(tb, "cursor_over", lambda hwnd: cur.over)
    a = B.StatusBar.__new__(B.StatusBar)
    a.root = FakeRoot()
    a.hwnd = "BAR"
    a.hovering = False
    a.tooltip = a.mini_tip = a.tooltip_job = a.leave_job = a.cycle_job = None
    a.hover_guard_job = None
    a.tooltip_entry = None
    a.hidden_fullscreen = False
    a.set_hover = lambda e, dots=False: None
    a.schedule_cycle = lambda: None
    a.cur_state = cur
    return a


def show_card(a):
    a.on_enter()
    a.tooltip = FakeTip()
    a.tooltip_entry = object()
    a.arm_hover_guard()
    return a.tooltip


def test_leave_dropped_card_closes(app):
    tip = show_card(app)
    app.root.run_pending()                     # 커서가 위에 있는 동안은 그대로
    assert app.tooltip is tip and tip.alive
    app.cur_state.over = False                 # Leave 이벤트 없이 떠남
    app.root.run_pending()
    assert app.tooltip is None and not tip.alive and not app.hovering


def test_leave_ignored_on_transparent_pixel_then_exit(app):
    tip = show_card(app)
    app.on_leave()                             # 투명 픽셀 위 Leave — 커서는 아직 창 안이라 무시된다
    assert app.leave_job is None and app.tooltip is tip
    app.cur_state.over = False                 # 그 뒤 창 밖으로 — Leave 는 다시 오지 않는다
    app.root.run_pending()
    assert app.tooltip is None and not app.hovering


def test_guard_stops_when_nothing_is_open(app):
    show_card(app)
    app.cur_state.over = False
    app.root.run_pending()
    app.root.run_pending()
    assert app.hover_guard_job is None and not app.root.jobs


def test_close_hover_when_bar_hidden_for_fullscreen(app):
    show_card(app)
    app.hidden_fullscreen = True
    app.root.run_pending()
    assert app.tooltip is None
