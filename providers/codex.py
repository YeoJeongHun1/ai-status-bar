"""
Codex 제공자 — ChatGPT 구독(Plus/Pro/Team)으로 쓰는 OpenAI Codex CLI 의 5시간 / 주간 사용률.

계정 = Codex 설정 폴더 (기본 %USERPROFILE%\\.codex, 또는 CODEX_HOME). 그 안의 auth.json 을 읽는다.
  auth.json: {"auth_mode": "chatgpt", "tokens": {"id_token", "access_token", "refresh_token", "account_id"}, "last_refresh"}
  - 라벨·플랜·만료는 JWT(id_token / access_token) 의 claim 을 로컬에서 디코드해 얻는다. 서명 검증은 하지 않는다(표시용).
  - auth_mode 가 "apikey" 이거나 tokens 가 없으면(API 키 방식) 사용량 창이 없어 지원하지 않는다.

요청 (5분마다, 읽기 전용):
  GET https://chatgpt.com/backend-api/wham/usage
  Authorization: Bearer <access_token>   ·   ChatGPT-Account-Id: <account_id>
응답에서 읽는 것: rate_limit.primary_window.{used_percent, reset_at, limit_window_seconds} → 5h,
                  rate_limit.secondary_window.{…} → 7d.   (email·user_id 등 나머지는 읽지 않는다)
비공식 엔드포인트(OpenAI 가 문서화하지 않음). 토큰 갱신은 하지 않는다 — Codex CLI 가 한다.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from . import Provider

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
DEFAULT_CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
CLAIM_AUTH = "https://api.openai.com/auth"
CLAIM_PROFILE = "https://api.openai.com/profile"


class Codex(Provider):
    id = "codex"
    name = "Codex (ChatGPT)"
    short = "Codex"
    cred_file = "auth.json"
    usage_page = "https://chatgpt.com/codex/settings/usage"
    supports_official = False
    help_key = "help_codex_body"

    def discover(self):
        """CODEX_HOME + 홈의 .codex* 중 auth.json 이 있는 것."""
        found, seen = [], set()
        home = os.path.expanduser("~")
        cands = []
        if os.environ.get("CODEX_HOME"):
            cands.append(os.environ["CODEX_HOME"])
        try:
            cands += [os.path.join(home, n) for n in sorted(os.listdir(home)) if n.startswith(".codex")]
        except OSError:
            pass
        for d in cands:
            d = os.path.abspath(d)
            key = os.path.normcase(d)
            if key in seen or not os.path.isfile(os.path.join(d, self.cred_file)):
                continue
            seen.add(key)
            found.append(d)
        return found

    def label(self, path):
        try:
            tok = _tokens(path)
            for jwt in (tok.get("id_token"), tok.get("access_token")):
                email = (_claims(jwt).get(CLAIM_PROFILE) or {}).get("email")
                if email:
                    return email.split("@")[0]
        except Exception:
            pass
        name = os.path.basename(os.path.normpath(path))
        return "default" if name == ".codex" else name.lstrip(".").replace("codex-", "") or name

    def info(self, path):
        cp = os.path.join(path, self.cred_file)
        info = {"connected": False, "path": cp, "reason": "", "plan": None, "expires_at": None}
        if not os.path.exists(cp):
            info["reason"] = "err_codex_no_auth"
            return info
        try:
            auth = _load(path)
        except Exception as e:
            info["reason"] = f"err_token_read {e}"
            return info
        tok = auth.get("tokens") or {}
        if auth.get("auth_mode") == "apikey" or not tok.get("access_token"):
            info["reason"] = "err_codex_apikey"
            return info
        c = _claims(tok["access_token"])
        exp = datetime.fromtimestamp(float(c.get("exp") or 0)) if c.get("exp") else None
        plan = ((c.get(CLAIM_AUTH) or {}).get("chatgpt_plan_type") or "").capitalize() or None
        info.update(plan=plan, expires_at=exp, connected=bool(exp and exp > datetime.now()))
        if not info["connected"]:
            info["reason"] = "err_codex_401"
        return info

    def fetch(self, path):
        cp = os.path.join(path, self.cred_file)
        if not os.path.exists(cp):
            raise RuntimeError("err_codex_no_auth")
        auth = _load(path)
        tok = auth.get("tokens") or {}
        if auth.get("auth_mode") == "apikey" or not tok.get("access_token"):
            raise RuntimeError("err_codex_apikey")
        headers = {
            "Authorization": f"Bearer {tok['access_token']}",
            "User-Agent": "ai-status-bar/1.0",
        }
        if tok.get("account_id"):
            headers["ChatGPT-Account-Id"] = tok["account_id"]
        req = urllib.request.Request(USAGE_URL, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return parse(json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError("err_codex_401") from None
            raise RuntimeError(f"err_http {e.code}") from None


def _load(path):
    with open(os.path.join(path, "auth.json"), encoding="utf-8") as f:
        return json.load(f)


def _tokens(path):
    return _load(path).get("tokens") or {}


def _claims(jwt):
    """JWT 본문(claims)만 base64url 디코드. 서명은 보지 않는다 — 표시용이니까."""
    try:
        part = jwt.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def parse(data):
    rl = data.get("rate_limit") or {}
    if not rl:
        raise RuntimeError("err_codex_nodata")

    def window(default_key, d):
        if not d or d.get("used_percent") is None:
            return None
        secs = d.get("limit_window_seconds") or 0
        key = default_key
        if secs:                                    # 창 길이가 바뀌어도 라벨이 따라가게
            key = f"{secs // 86400}d" if secs % 86400 == 0 and secs >= 86400 else f"{secs // 3600}h"
        reset = d.get("reset_at")
        return {"key": key, "pct": float(d["used_percent"]),
                "resets_at": datetime.fromtimestamp(float(reset)) if reset else None}

    windows = [w for w in (window("5h", rl.get("primary_window")), window("7d", rl.get("secondary_window"))) if w]
    return {"windows": windows, "scoped": [], "fetched_at": datetime.now()}
