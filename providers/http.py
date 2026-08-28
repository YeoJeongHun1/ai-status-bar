"""
제공자 공용 HTTP — 앱의 네트워크 코드는 이 파일의 get_json() 하나뿐이다.

지키는 것
- **리다이렉트를 따라가지 않는다.** 기본 urllib 은 30x 로 다른 호스트로 튕겨도 Authorization 헤더를 그대로 붙여 보낸다
  (프록시·DNS 오염·벤더의 30x 한 번이면 토큰 유출). 여기서는 30x 를 오류(err_redirect)로 끊는다.
- 요청 전에 URL 호스트가 허용 목록에 있는지 확인한다 — 코드 어딘가에서 URL 이 바뀌어도 다른 호스트로는 나가지 않는다.
- 본문 없음, GET 만, 타임아웃 15초.
- 429 는 Retry-After 를 읽어 «err_429 <초>» 로, 5xx 는 «err_http <코드>», 연결 실패는 «err_network» 로 던진다 —
  호출자(폴링)가 백오프에 쓴다.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = ("api.anthropic.com", "chatgpt.com")
TIMEOUT_SEC = 15


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """모든 30x 를 거부한다 — urllib 이 새 요청을 만들지 못하게 None 을 돌려주면 HTTPError 로 떨어진다."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect())


def host_of(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def retry_after_seconds(headers, default=60):
    """Retry-After 헤더(초 또는 HTTP 날짜) → 초. 없거나 못 읽으면 default."""
    v = (headers.get("Retry-After") if headers else None) or ""
    v = v.strip()
    if v.isdigit():
        return max(1, int(v))
    if v:
        try:
            from email.utils import parsedate_to_datetime
            from datetime import datetime, timezone
            dt = parsedate_to_datetime(v)
            return max(1, int((dt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            pass
    return default


def get_json(url, headers, allowed_hosts=ALLOWED_HOSTS, timeout=TIMEOUT_SEC, opener=None):
    """GET url → JSON(dict). 허용 호스트 밖이면 요청 자체를 하지 않는다.
    오류는 i18n 키로: err_redirect / err_401 / err_403 / err_429 <초> / err_http <코드> / err_network."""
    host = host_of(url)
    if host not in allowed_hosts:
        raise RuntimeError(f"err_host {host}")
    if urllib.parse.urlsplit(url).scheme != "https" and not host.startswith("127."):
        raise RuntimeError(f"err_host {host}")
    req = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with (opener or _opener).open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            raise RuntimeError("err_redirect") from None
        if e.code == 401:
            raise RuntimeError("err_401") from None
        if e.code == 403:
            raise RuntimeError("err_403") from None
        if e.code == 429:
            raise RuntimeError(f"err_429 {retry_after_seconds(e.headers)}") from None
        raise RuntimeError(f"err_http {e.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("err_network") from None
    except (TimeoutError, OSError):
        raise RuntimeError("err_network") from None
