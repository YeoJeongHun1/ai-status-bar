"""
AI Status Bar — macOS 메뉴 막대 판. Claude Code · Codex 구독의 5시간 / 7일 사용률을 메뉴 막대 글자로 보여준다.

    5h 23% · 7d 66%          (항목 하나)          C 23%/66% · X 4%/12%     (여럿)

- 자격증명: Claude Code 는 macOS 키체인 «Claude Code-credentials»(파일이 있으면 파일), Codex 는 ~/.codex/auth.json.
- 조회·파싱·네트워크 규칙(리다이렉트 금지·허용 호스트·백오프)은 Windows 판과 같은 providers/ · polling.py 를 쓴다.
- 설정: ~/Library/Application Support/AIStatusBar/settings.json   로그: ~/Library/Logs/AIStatusBar/error.log
- 자동 시작: ~/Library/LaunchAgents/com.yeojeonghun.ai-status-bar.plist

실행:  python ai_status_bar_mac.py            필요 패키지: requirements-mac.txt (rumps · pyobjc-framework-Cocoa · pillow)
       --autostart / --no-autostart          LaunchAgent 등록(+즉시 기동) / 해제(+종료)
       --unlink-statusline                   모든 Claude 계정 폴더의 상태줄 연결 해제 (제거 전에)
       --setup                               설정 창 열기 (이미 떠 있으면 그 인스턴스의 창을 연다)
"""
import fcntl
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import applog                                                             # noqa: E402


def single_instance():
    from mac.paths import APP_SUPPORT, LOCK_PATH
    os.makedirs(APP_SUPPORT, exist_ok=True)
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return fh                                   # 닫히면 잠금이 풀리므로 프로세스가 사는 동안 들고 있는다


def unlink_statusline_all():
    from mac.settings import load_settings
    from providers import claude_code as cc, get as get_provider
    s = load_settings()
    dirs = [e["path"] for e in s["entries"] if e["provider"] == "claude_code"]
    if not dirs:
        dirs = get_provider("claude_code").discover()
    return cc.unlink_all(dirs)


def main(argv):
    if sys.platform != "darwin":
        print("ai_status_bar_mac.py is for macOS; on Windows run ai_status_bar.py", file=sys.stderr)
        return 2
    if "--autostart" in argv:
        from mac import launchagent
        print(launchagent.enable(start=True))
        return 0
    if "--no-autostart" in argv:
        from mac import launchagent
        launchagent.disable(unload=True)
        return 0
    if "--unlink-statusline" in argv:
        for d in unlink_statusline_all():
            print("unlinked:", d)
        return 0
    lock = single_instance()
    if lock is None:                                 # 이미 떠 있다 — --setup 이면 그 인스턴스에 «설정 창 열어»
        if "--setup" in argv:
            from Foundation import NSDistributedNotificationCenter
            from mac.paths import OPEN_SETTINGS_NOTE
            NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(
                OPEN_SETTINGS_NOTE, None, None, True)
        return 0
    applog.install_crash_handlers()
    from mac.app import MacStatusBar
    from mac.paths import SETTINGS_PATH
    first_run = not os.path.exists(SETTINGS_PATH)    # 처음 실행: 시작 설정 창을 먼저 (Windows 와 같다)
    app = MacStatusBar(install_mode=first_run or "--setup" in argv)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
