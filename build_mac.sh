#!/bin/zsh
# .app 번들 빌드 (py2app) → dist/AI Status Bar.app + AIStatusBar-<버전>-macos-<arch>.zip + .sha256  (Windows 의 build.cmd 와 같은 규약)
# 필요: mac/install.sh 가 만든 venv (~/Library/Application Support/AIStatusBar/venv) 또는 PYTHON 환경변수의 파이썬 + py2app.
# 만든 번들은 **빌드한 파이썬의 최소 macOS·아키텍처**를 그대로 따른다 (Homebrew python 3.14 = arm64 · macOS 26+) — Info.plist 에 그 값을 적는다.
set -eu
ROOT="${0:a:h}"
cd "$ROOT"
PY="${PYTHON:-$HOME/Library/Application Support/AIStatusBar/venv/bin/python}"
[[ -x "$PY" ]] || { echo "venv 파이썬이 없습니다: $PY (먼저 zsh mac/install.sh --source --no-autostart)" >&2; exit 1; }
"$PY" -c 'import py2app' 2>/dev/null || "$PY" -m pip install --quiet "py2app==0.28.10"
VER="$("$PY" -c 'import version; print(version.__version__)')"
ARCH="$(uname -m)"
# 아이콘: app.ico(Windows) → .icns (빌드 산출물 — git 에 넣지 않는다)
"$PY" - <<'PYEOF'
from PIL import Image
im = Image.open("app.ico")
sizes = sorted(im.ico.sizes(), reverse=True) if hasattr(im, "ico") else [im.size]
im.size = max(sizes)
im = im.convert("RGBA").resize((512, 512), Image.LANCZOS)
im.save("mac/AIStatusBar.icns", format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
PYEOF
rm -rf build dist
"$PY" setup_mac.py py2app 2>&1 | tail -3
APP="dist/AI Status Bar.app"
[[ -d "$APP" ]] || { echo "빌드 실패" >&2; exit 1; }
chmod +x "$APP/Contents/Resources/statusline_export.sh" 2>/dev/null || true
# --- 배포물에서 빌드 머신의 경로를 지운다 (서명 전) ---
# 1) Info.plist 의 PythonInfoDict(빌드 파이썬 절대경로) 제거
/usr/bin/plutil -remove PythonInfoDict "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
# 2) .pyc 안의 co_filename(소스 절대경로) → 홈·저장소·venv 를 중립 이름으로
"$PY" - "$APP" <<'PYEOF'
import marshal, os, sys, types
app = sys.argv[1]
home = os.path.expanduser("~")
site = os.path.dirname(os.path.dirname(os.__file__))            # …/venv/lib 또는 framework lib
repo = os.getcwd()
subs = [(repo, "<app>"), (home, "~")]
def fix(code):
    fn = code.co_filename
    for old, new in subs:
        if fn.startswith(old):
            fn = new + fn[len(old):]
            break
    consts = tuple(fix(c) if isinstance(c, types.CodeType) else c for c in code.co_consts)
    return code.replace(co_filename=fn, co_consts=consts)
n = 0
for d, _, files in os.walk(app):
    for f in files:
        if not f.endswith(".pyc"):
            continue
        p = os.path.join(d, f)
        with open(p, "rb") as fh:
            head, body = fh.read(16), fh.read()
        try:
            code = marshal.loads(body)
        except Exception:
            continue
        if not isinstance(code, types.CodeType):
            continue
        with open(p, "wb") as fh:
            fh.write(head + marshal.dumps(fix(code)))
        n += 1
print(f"pyc co_filename neutralized: {n}")
PYEOF
LEFT="$(grep -rl "$HOME" "$APP" 2>/dev/null | wc -l | tr -d ' ')"
echo "files still containing $HOME: $LEFT"
# --- 서명 (ad-hoc) ---
codesign --force --deep --sign - "$APP" 2>/dev/null && echo "ad-hoc signed" || echo "codesign(ad-hoc) 생략"
codesign --verify --deep --strict "$APP" && echo "codesign verify: ok"
MINOS="$(/usr/bin/plutil -extract LSMinimumSystemVersion raw "$APP/Contents/Info.plist")"
echo "LSMinimumSystemVersion=$MINOS arch=$ARCH version=$VER"
# --- zip: --norsrc 로 리소스 포크·xattr(AppleDouble ._*·__MACOSX) 를 아예 넣지 않는다 — 들어가면 unzip 으로 풀 때 서명이 깨질 수 있다 ---
ZIP="AIStatusBar-$VER-macos-$ARCH.zip"
( cd dist && rm -f "$ZIP" && /usr/bin/ditto -c -k --norsrc --keepParent "AI Status Bar.app" "$ZIP" )
( cd dist && /usr/bin/shasum -a 256 "$ZIP" > "$ZIP.sha256" && cat "$ZIP.sha256" )
# --- 실측: unzip 으로 풀어도 서명이 유효한가 ---
TMPD="$(mktemp -d)"
( cd "$TMPD" && /usr/bin/unzip -q "$ROOT/dist/$ZIP" && echo "AppleDouble files after unzip: $(find . -name '._*' | wc -l | tr -d ' ')" && codesign --verify --deep --strict "AI Status Bar.app" && echo "unzip → codesign verify: ok" )
rm -rf "$TMPD"
du -sh "$APP" "dist/$ZIP"
