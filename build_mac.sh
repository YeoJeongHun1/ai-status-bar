#!/bin/zsh
# .app 번들 빌드 (py2app) → dist/AI Status Bar.app + AIStatusBar-<버전>-macos.zip + .sha256  (Windows 의 build.cmd 와 같은 규약)
# 필요: mac/install.sh 가 만든 venv (~/Library/Application Support/AIStatusBar/venv) 또는 PYTHON 환경변수의 파이썬 + py2app.
set -e
ROOT="${0:a:h}"
cd "$ROOT"
PY="${PYTHON:-$HOME/Library/Application Support/AIStatusBar/venv/bin/python}"
[[ -x "$PY" ]] || { echo "venv 파이썬이 없습니다: $PY (먼저 zsh mac/install.sh --no-autostart)" >&2; exit 1; }
"$PY" -c 'import py2app' 2>/dev/null || "$PY" -m pip install --quiet py2app
VER="$("$PY" -c 'import version; print(version.__version__)')"
# 아이콘: app.ico(Windows) → .icns
"$PY" - <<'PYEOF'
from PIL import Image
im = Image.open("app.ico")
sizes = sorted({s for s in im.ico.sizes()}, reverse=True) if hasattr(im, "ico") else [im.size]
im = Image.open("app.ico"); im.size = max(sizes); im = im.convert("RGBA")
big = im.resize((512, 512), Image.LANCZOS)
big.save("mac/AIStatusBar.icns", format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
print("icns from app.ico", im.size)
PYEOF
rm -rf build dist
"$PY" setup_mac.py py2app 2>&1 | tail -3
APP="dist/AI Status Bar.app"
[[ -d "$APP" ]] || { echo "빌드 실패" >&2; exit 1; }
# 번들 안에서 statusline_export.sh 가 실행 가능해야 한다
chmod +x "$APP/Contents/Resources/statusline_export.sh" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null && echo "ad-hoc signed" || echo "codesign(ad-hoc) 생략"
ZIP="AIStatusBar-$VER-macos.zip"
( cd dist && rm -f "$ZIP" && /usr/bin/ditto -c -k --keepParent "AI Status Bar.app" "$ZIP" )
( cd dist && /usr/bin/shasum -a 256 "$ZIP" > "$ZIP.sha256" && cat "$ZIP.sha256" )
du -sh "$APP" "dist/$ZIP"
