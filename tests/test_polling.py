"""조회 폭주 방지: POLL_SEC 하한, 수동 새로고침 디바운스, 429/5xx 백오프."""
from datetime import datetime, timedelta

import polling


def test_clamp_poll_sec():
    assert polling.clamp_poll_sec("300") == 300
    assert polling.clamp_poll_sec(None) == 300
    assert polling.clamp_poll_sec("") == 300
    assert polling.clamp_poll_sec("abc") == 300
    assert polling.clamp_poll_sec("0") == 300
    assert polling.clamp_poll_sec("-5") == 300
    assert polling.clamp_poll_sec("10") == 60          # 60초 밑으로는 못 내린다
    assert polling.clamp_poll_sec("900") == 900


def test_manual_refresh_debounce_five_clicks_one_call():
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    db = polling.Debounce(gap_sec=10)
    allowed = [db.allow(t0 + timedelta(seconds=i)) for i in range(5)]   # 5연타 (1초 간격)
    assert allowed == [True, False, False, False, False]
    assert db.allow(t0 + timedelta(seconds=10)) is True


def test_backoff_respects_retry_after_and_grows_on_5xx():
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    bo = polling.Backoff()
    assert bo.fail("k", "err_429 120", now=t0) is True
    assert bo.next_try("k") == t0 + timedelta(seconds=120)
    assert bo.blocked("k", t0 + timedelta(seconds=119))
    assert not bo.blocked("k", t0 + timedelta(seconds=120))
    bo.ok("k")
    assert bo.next_try("k") is None
    # 5xx: 60 → 120 → 240 … 최대 1800
    delays = []
    now = t0
    for _ in range(7):
        bo.fail("k", "err_http 503", now=now)
        delays.append(int((bo.next_try("k") - now).total_seconds()))
        now = bo.next_try("k")
    assert delays == [60, 120, 240, 480, 960, 1800, 1800]
    # 401·토큰 없음은 백오프 대상이 아니다 (사용자가 고쳐야 함)
    bo2 = polling.Backoff()
    assert bo2.fail("k", "err_401", now=t0) is False
    assert bo2.fail("k", "err_no_token", now=t0) is False
    assert bo2.next_try("k") is None


def test_run_refresh_skips_blocked_entries_and_records_next_try():
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    calls = []

    def fetch(e):
        calls.append(e)
        if e == "bad":
            raise RuntimeError("err_429 300")
        return {"windows": [], "scoped": [], "fetched_at": t0}, None

    data, bo = {}, polling.Backoff()
    assert polling.run_refresh(["good", "bad"], fetch, data, bo, now=t0) == 2
    assert data["good"]["usage"] and data["good"]["error"] is None and data["good"]["next_try"] is None
    assert data["bad"]["error"] == "err_429 300" and data["bad"]["next_try"] == t0 + timedelta(seconds=300)
    # 5분 안 재조회: bad 는 건너뛴다 (호출 1건)
    assert polling.run_refresh(["good", "bad"], fetch, data, bo, now=t0 + timedelta(seconds=60)) == 1
    assert calls.count("bad") == 1
    # Retry-After 지난 뒤엔 다시 부른다
    assert polling.run_refresh(["good", "bad"], fetch, data, bo, now=t0 + timedelta(seconds=300)) == 2
