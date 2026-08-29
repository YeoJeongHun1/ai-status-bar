"""
로그인 시 자동 시작 — LaunchAgent 하나 (~/Library/LaunchAgents/com.yeojeonghun.ai-status-bar.plist).

- RunAtLoad true · KeepAlive false: 로그인 때 한 번 띄우고, 사용자가 «종료» 하면 다시 살리지 않는다.
- ProgramArguments = [venv 파이썬, ai_status_bar_mac.py] — 설치 스크립트(mac/install.sh)가 만든 venv 의 경로를 그대로 쓴다.
- stdout/stderr 는 ~/Library/Logs/AIStatusBar/launchd.log (트레이스백은 applog 의 error.log 에도 남는다).
- 앱 안에서 «끄기» 는 plist 만 지운다 — 지금 도는 프로세스가 launchd 가 띄운 것일 수 있어 bootout 하면 자기 자신이 죽는다.
  명령줄 --no-autostart 와 uninstall.sh 는 bootout 까지 한다.
"""
import os
import plistlib
import subprocess

from .paths import ENTRY_SCRIPT, LAUNCH_AGENT_PLIST, LAUNCH_AGENTS_DIR, LAUNCH_LABEL, LOG_DIR, PYTHON, ROOT_DIR


def _domain():
    return f"gui/{os.getuid()}"


def _launchctl(*args, timeout=20):
    return subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True, timeout=timeout)


def is_enabled():
    return os.path.isfile(LAUNCH_AGENT_PLIST)


def is_loaded():
    try:
        return _launchctl("print", f"{_domain()}/{LAUNCH_LABEL}").returncode == 0
    except Exception:
        return False


def plist_dict(python=None, script=None):
    args = [python or PYTHON]
    if script is not None or ENTRY_SCRIPT is not None:
        args.append(script or ENTRY_SCRIPT)
    return {
        "Label": LAUNCH_LABEL,
        "ProgramArguments": args,
        "WorkingDirectory": ROOT_DIR,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": os.path.join(LOG_DIR, "launchd.log"),
        "StandardErrorPath": os.path.join(LOG_DIR, "launchd.log"),
    }


def write_plist(python=None, script=None):
    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    tmp = LAUNCH_AGENT_PLIST + ".tmp"
    with open(tmp, "wb") as f:
        plistlib.dump(plist_dict(python, script), f)
    os.replace(tmp, LAUNCH_AGENT_PLIST)
    return LAUNCH_AGENT_PLIST


def enable(start=False, python=None, script=None):
    """plist 를 쓴다. start=True 면 launchd 에 올려 지금 바로 띄운다(이미 올라가 있으면 그대로 둔다)."""
    write_plist(python, script)
    if start and not is_loaded():
        r = _launchctl("bootstrap", _domain(), LAUNCH_AGENT_PLIST)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or f"launchctl bootstrap rc={r.returncode}").strip())
    return LAUNCH_AGENT_PLIST


def disable(unload=False):
    """plist 삭제. unload=True 면 launchd 에서도 내린다 — 그 잡이 띄운 앱은 함께 종료된다."""
    if unload and is_loaded():
        _launchctl("bootout", f"{_domain()}/{LAUNCH_LABEL}")
    if os.path.isfile(LAUNCH_AGENT_PLIST):
        os.remove(LAUNCH_AGENT_PLIST)
