#!/bin/zsh
# AI Status Bar - official-mode exporter for Claude Code on macOS (registered as the Claude Code statusLine command)
#
# Claude Code runs this script (via  /bin/zsh "<repo>/statusline_export.sh")  every time it draws the status line and
# passes the status-line JSON on stdin. This script:
#   1. keeps ONLY  model.display_name  and  rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}
#      (cwd, transcript_path, session_id, workspace, cost ... are NOT saved), adds saved_at (UTC epoch) and writes
#        ~/Library/Application Support/AIStatusBar/official/<key>.json
#      via a per-process temp file (<key>.<pid>.tmp) so several Claude Code sessions do not clobber each other;
#   2. if the app kept your original statusLine command in <key>.original.json, runs it with the same JSON on stdin
#      and prints its output unchanged. The command string is handed to /bin/sh as ONE argument (this script never
#      interpolates its contents — same rule as statusline_export.ps1 on Windows);
#   3. otherwise prints one line:  "model | 5h xx% | 7d xx%".
# No network access. Nothing else is read or written.
#
# key = first 12 hex chars of SHA-1(UTF-8) of the config-folder path after abspath -> trim trailing "/"
#       (must match official_key() in providers/claude_code.py; os.path.normcase is a no-op on macOS)
# JSON is handled by a python interpreter, tried in this order: the app bundle's own  Contents/MacOS/python  (when this
# script runs from inside  AI Status Bar.app/Contents/Resources  — no Python installation needed), the app's venv python
# (source install, mac/install.sh), then any python3 on PATH. With none of them nothing is saved and nothing is printed.
emulate -L zsh
raw="$(cat)"
[[ -z "$raw" ]] && exit 0

dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
norm="${dir:a}"
while [[ "$norm" == */ && "$norm" != "/" ]]; do norm="${norm%/}"; done
key="$(printf '%s' "$norm" | /usr/bin/shasum -a 1 | /usr/bin/cut -c1-12)"

out_dir="$HOME/Library/Application Support/AIStatusBar/official"
here="${0:a:h}"
py=""
for cand in "$here/../MacOS/python" "$HOME/Library/Application Support/AIStatusBar/venv/bin/python" "$(command -v python3 2>/dev/null)"; do
    [[ -n "$cand" && -x "$cand" ]] && { py="$cand"; break; }
done
[[ -n "$py" ]] || exit 0

# --- 1. save only what the app displays (exit 3 = an original command is kept -> step 2) ---
export ASB_RAW="$raw"
"$py" - "$out_dir" "$key" <<'PY'
import json, os, sys, time
out_dir, key = sys.argv[1], sys.argv[2]
try:
    j = json.loads(os.environ.get("ASB_RAW") or "")
except Exception:
    j = {}
model = ((j.get("model") or {}).get("display_name")) if isinstance(j, dict) else None
rl = {}
for w in ("five_hour", "seven_day"):
    src = ((j.get("rate_limits") or {}).get(w)) if isinstance(j, dict) else None
    if isinstance(src, dict):
        rl[w] = {"used_percentage": src.get("used_percentage"), "resets_at": src.get("resets_at")}
os.makedirs(out_dir, exist_ok=True)
tmp = os.path.join(out_dir, f"{key}.{os.getpid()}.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"saved_at": int(time.time()), "model": model, "rate_limits": rl}, f, separators=(",", ":"))
os.replace(tmp, os.path.join(out_dir, key + ".json"))
if os.path.isfile(os.path.join(out_dir, key + ".original.json")):
    sys.exit(3)
parts = [model] if model else []
for w, name in (("five_hour", "5h"), ("seven_day", "7d")):
    v = (rl.get(w) or {}).get("used_percentage")
    if v is not None:
        parts.append(f"{name} {round(float(v))}%")
print(" | ".join(parts))
PY
rc=$?
unset ASB_RAW
[[ $rc -ne 3 ]] && exit 0

# --- 2. original status-line command, if the app kept one ---
cmd="$("$py" -c 'import json,sys
try:
    o=(json.load(open(sys.argv[1])).get("original_statusLine") or {}).get("command") or ""
except Exception:
    o=""
sys.stdout.write(str(o))' "$out_dir/$key.original.json")"
if [[ -n "$cmd" ]]; then
    # /bin/sh -c takes the command as a single argument variable; nothing is spliced into this script's own text.
    print -rn -- "$raw" | /bin/sh -c "$cmd"
fi
exit 0
