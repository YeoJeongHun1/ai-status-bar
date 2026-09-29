"""배치 안정성: 캡처 제외 «구멍» 이 우리 자신을 내용으로 세지 않는가 · 튀는 측정 한 번에 자리를 옮기지 않는가.

26-09-29 실측 결함: WDA_EXCLUDEFROMCAPTURE 창이 캡처에 순흑(0,0,0) 으로 찍히고 작업 표시줄 배경(~34)과 차이가
CONTENT_DIFF(28)를 넘어, 첫 빈 공간이 우리 창 양옆 조각으로 쪼개졌다 → 20초 재측정마다 왼쪽↔오른쪽 조각을 오가며
폭(=표시 단계)까지 바뀌고, 조절 알림이 되풀이됐다. 여기서는 합성 작업 표시줄로 그 상황을 그대로 재현한다.
"""
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

import ai_status_bar as B
import layout
import taskbar as tb

W, H = 2560, 48
BG = (34, 34, 34)
WIDGETS_RIGHT = 158


def world(bar=None, extra=()):
    """작업 표시줄 캡처 한 장: 맨 위 1px 경계선, 위젯 글자, 가운데 앱 아이콘 묶음, 트레이.
    bar = 우리 창 (x0, x1) — 캡처 제외 창은 이 PC 에서처럼 순흑 구멍으로 찍힌다. extra = 이 캡처에만 있는 내용 (x0, x1)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.line([(0, 0), (W, 0)], fill=(67, 67, 67))
    d.rectangle([20, 12, 73, 36], fill=(230, 230, 230))           # 위젯 (날씨) 글자
    for x in range(849, 1700, 56):                                  # 앱 아이콘
        d.rectangle([x, 10, x + 32, 38], fill=(80, 160, 230))
    d.rectangle([2280, 14, 2555, 34], fill=(220, 220, 220))         # 트레이·시계
    for x0, x1 in extra:
        d.rectangle([x0, 8, x1 - 1, 40], fill=(240, 240, 240))
    if bar:
        d.rectangle([bar[0], 0, bar[1] - 1, H - 1], fill=(0, 0, 0))
    return img


MIN_W = 24 + 2 * 16


def test_hole_of_own_window_is_not_content():
    img = world(bar=(186, 829))
    split, _ = tb.free_gaps_from_image(img, 0, MIN_W)                 # 우리 창을 모르면 (옛 동작) 구멍이 내용으로 잡힌다
    assert split[0] == (74, 186)
    gaps, bg = tb.free_gaps_from_image(img, 0, MIN_W, own=(186, 829))
    assert any(a <= 186 and 829 <= b for a, b in gaps), gaps
    assert gaps[0] == (74, 849) and bg == BG


def test_see_through_build_keeps_real_content_under_us():
    """밑이 비쳐 찍히는 빌드: 우리 창 자리에 진짜 내용이 있으면 구멍이 아니므로 그대로 내용으로 본다."""
    img = world(extra=[(500, 560)])
    gaps, _ = tb.free_gaps_from_image(img, 0, MIN_W, own=(186, 829))
    assert not any(a <= 186 and 829 <= b for a, b in gaps)


def test_spot_clear_and_settle():
    assert layout.spot_clear((186, 786), [(74, 849)], 10)
    assert not layout.spot_clear((186, 786), [(74, 790)], 10)
    s = layout.Settle(need=2, tol=4)
    cur = [(186, 829)]
    assert s.offer(cur, [(186, 831)]) == "same"
    assert s.offer(cur, [(186, 780)]) == "wait"
    assert s.offer(cur, [(186, 829)]) == "same" and s.pending is None      # 튄 값이 사라지면 대기도 해제
    assert s.offer(cur, [(186, 780)]) == "wait"
    assert s.offer(cur, [(186, 781)]) == "accept"


class FakeRoot:
    def __init__(self):
        self.jobs = []
        self.shown = True

    def state(self):
        return "normal" if self.shown else "withdrawn"

    def withdraw(self):
        self.shown = False

    def deiconify(self):
        self.shown = True

    def after(self, ms, fn=None):
        if fn:
            self.jobs.append(fn)
            return len(self.jobs)

    def update(self):
        pass

    def configure(self, **kw):
        pass

    def attributes(self, *a):
        pass


@pytest.fixture
def sim(monkeypatch):
    """StatusBar.measure 를 가짜 화면 위에서 돌린다. 창 배치는 앱과 같게: 첫 후보 구간 왼쪽 끝, 폭 = min(need, 구간 폭)."""
    st = SimpleNamespace(bar=None, extra=[], grabs=0, need=600, noise_once=None)

    def grab(bbox=None, **kw):
        st.grabs += 1
        extra = list(st.extra)
        if st.noise_once:
            extra.append(st.noise_once)
            st.noise_once = None
        own = st.bar if app.root.shown else None
        return world(bar=own, extra=extra).crop(bbox)

    monkeypatch.setattr(tb.ImageGrab, "grab", grab)
    monkeypatch.setattr(tb, "taskbar", lambda: "TB")
    monkeypatch.setattr(tb, "widgets_button_right", lambda: WIDGETS_RIGHT)
    monkeypatch.setattr(tb, "user32", SimpleNamespace(IsWindowVisible=lambda h: 1))
    monkeypatch.setattr(tb, "win_rect", lambda h: (0, 0, W, H) if h == "TB" else (st.bar[0], 0, st.bar[1], H))

    app = B.StatusBar.__new__(B.StatusBar)
    app.scale = 1.0
    app.capture_excluded = True
    app.gaps = []
    app.settle = layout.Settle()
    app.settle_job = None
    app.hidden_fullscreen = False
    app.hovering = False
    app.root = FakeRoot()
    app.canvas = SimpleNamespace(configure=lambda **kw: None)
    app.hwnd = "BAR"

    def place():
        g = app.gaps[0]
        st.bar = (g[0], g[0] + min(st.need, g[1] - g[0]))
        app.root.shown = True

    def measure(settle=True):
        app.measure(settle)
        place()
        return st.bar

    st.app, st.measure = app, measure
    app.root.shown = False                   # 기동: 창이 아직 없다 (withdraw 상태)
    app.measure(False)
    place()
    return st


def test_periodic_remeasure_does_not_wander(sim):
    """고치기 전: 186 → 515 → 186 … 20초마다 왼쪽↔오른쪽 조각을 오갔다 (이 PC 실측과 같은 좌표)."""
    first = sim.bar
    assert first == (186, 786)
    positions = [sim.measure()[0] for _ in range(10)]
    assert positions == [186] * 10


def test_one_off_noise_does_not_move_or_shrink(sim):
    """한 캡처에만 나타난 내용(다른 앱 툴팁·아이콘 애니메이션)이 우리 오른쪽 여백 너머 구간을 줄여도
    자리·구간을 바꾸지 않는다 (바꾸면 600px 가 안 들어가 표시 단계가 바뀌고 알림이 뜬다)."""
    gaps0 = list(sim.app.gaps)
    sim.noise_once = (800, 815)
    sim.measure()
    assert sim.app.gaps == gaps0 and sim.bar == (186, 786)
    assert sim.app.settle_job is not None                 # 곧 한 번 더 재서 확인한다
    sim.measure()                                         # 확인 측정: 잡음이 사라졌다
    assert sim.app.gaps == gaps0 and sim.app.settle.pending is None


def test_sustained_change_is_adopted_after_confirmation(sim):
    sim.extra = [(800, 815)]
    sim.measure()
    assert sim.app.gaps[0] == (186, 829)                  # 첫 번째는 대기
    sim.measure()
    assert sim.app.gaps[0] == (186, 780)                  # 같은 결과 2연속 → 채택


def test_intrusion_into_our_margin_moves_immediately(sim):
    """아이콘 묶음이 우리 창 밑까지 밀고 들어오면(구멍 밑은 안 보인다) 여백에서 잡고, 숨긴 채 다시 재서 바로 옮긴다."""
    sim.extra = [(700, 849)]
    sim.measure()
    assert sim.app.gaps[0] == (186, 680) and sim.bar == (186, 680)
