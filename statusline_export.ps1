# AI Status Bar - official-mode exporter for Claude Code (registered as the Claude Code statusLine command)
#
# Reads the status-line JSON that Claude Code passes on stdin and saves it, unchanged, to
#   %LOCALAPPDATA%\AIStatusBar\official\<key>.json
# then pipes the same JSON to the user's original status-line command (kept by the app in
# <key>.original.json) and prints its output as-is; if there was none, prints one line
# "model | 5h xx% | 7d xx%". No network access.
#
# key = first 12 hex chars of SHA-1(UTF-8) of the config-folder path after
#       GetFullPath -> trim trailing separators -> lower-case
#       (must match official_key() in providers/claude_code.py)
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

$outDir = Join-Path $env:LOCALAPPDATA "AIStatusBar\official"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$wrapper = '{"config_dir":' + ($dir | ConvertTo-Json) + ',"saved_at":' + $epoch + ',"statusline":' + $raw.Trim() + '}'
$tmp = Join-Path $outDir ($key + ".json.tmp")
$dst = Join-Path $outDir ($key + ".json")
[IO.File]::WriteAllText($tmp, $wrapper, (New-Object Text.UTF8Encoding $false))
Move-Item -Force $tmp $dst

# Original status-line command, if the app kept one: pass the JSON through and print its output.
$origFile = Join-Path $outDir ($key + ".original.json")
if (Test-Path $origFile) {
    $orig = (Get-Content $origFile -Raw | ConvertFrom-Json).original_statusLine
    if ($orig -and $orig.command) {
        $raw | cmd.exe /d /s /c "$($orig.command)"
        exit 0
    }
}

# Otherwise a minimal line.
$j = $raw | ConvertFrom-Json
$model = $j.model.display_name
$parts = @()
if ($model) { $parts += $model }
if ($j.rate_limits.five_hour.used_percentage -ne $null) { $parts += ("5h " + [math]::Round($j.rate_limits.five_hour.used_percentage) + "%") }
if ($j.rate_limits.seven_day.used_percentage -ne $null) { $parts += ("7d " + [math]::Round($j.rate_limits.seven_day.used_percentage) + "%") }
Write-Output ($parts -join " | ")
