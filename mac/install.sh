#!/bin/zsh
# AI Status Bar (macOS) 설치 — venv 생성 → 패키지 설치 → LaunchAgent 등록 → 즉시 기동.
#   zsh mac/install.sh              자동 시작 켬 + 지금 띄움
#   zsh mac/install.sh --no-autostart   venv 만 만들고 지금 한 번 띄움 (LaunchAgent 없음)
# 시스템 폴더·sudo 불필요. 만드는 것: ~/Library/Application Support/AIStatusBar/venv, settings.json,
#   ~/Library/LaunchAgents/com.yeojeonghun.ai-status-bar.plist, ~/Library/Logs/AIStatusBar/.
set -e
ROOT="${0:a:h:h}"
APP_SUPPORT="$HOME/Library/Application Support/AIStatusBar"
VENV="$APP_SUPPORT/venv"
LABEL="com.yeojeonghun.ai-status-bar"

# Python 3.11+ — /usr/bin/python3(3.9) 은 피한다. Homebrew python3 우선.
PY=""
for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$cand"; break; fi
    fi
done
if [[ -z "$PY" ]]; then
    echo "Python 3.11+ 가 필요합니다 (brew install python)." >&2; exit 1
fi
echo "python: $PY ($("$PY" --version))"

mkdir -p "$APP_SUPPORT" "$HOME/Library/Logs/AIStatusBar"
if [[ ! -x "$VENV/bin/python" ]]; then
    "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements-mac.txt"
"$VENV/bin/python" -c 'import rumps, AppKit, PIL' || { echo "패키지 설치 실패" >&2; exit 1; }

if [[ "$1" == "--no-autostart" ]]; then
    "$VENV/bin/python" "$ROOT/ai_status_bar_mac.py" --no-autostart 2>/dev/null || true
    nohup "$VENV/bin/python" "$ROOT/ai_status_bar_mac.py" >>"$HOME/Library/Logs/AIStatusBar/launchd.log" 2>&1 &
    echo "started (no autostart): pid $!"
else
    # 이미 launchd 에 올라가 있으면 내렸다가 새 plist 로 다시 올린다 (경로가 바뀌었을 수 있다)
    /bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    "$VENV/bin/python" "$ROOT/ai_status_bar_mac.py" --autostart
    echo "LaunchAgent: ~/Library/LaunchAgents/$LABEL.plist (RunAtLoad) — 지금 기동했습니다"
fi
echo "설정: $APP_SUPPORT/settings.json   로그: ~/Library/Logs/AIStatusBar/error.log"
echo "제거: zsh mac/uninstall.sh"
