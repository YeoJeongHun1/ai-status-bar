"""py2app 설정 — build_mac.sh 가 부른다:  python setup_mac.py py2app
만드는 것: dist/AI Status Bar.app (LSUIElement — Dock 아이콘 없음, 번들 ID com.yeojeonghun.ai-status-bar → 알림에 앱 이름이 뜬다)."""
import os
import sys

from setuptools import setup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from version import __version__      # noqa: E402

APP = ["ai_status_bar_mac.py"]
DATA_FILES = ["statusline_export.sh"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "mac/AIStatusBar.icns",
    "packages": ["mac", "providers", "rumps", "PIL", "Quartz"],
    "includes": ["i18n", "polling", "applog", "version"],
    "excludes": ["tkinter", "test", "unittest", "pydoc_data", "setuptools", "pip", "wheel", "py2app"],
    "plist": {
        "CFBundleName": "AI Status Bar",
        "CFBundleDisplayName": "AI Status Bar",
        "CFBundleIdentifier": "com.yeojeonghun.ai-status-bar",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSUIElement": True,                                   # 메뉴 막대 전용 — Dock·⌘Tab 에 안 나온다
        "LSMinimumSystemVersion": "12.0",
        "NSHumanReadableCopyright": "MIT — YeoJeongHun1. Unaffiliated with Anthropic or OpenAI.",
        "NSAppleEventsUsageDescription": "Not used.",
    },
}

setup(name="AI Status Bar", app=APP, data_files=DATA_FILES, options={"py2app": OPTIONS}, setup_requires=["py2app"])
