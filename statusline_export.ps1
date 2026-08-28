# AI Status Bar - official-mode exporter for Claude Code (registered as the Claude Code statusLine command)
#
# Claude Code runs this script (via "powershell -NoProfile -ExecutionPolicy Bypass -File ...") every time it draws
# the status line and passes the status-line JSON on stdin. This script:
#   1. keeps ONLY  model.display_name  and  rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}
#      (cwd, transcript_path, session_id, workspace, cost ... are NOT saved), adds saved_at (UTC epoch) and writes
#        %LOCALAPPDATA%\AIStatusBar\official\<key>.json
#      via a per-process temp file (<key>.<pid>.tmp) so several Claude Code sessions do not clobber each other;
#   2. if the app kept your original statusLine command in <key>.original.json, runs it with the same JSON on
#      stdin and prints its output unchanged (so your old status line keeps working). The command string is
#      handed to cmd.exe as ONE argument (no string interpolation of its contents by this script);
#   3. otherwise prints one line:  "model | 5h xx% | 7d xx%".
# No network access. Nothing else is read or written.
#
# key = first 12 hex chars of SHA-1(UTF-8) of the config-folder path after
#       GetFullPath -> trim trailing separators -> lower-case   (must match official_key() in providers/claude_code.py)
#
# NOTE: keep this file ASCII with a UTF-8 BOM - Windows PowerShell 5.1 reads BOM-less scripts as ANSI,
#       and multibyte comment bytes can swallow the following line.
$ErrorActionPreference = "SilentlyContinue"
$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }

$dir = $env:CLAUDE_CONFIG_DIR
if (-not $dir) { $dir = Join-Path $HOME ".claude" }
$norm = [IO.Path]::GetFullPath($dir).TrimEnd('\', '/').ToLowerInvariant()
$sha = [Security.Cryptography.SHA1]::Create()
$key = (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($norm)) | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 12)

$j = $null
try { $j = $raw | ConvertFrom-Json } catch { $j = $null }

# --- 1. save only what the app displays ---
$model = $null
if ($j -and $j.model) { $model = $j.model.display_name }
$rl = @{}
if ($j -and $j.rate_limits) {
    foreach ($w in @("five_hour", "seven_day")) {
        $src = $j.rate_limits.$w
        if ($src -ne $null) {
            $rl[$w] = @{ used_percentage = $src.used_percentage; resets_at = $src.resets_at }
        }
    }
}
$out = @{ saved_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); model = $model; rate_limits = $rl }
$outDir = Join-Path $env:LOCALAPPDATA "AIStatusBar\official"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$tmp = Join-Path $outDir ($key + "." + $PID + ".tmp")
$dst = Join-Path $outDir ($key + ".json")
[IO.File]::WriteAllText($tmp, ($out | ConvertTo-Json -Compress -Depth 4), (New-Object Text.UTF8Encoding $false))
Move-Item -Force $tmp $dst

# --- 2. original status-line command, if the app kept one ---
$origFile = Join-Path $outDir ($key + ".original.json")
if (Test-Path $origFile) {
    $orig = $null
    try { $orig = (Get-Content $origFile -Raw | ConvertFrom-Json).original_statusLine } catch { $orig = $null }
    if ($orig -and $orig.command) {
        $cmdLine = [string]$orig.command
        # cmd.exe is used because Claude Code itself runs statusLine commands through a shell; the string is passed
        # as a single argument variable, never spliced into this script's own command text.
        $raw | & $env:ComSpec /d /s /c $cmdLine
        exit 0
    }
}

# --- 3. minimal line ---
$parts = @()
if ($model) { $parts += $model }
if ($rl.ContainsKey("five_hour") -and $rl.five_hour.used_percentage -ne $null) { $parts += ("5h " + [math]::Round($rl.five_hour.used_percentage) + "%") }
if ($rl.ContainsKey("seven_day") -and $rl.seven_day.used_percentage -ne $null) { $parts += ("7d " + [math]::Round($rl.seven_day.used_percentage) + "%") }
Write-Output ($parts -join " | ")
