"""
Claude Code 제공자 — Claude 구독(Pro/Max)의 5시간 / 7일 사용률.

계정 = Claude Code 설정 폴더 (기본 %USERPROFILE%\\.claude, 또는 CLAUDE_CONFIG_DIR). 그 안의 .credentials.json 을 읽는다.

두 가지 데이터 원본
- API 모드: GET https://api.anthropic.com/api/oauth/usage (비공식·문서화 안 됨) 를 5분마다.
- 공식 모드: Claude Code 상태줄이 공식으로 넘겨주는 rate_limits 만 읽는다 (네트워크 0).
    Claude Code ──(상태줄 JSON, stdin)──▶ statusline_export.ps1 ──▶ %LOCALAPPDATA%\\AIStatusBar\\official\\<key>.json
                                                    └──(원래 상태줄 명령이 있으면 그대로 파이프)──▶ 화면
  key = 설정 폴더 경로 normcase(소문자·끝 구분자 제거) 의 UTF-8 SHA-1 앞 12자 — ps1 과 같은 규칙.
  «상태줄 연결 설치» 는 그 폴더의 settings.json 을 백업(settings.json.bak-aistatusbar)한 뒤 statusLine 을 export 스크립트로
  바꾸고, 원래 statusLine 은 이 앱 폴더(official/<key>.original.json)에 보관한다 — Claude Code 의 settings.json 에
  낯선 키를 넣지 않기 위해서다(스키마가 거부하는 값이 있으면 Claude Code 가 «Settings Error» 를 띄운다).
"""
import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime

from . import Provider

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
DEFAULT_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
OFFICIAL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AIStatusBar", "official")
STALE_AFTER_SEC = 600          # 이보다 오래된 상태줄 데이터는 흐리게 + «N분 전»
PS1_NAME = "statusline_export.ps1"
BACKUP_SUFFIX = ".bak-aistatusbar"


class ClaudeCode(Provider):
    id = "claude_code"
    name = "Claude Code"
    short = "Claude"
    cred_file = ".credentials.json"
    usage_page = "https://claude.ai/settings/usage"
    supports_official = True
    help_key = "help_claude_body"

    # --- 계정 ---
    def discover(self):
        """CLAUDE_CONFIG_DIR + 홈의 .claude* 중 .credentials.json 이 있는 것."""
        found, seen = [], set()
        home = os.path.expanduser("~")
        cands = []
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            cands.append(os.environ["CLAUDE_CONFIG_DIR"])
        try:
            cands += [os.path.join(home, n) for n in sorted(os.listdir(home)) if n.startswith(".claude")]
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
        """로그인 때 저장되는 .claude.json 의 oauthAccount.emailAddress 앞부분. 없으면 폴더 이름."""
        home = os.path.expanduser("~")
        candidates = [os.path.join(path, ".claude.json")]
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.join(home, ".claude")):
            candidates.append(os.path.join(home, ".claude.json"))   # 기본 폴더는 홈에 .claude.json 이 있다
        for p in candidates:
            try:
                with open(p, encoding="utf-8") as f:
                    email = (json.load(f).get("oauthAccount") or {}).get("emailAddress")
                if email:
                    return email.split("@")[0]
            except Exception:
                pass
        name = os.path.basename(os.path.normpath(path))
        return "default" if name == ".claude" else name.lstrip(".").replace("claude-", "") or name

    def info(self, path):
        cp = os.path.join(path, self.cred_file)
        info = {"connected": False, "path": cp, "reason": "", "plan": None, "expires_at": None}
        if not os.path.exists(cp):
            info["reason"] = "err_no_token"
            return info
        try:
            with open(cp, encoding="utf-8") as f:
                oauth = json.load(f)["claudeAiOauth"]
        except Exception as e:
            info["reason"] = f"err_token_read {e}"
            return info
        exp = datetime.fromtimestamp((oauth.get("expiresAt") or 0) / 1000)
        plan = (oauth.get("subscriptionType") or "").capitalize()
        if oauth.get("rateLimitTier"):
            plan += f" ({oauth['rateLimitTier']})"
        info.update(plan=plan.strip() or None, expires_at=exp, connected=exp > datetime.now())
        if not info["connected"]:
            info["reason"] = "err_token_expired"
        return info

    # --- API 모드 ---
    def fetch(self, path):
        cp = os.path.join(path, self.cred_file)
        if not os.path.exists(cp):
            raise RuntimeError("err_no_token")
        with open(cp, encoding="utf-8") as f:
            oauth = json.load(f)["claudeAiOauth"]
        token, expires_at = oauth["accessToken"], oauth.get("expiresAt", 0)
        if expires_at and expires_at / 1000 < datetime.now().timestamp():
            raise RuntimeError("err_token_expired")
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "ai-status-bar/1.0",
        }
        req = urllib.request.Request(USAGE_URL, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return parse(json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("err_401") from None
            raise RuntimeError(f"err_http {e.code}") from None

    # --- 공식 모드 ---
    def fetch_official(self, path):
        return read_official(path)


def parse(data):
    """응답에서 화면에 필요한 것만 뽑는다."""
    def window(key, d):
        if not d:
            return None
        return {"key": key, "pct": float(d.get("utilization") or 0), "resets_at": to_local(d.get("resets_at"))}

    windows = [w for w in (window("5h", data.get("five_hour")), window("7d", data.get("seven_day"))) if w]
    scoped = []
    for lim in data.get("limits") or []:
        if lim.get("kind") == "weekly_scoped":
            model = ((lim.get("scope") or {}).get("model") or {}).get("display_name") or "?"
            scoped.append({"model": model, "pct": float(lim.get("percent") or 0)})
    return {"windows": windows, "scoped": scoped, "fetched_at": datetime.now()}


def to_local(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone()


# ---------- 공식 모드: 상태줄 export 파일 ----------

def official_key(config_dir):
    norm = os.path.normcase(os.path.abspath(config_dir)).rstrip("\\/")
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def official_path(config_dir):
    return os.path.join(OFFICIAL_DIR, official_key(config_dir) + ".json")


def original_path(config_dir):
    return os.path.join(OFFICIAL_DIR, official_key(config_dir) + ".original.json")


def read_official(config_dir):
    """상태줄 export 파일 → usage + saved_at. 없으면 err_official_missing, rate_limits 가 아직 없으면 err_official_nodata."""
    path = official_path(config_dir)
    if not os.path.isfile(path):
        raise RuntimeError("err_official_missing")
    with open(path, encoding="utf-8") as f:
        wrapper = json.load(f)
    saved_at = datetime.fromtimestamp(float(wrapper.get("saved_at") or 0))
    rl = (wrapper.get("statusline") or {}).get("rate_limits") or {}
    if not rl:
        raise RuntimeError("err_official_nodata")

    def window(key, d):
        if not d or d.get("used_percentage") is None:
            return None
        resets = d.get("resets_at")
        return {"key": key, "pct": float(d["used_percentage"]),
                "resets_at": datetime.fromtimestamp(float(resets)) if resets else None}

    windows = [w for w in (window("5h", rl.get("five_hour")), window("7d", rl.get("seven_day"))) if w]
    return {"windows": windows, "scoped": [], "fetched_at": saved_at}, saved_at


# ---------- 상태줄 연결 설치 / 해제 (계정 폴더의 settings.json) ----------

def settings_path(config_dir):
    return os.path.join(config_dir, "settings.json")


def backup_path(config_dir):
    return settings_path(config_dir) + BACKUP_SUFFIX


def export_command(ps1_path):
    return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"'


def _load(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def statusline_installed(config_dir):
    sl = _load(settings_path(config_dir)).get("statusLine") or {}
    return PS1_NAME in str(sl.get("command", ""))


def statusline_install(config_dir, ps1_path):
    """settings.json 백업 → statusLine 을 export 스크립트로 → 원래 statusLine 은 official/<key>.original.json 에."""
    sp = settings_path(config_dir)
    data = _load(sp)
    if os.path.isfile(sp):
        shutil.copy2(sp, backup_path(config_dir))
    original = data.get("statusLine")
    if original and PS1_NAME in str(original.get("command", "")):
        original = None                     # 이미 우리 것 — 원본은 보관본 그대로
    else:
        os.makedirs(OFFICIAL_DIR, exist_ok=True)
        _save(original_path(config_dir), {"config_dir": config_dir, "original_statusLine": original})
    data["statusLine"] = {"type": "command", "command": export_command(ps1_path)}
    os.makedirs(config_dir, exist_ok=True)
    _save(sp, data)
    return backup_path(config_dir)


def statusline_uninstall(config_dir):
    """원래 statusLine 복원(없었으면 키 제거) + 보관본 삭제."""
    sp = settings_path(config_dir)
    data = _load(sp)
    original = None
    op = original_path(config_dir)
    if os.path.isfile(op):
        with open(op, encoding="utf-8") as f:
            original = json.load(f).get("original_statusLine")
    if original:
        data["statusLine"] = original
    else:
        data.pop("statusLine", None)
    _save(sp, data)
    if os.path.isfile(op):
        os.remove(op)
