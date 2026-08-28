#!/bin/zsh
# AI Status Bar (macOS) 제거 — 순서: 상태줄 연결 해제(공식 모드) → LaunchAgent 해제(앱 종료) → 남은 폴더 안내.
ROOT="${0:a:h:h}"
APP_SUPPORT="$HOME/Library/Application Support/AIStatusBar"
VENV="$APP_SUPPORT/venv"
LABEL="com.yeojeonghun.ai-status-bar"
PY="$VENV/bin/python"; [[ -x "$PY" ]] || PY="$(command -v python3)"

echo "1) Claude Code 상태줄 연결 해제 (공식 모드를 썼다면)"
"$PY" "$ROOT/ai_status_bar_mac.py" --unlink-statusline || true
echo "2) LaunchAgent 해제 + 앱 종료"
"$PY" "$ROOT/ai_status_bar_mac.py" --no-autostart || /bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
# launchd 밖에서 띄운 인스턴스가 있으면 이 앱의 진입 스크립트를 든 프로세스만 정확히 골라 종료한다
for pid in $(/usr/bin/pgrep -f "$ROOT/ai_status_bar_mac.py"); do kill "$pid" 2>/dev/null || true; done
echo "3) 남은 것 — 필요 없으면 직접 지우세요:"
echo "   $APP_SUPPORT   (settings.json · venv · official/)"
echo "   $HOME/Library/Logs/AIStatusBar   (error.log · launchd.log)"
echo "   $ROOT   (이 저장소 폴더)"
