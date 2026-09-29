"""
배치 안정화 — 순수 로직 (tk·Win32 없음, pytest 대상).

- spot_clear: 지금 우리 창 자리가 새 측정에서도 양옆 여유까지 비어 있나 (아니면 즉시 옮긴다).
- Settle: 지금 자리가 멀쩡한데 측정 결과만 달라졌으면, 같은 결과가 한 번 더 나올 때까지 옮기지 않는다.
  한 번 튄 측정(아이콘 깜빡임·다른 앱 툴팁·애니메이션)이 위치·표시 단계·알림을 흔들지 못하게 한다.
"""


def spot_clear(own, gaps, band):
    """우리 창 (x0, x1) 이 어느 빈 구간 안에 양옆 band px 여유를 두고 온전히 들어 있으면 True."""
    l, r = own
    return any(g0 <= l - band and r + band <= g1 for g0, g1 in gaps)


def same_gaps(a, b, tol):
    """빈 구간 목록이 개수·양끝 모두 tol px 안에서 같으면 True (몇 px 흔들림은 같은 것으로 본다)."""
    return len(a) == len(b) and all(abs(x0 - y0) <= tol and abs(x1 - y1) <= tol for (x0, x1), (y0, y1) in zip(a, b))


class Settle:
    """재측정 결과를 채택할지 정한다. offer() 가
    - "same"   : 지금과 (tol 안에서) 같다 → 아무것도 바꾸지 말 것 (몇 px 흔들림으로 창을 움직이지 않는다)
    - "wait"   : 다르지만 아직 한 번뿐 → 지금 자리를 유지하고 곧 다시 재 볼 것
    - "accept" : 같은 새 결과가 need 번 연속 → 채택"""

    def __init__(self, need=2, tol=4):
        self.need = need
        self.tol = tol
        self.pending = None
        self.count = 0

    def reset(self):
        self.pending = None
        self.count = 0

    def offer(self, current, new):
        if same_gaps(current, new, self.tol):
            self.reset()
            return "same"
        if self.pending is not None and same_gaps(self.pending, new, self.tol):
            self.count += 1
        else:
            self.pending, self.count = list(new), 1
        if self.count >= self.need:
            self.reset()
            return "accept"
        return "wait"
