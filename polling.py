"""
조회 폭주 방지 — tkinter 와 무관한 순수 로직이라 pytest 로 검증한다.

- clamp_poll_sec: 환경변수 AI_STATUS_BAR_POLL_SEC 는 60초 미만·0·음수·문자를 받지 않는다 (기본 300).
- Debounce: 수동 «새로고침» 연타는 MIN_MANUAL_GAP 안에 한 번만.
- Backoff: 계정별로 429(Retry-After 존중)·5xx·네트워크 오류·(macOS) 키체인 거부/대기 때 60→120→240…최대 1800초 지수 백오프, 성공하면 리셋.
- run_refresh: 항목 목록을 돌며 fetch 를 부르되 백오프 중인 항목은 건너뛴다. 인플라이트 락은 호출자(StatusBar)가 건다.
"""
from datetime import datetime, timedelta

DEFAULT_POLL_SEC = 300
MIN_POLL_SEC = 60
MIN_MANUAL_GAP_SEC = 10
BACKOFF_FIRST_SEC = 60
BACKOFF_MAX_SEC = 1800


def clamp_poll_sec(raw, default=DEFAULT_POLL_SEC, minimum=MIN_POLL_SEC):
    """'300' → 300, '0'·'-5'·'abc'·None → default, '10' → minimum."""
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if v <= 0:
        return default
    return max(minimum, v)


class Debounce:
    def __init__(self, gap_sec=MIN_MANUAL_GAP_SEC):
        self.gap = timedelta(seconds=gap_sec)
        self.last = None

    def allow(self, now=None):
        """이번 수동 요청을 허용하면 True 로 답하고 시각을 기록한다."""
        now = now or datetime.now()
        if self.last is not None and now - self.last < self.gap:
            return False
        self.last = now
        return True


class Backoff:
    """키(항목)별 다음 시도 시각. 오류 종류에 따라 지연을 늘리고, 성공하면 지운다."""

    def __init__(self, first=BACKOFF_FIRST_SEC, maximum=BACKOFF_MAX_SEC):
        self.first, self.maximum = first, maximum
        self._state = {}          # key -> {"until": datetime, "delay": int}

    def blocked(self, key, now=None):
        st = self._state.get(key)
        return bool(st and (now or datetime.now()) < st["until"])

    def next_try(self, key):
        st = self._state.get(key)
        return st["until"] if st else None

    def ok(self, key):
        self._state.pop(key, None)

    def fail(self, key, error, now=None):
        """error 는 제공자 오류 문자열(«err_429 120» 등). 백오프 대상이면 다음 시도 시각을 정하고 True."""
        now = now or datetime.now()
        head, _, arg = str(error).partition(" ")
        if head == "err_429":
            delay = int(arg) if arg.isdigit() else self.first
            delay = max(1, min(self.maximum, delay))
        elif head == "err_http" and arg.isdigit() and int(arg) >= 500 or head in ("err_network", "err_keychain_denied", "err_keychain_prompt"):
            # 키체인 거부/다이얼로그 대기(macOS)도 지수 백오프 — 5분마다 «허용» 다이얼로그를 다시 띄우지 않게
            prev = self._state.get(key, {}).get("delay") or 0
            delay = min(self.maximum, prev * 2 if prev else self.first)
        else:
            return False                     # 401·토큰 없음 등은 사용자가 고쳐야 하는 것 — 백오프 안 함
        self._state[key] = {"until": now + timedelta(seconds=delay), "delay": delay}
        return True


def run_refresh(entries, fetch, data, backoff, now=None, key_of=lambda e: e):
    """항목마다 fetch(e) 를 부르고 data[key] 에 usage/error/last_ok/next_try 를 채운다.
    백오프 중인 항목은 부르지 않는다(값 유지, next_try 만 갱신). 호출한 항목 수를 돌려준다."""
    now = now or datetime.now()
    called = 0
    for e in entries:
        k = key_of(e)
        d = data.setdefault(k, {"usage": None, "error": None, "last_ok": None, "saved_at": None, "next_try": None})
        if backoff.blocked(k, now):
            d["next_try"] = backoff.next_try(k)
            continue
        called += 1
        try:
            d["usage"], d["saved_at"] = fetch(e)
            d["error"] = None
            d["last_ok"] = d["usage"]["fetched_at"]
            backoff.ok(k)
            d["next_try"] = None
        except Exception as ex:
            d["error"] = str(ex)[:120]
            d["next_try"] = backoff.next_try(k) if backoff.fail(k, d["error"], now) else None
    return called
