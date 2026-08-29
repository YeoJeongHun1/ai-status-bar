#!/bin/zsh
# AI Status Bar (macOS) 설치.
#   zsh mac/install.sh                 번들(dist/AI Status Bar.app 이 있으면) 또는 소스(venv) 로 설치 → LaunchAgent 등록 → 즉시 기동
#   zsh mac/install.sh --no-autostart  LaunchAgent 없이 지금 한 번만 띄움
#   zsh mac/install.sh --source        번들이 있어도 소스(venv) 로 설치
#   zsh mac/install.sh --build         venv 를 만든 뒤 build_mac.sh 로 번들을 만들어 그것으로 설치
# 만드는 것(전부 홈 아래, sudo 없음): ~/Library/Application Support/AIStatusBar/{venv,settings.json},
#   ~/Applications/AI Status Bar.app (번들 설치 때), ~/Library/LaunchAgents/com.yeojeonghun.ai-status-bar.plist, ~/Library/Logs/AIStatusBar/.
set -eu
ROOT="${0:a:h:h}"
APP_SUPPORT="$HOME/Library/Application Support/AIStatusBar"
VENV="$APP_SUPPORT/venv"
LABEL="com.yeojeonghun.ai-status-bar"
BUNDLE_SRC="$ROOT/dist/AI Status Bar.app"
BUNDLE_DST="$HOME/Applications/AI Status Bar.app"
LOGS="$HOME/Library/Logs/AIStatusBar"
MODE="auto"; AUTOSTART=1
for a in "$@"; do
    case "$a" in
        --no-autostart) AUTOSTART=0 ;;
        --source) MODE="source" ;;
        --build) MODE="build" ;;
    esac
done

# Python 3.11+ — /usr/bin/python3(3.9) 은 피한다. Homebrew python3 우선.
PY=""
for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$cand"; break; fi
    fi
done
if [[ -z "$PY" && "$MODE" != "auto" || -z "$PY" && ! -d "$BUNDLE_SRC" ]]; then
    echo "Python 3.11+ 가 필요합니다 (brew install python)." >&2; exit 1
fi
mkdir -p "$APP_SUPPORT" "$LOGS"

make_venv() {
    echo "python: $PY ($("$PY" --version))"
    [[ -x "$VENV/bin/python" ]] || "$PY" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet "pip>=25"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements-mac.txt"
    "$VENV/bin/python" -c 'import rumps, AppKit, PIL' || { echo "패키지 설치 실패" >&2; exit 1; }
}

if [[ "$MODE" == "build" ]]; then
    make_venv
    zsh "$ROOT/build_mac.sh"
    MODE="bundle"
elif [[ "$MODE" == "auto" ]]; then
    if [[ -d "$BUNDLE_SRC" ]]; then MODE="bundle"; else MODE="source"; make_venv; fi
elif [[ "$MODE" == "source" ]]; then
    make_venv
fi

# 실행 중이면(launchd 또는 수동) 내린다 — 우리 LaunchAgent 와 우리 진입 스크립트/번들만 정확히
/bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
for pid in $(/usr/bin/pgrep -f "$ROOT/ai_status_bar_mac.py" 2>/dev/null) $(/usr/bin/pgrep -f "$BUNDLE_DST/Contents/MacOS/" 2>/dev/null); do kill "$pid" 2>/dev/null || true; done
sleep 1

if [[ "$MODE" == "bundle" ]]; then
    mkdir -p "$HOME/Applications"
    rm -rf "$BUNDLE_DST"
    /usr/bin/ditto "$BUNDLE_SRC" "$BUNDLE_DST"
    EXE="$BUNDLE_DST/Contents/MacOS/AI Status Bar"
    echo "설치: $BUNDLE_DST"
    RUN=("$EXE")
else
    # 소스로 쓸 때는 공식 모드 스크립트가 venv 파이썬을 쓴다 (statusline_export.sh 참고)
    RUN=("$VENV/bin/python" "$ROOT/ai_status_bar_mac.py")
fi

if [[ $AUTOSTART -eq 0 ]]; then
    "${RUN[@]}" --no-autostart 2>/dev/null || true
    nohup "${RUN[@]}" >>"$LOGS/launchd.log" 2>&1 &
    echo "started (no autostart): pid $!"
else
    "${RUN[@]}" --autostart
    echo "LaunchAgent: ~/Library/LaunchAgents/$LABEL.plist (RunAtLoad) — 지금 기동했습니다"
fi
echo "설정: $APP_SUPPORT/settings.json   로그: $LOGS/error.log   설정 창: 메뉴 막대 클릭 → 설정… (또는 --setup)"
echo "제거: zsh mac/uninstall.sh"
