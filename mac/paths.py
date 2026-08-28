"""macOS 경로 — 전부 사용자 홈 아래. 시스템 폴더·레지스트리 격의 것은 건드리지 않는다."""
import os
import sys

APP_TITLE = "AI Status Bar"
APP_NAME = "AIStatusBar"
LAUNCH_LABEL = "com.yeojeonghun.ai-status-bar"
REPO_URL = "https://github.com/YeoJeongHun1/ai-status-bar"
README_URL = REPO_URL + "#readme"
SUPPORT_URL = "https://github.com/sponsors/YeoJeongHun1"

HOME = os.path.expanduser("~")
APP_SUPPORT = os.path.join(HOME, "Library", "Application Support", APP_NAME)
SETTINGS_PATH = os.path.join(APP_SUPPORT, "settings.json")
LOCK_PATH = os.path.join(APP_SUPPORT, "app.lock")
VENV_DIR = os.path.join(APP_SUPPORT, "venv")
LOG_DIR = os.path.join(HOME, "Library", "Logs", APP_NAME)
LAUNCH_AGENTS_DIR = os.path.join(HOME, "Library", "LaunchAgents")
LAUNCH_AGENT_PLIST = os.path.join(LAUNCH_AGENTS_DIR, LAUNCH_LABEL + ".plist")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # 저장소(풀어 둔 폴더)
ENTRY_SCRIPT = os.path.join(ROOT_DIR, "ai_status_bar_mac.py")
STATUSLINE_SH = os.path.join(ROOT_DIR, "statusline_export.sh")
PYTHON = sys.executable
