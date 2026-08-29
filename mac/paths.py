"""macOS 경로 — 전부 사용자 홈 아래. 시스템 폴더·레지스트리 격의 것은 건드리지 않는다."""
import os
import sys

APP_TITLE = "AI Status Bar"
APP_NAME = "AIStatusBar"
LAUNCH_LABEL = "com.yeojeonghun.ai-status-bar"
REPO_URL = "https://github.com/YeoJeongHun1/ai-status-bar"
README_URL = REPO_URL + "#readme"
SUPPORT_URL = "https://github.com/sponsors/YeoJeongHun1"
RELEASES_URL = REPO_URL + "/releases"
OPEN_SETTINGS_NOTE = LAUNCH_LABEL + ".open-settings"     # --setup → 실행 중인 인스턴스에 «설정 창 열어» (NSDistributedNotification)

HOME = os.path.expanduser("~")
APP_SUPPORT = os.path.join(HOME, "Library", "Application Support", APP_NAME)
SETTINGS_PATH = os.path.join(APP_SUPPORT, "settings.json")
LOCK_PATH = os.path.join(APP_SUPPORT, "app.lock")
VENV_DIR = os.path.join(APP_SUPPORT, "venv")
LOG_DIR = os.path.join(HOME, "Library", "Logs", APP_NAME)
LAUNCH_AGENTS_DIR = os.path.join(HOME, "Library", "LaunchAgents")
LAUNCH_AGENT_PLIST = os.path.join(LAUNCH_AGENTS_DIR, LAUNCH_LABEL + ".plist")

FROZEN = bool(getattr(sys, "frozen", False))                                # py2app 번들 안
if FROZEN:
    RESOURCES = os.environ.get("RESOURCEPATH") or os.path.dirname(os.path.abspath(sys.argv[0]))
    BUNDLE = os.path.dirname(os.path.dirname(RESOURCES))                        # …/AI Status Bar.app (Resources → Contents → .app)
    ROOT_DIR = BUNDLE                                                            # «실행 위치» 로 보여주는 것
    STATUSLINE_SH = os.path.join(RESOURCES, "statusline_export.sh")
    # LaunchAgent 는 번들의 실행 파일(CFBundleExecutable)을 가리킨다 (python + 스크립트가 아니라)
    try:
        import plistlib
        with open(os.path.join(BUNDLE, "Contents", "Info.plist"), "rb") as _f:
            _exe = plistlib.load(_f).get("CFBundleExecutable") or "AI Status Bar"
    except Exception:
        _exe = "AI Status Bar"
    PYTHON = os.path.join(BUNDLE, "Contents", "MacOS", _exe)
    ENTRY_SCRIPT = None
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # 저장소(풀어 둔 폴더)
    ENTRY_SCRIPT = os.path.join(ROOT_DIR, "ai_status_bar_mac.py")
    STATUSLINE_SH = os.path.join(ROOT_DIR, "statusline_export.sh")
    PYTHON = sys.executable
