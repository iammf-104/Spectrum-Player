# Interactive Python selector - saves choice to .python_path
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cfg  = Join-Path $Root '.python_path'

function Add-Entry($list, $path, $label) {
    if (-not $path) { return $list }
    $path = $path.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $path)) { return $list }
    $key = (Resolve-Path -LiteralPath $path).Path.ToLower()
    if ($list.ContainsKey($key)) { return $list }
    $list[$key] = $label
    return $list
}

$entries = [ordered]@{}

try {
    $pyOut = & py -0p 2>$null
    foreach ($line in $pyOut) {
        if ($line -match '^\s*(-V:[^\s]+)\s+(.+)$') {
            $tag  = $matches[1].Trim()
            $path = $matches[2].Trim()
            $entries = Add-Entry $entries $path "py launcher $tag"
        }
    }
} catch {}

try {
    $whereOut = cmd /c "where python 2>nul"
    foreach ($line in ($whereOut -split "`r?`n")) {
        if ($line.Trim()) {
            $entries = Add-Entry $entries $line.Trim() "PATH: python"
        }
    }
} catch {}

Write-Host ""
Write-Host "Select Python environment for this project"
Write-Host "============================================"
Write-Host ""

if (Test-Path -LiteralPath $Cfg) {
    $cur = (Get-Content -LiteralPath $Cfg -Raw).Trim()
    Write-Host "Current saved: $cur"
    Write-Host ""
}

Write-Host "0) Auto-detect (delete saved choice, use py -3 or PATH python)"
Write-Host ""

$i = 1
$keys = @()
foreach ($kv in $entries.GetEnumerator()) {
    Write-Host "$i) $($kv.Value)"
    Write-Host "   $($kv.Key)"
    $keys += $kv.Key
    $i++
}

if ($keys.Count -eq 0) {
    Write-Host "No Python found. Install from https://www.python.org/downloads/"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
$choice = Read-Host "Enter number (0-$($keys.Count))"

if ($choice -eq '0') {
    if (Test-Path -LiteralPath $Cfg) { Remove-Item -LiteralPath $Cfg -Force }
    Write-Host "Saved: auto-detect (py -3 / PATH python)"
    Read-Host "Press Enter"
    exit 0
}

$idx = 0
try { $idx = [int]$choice } catch { $idx = -1 }
if ($idx -lt 1 -or $idx -gt $keys.Count) {
    Write-Host "Invalid choice."
    Read-Host "Press Enter"
    exit 1
}

$selected = $keys[$idx - 1]
Set-Content -LiteralPath $Cfg -Value $selected -Encoding ASCII -NoNewline
Write-Host ""
Write-Host "Saved: $selected"
& $selected --version
Read-Host "Press Enter"
