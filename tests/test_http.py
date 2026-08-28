"""리다이렉트 시 토큰이 새는지 — 로컬 서버 두 개로 실증한다.

A(첫 서버)가 302 로 B(다른 포트 = 다른 오리진)로 보낸다. 기본 urllib 은 Authorization 을 그대로 들고 B 로 따라가지만,
providers/http.get_json 은 30x 에서 멈추고 B 에는 아무 요청도 보내지 않아야 한다."""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from providers import http as phttp


class _Recorder(BaseHTTPRequestHandler):
    hits = []
    redirect_to = None
    status = 200
    body = b'{"ok": true}'
    extra_headers = {}

    def do_GET(self):
        type(self).hits.append({"path": self.path, "authorization": self.headers.get("Authorization")})
        if type(self).redirect_to:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.end_headers()
            return
        self.send_response(type(self).status)
        for k, v in type(self).extra_headers.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *a):
        pass


def _serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


@pytest.fixture
def servers():
    class A(_Recorder):
        hits = []

    class B(_Recorder):
        hits = []
    a, a_url = _serve(A)
    b, b_url = _serve(B)
    A.redirect_to = b_url + "/stolen"
    yield A, a_url, B, b_url
    a.shutdown()
    b.shutdown()


def test_default_urllib_forwards_token_on_redirect(servers):
    """리뷰어의 실증 재현: 기본 opener 는 다른 오리진으로 튕겨도 Authorization 을 붙여 보낸다."""
    A, a_url, B, b_url = servers
    req = urllib.request.Request(a_url + "/usage", headers={"Authorization": "Bearer sk-ant-TEST"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
    assert B.hits and B.hits[0]["authorization"] == "Bearer sk-ant-TEST"


def test_get_json_refuses_redirect_and_never_contacts_second_host(servers):
    A, a_url, B, b_url = servers
    with pytest.raises(RuntimeError) as ei:
        phttp.get_json(a_url + "/usage", {"Authorization": "Bearer sk-ant-TEST"}, allowed_hosts=("127.0.0.1",))
    assert str(ei.value) == "err_redirect"
    assert len(A.hits) == 1
    assert B.hits == []                      # 두 번째 서버는 요청 자체를 받지 않는다


def test_get_json_refuses_hosts_outside_allow_list():
    with pytest.raises(RuntimeError) as ei:
        phttp.get_json("https://evil.example/usage", {"Authorization": "Bearer x"})
    assert str(ei.value).startswith("err_host")


def test_get_json_maps_429_with_retry_after_and_5xx():
    class H(_Recorder):
        hits = []
    srv, url = _serve(H)
    try:
        H.status, H.extra_headers = 429, {"Retry-After": "120"}
        with pytest.raises(RuntimeError) as ei:
            phttp.get_json(url + "/u", {}, allowed_hosts=("127.0.0.1",))
        assert str(ei.value) == "err_429 120"
        H.status, H.extra_headers = 503, {}
        with pytest.raises(RuntimeError) as ei:
            phttp.get_json(url + "/u", {}, allowed_hosts=("127.0.0.1",))
        assert str(ei.value) == "err_http 503"
        H.status, H.body = 200, json.dumps({"a": 1}).encode()
        assert phttp.get_json(url + "/u", {}, allowed_hosts=("127.0.0.1",)) == {"a": 1}
    finally:
        srv.shutdown()


def test_get_json_network_error_key():
    with pytest.raises(RuntimeError) as ei:
        phttp.get_json("http://127.0.0.1:9/never", {}, allowed_hosts=("127.0.0.1",), timeout=2)
    assert str(ei.value) == "err_network"


def test_providers_only_use_the_helper():
    """제공자 파일에 urlopen 이 직접 등장하지 않는다 — 네트워크 코드는 http.get_json 하나뿐."""
    import inspect
    from providers import claude_code, codex
    for mod in (claude_code, codex):
        src = inspect.getsource(mod)
        assert "urlopen" not in src and "urllib.request" not in src
        assert "http.get_json(" in src
