# setup.ps1 - Choose Python environment and install dependencies
param(
    [switch]$SelectOnly
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cfg  = Join-Path $Root '.python_path'

function Add-Entry($dict, $path, $label) {
    if (-not $path) { return $dict }
    $path = $path.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $path)) { return $dict }
    try {
        $key = (Resolve-Path -LiteralPath $path).Path.ToLower()
    } catch {
        return $dict
    }
    if ($dict.ContainsKey($key)) { return $dict }
    $dict[$key] = $label
    return $dict
}

function Resolve-PythonPath {
    if (Test-Path -LiteralPath $Cfg) {
        $p = (Get-Content -LiteralPath $Cfg -Raw).Trim()
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    try {
        $p = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($p) { return $p.Trim() }
    } catch {}
    $w = cmd /c "where python 2>nul" | Select-Object -First 1
    if ($w) { return $w.Trim() }
    return $null
}

function Show-SelectMenu {
    $entries = [ordered]@{}

    try {
        foreach ($line in (& py -0p 2>$null)) {
            if ($line -match '^\s*(-V:[^\s]+)\s+(.+)$') {
                $entries = Add-Entry $entries $matches[2].Trim() "py launcher $($matches[1].Trim())"
            }
        }
    } catch {}

    try {
        foreach ($line in (cmd /c "where python 2>nul") -split "`r?`n") {
            if ($line.Trim()) {
                $entries = Add-Entry $entries $line.Trim() "PATH: python"
            }
        }
    } catch {}

    Write-Host ""
    Write-Host "Python environment"
    Write-Host "===================="

    if (Test-Path -LiteralPath $Cfg) {
        Write-Host "Saved: $((Get-Content -LiteralPath $Cfg -Raw).Trim())"
        Write-Host ""
    }

    Write-Host "0) Auto-detect (delete saved, use py -3 / PATH python)"
    Write-Host ""

    $keys = @()
    $i = 1
    foreach ($kv in $entries.GetEnumerator()) {
        Write-Host "$i) $($kv.Value)"
        Write-Host "   $($kv.Key)"
        $keys += $kv.Key
        $i++
    }

    if ($keys.Count -eq 0) {
        Write-Host "[ERROR] No Python found."
        Write-Host "Install from https://www.python.org/downloads/ (check Add to PATH)"
        return $false
    }

    Write-Host ""
    $choice = Read-Host "Enter number (0-$($keys.Count))"

    if ($choice -eq '0') {
        if (Test-Path -LiteralPath $Cfg) { Remove-Item -LiteralPath $Cfg -Force }
        Write-Host "Using auto-detect."
        return $true
    }

    $idx = 0
    try { $idx = [int]$choice } catch { $idx = -1 }
    if ($idx -lt 1 -or $idx -gt $keys.Count) {
        Write-Host "Invalid choice."
        return $false
    }

    $selected = $keys[$idx - 1]
    Set-Content -LiteralPath $Cfg -Value $selected -Encoding ASCII -NoNewline
    Write-Host "Saved: $selected"
    return $true
}

Write-Host "============================================"
if ($SelectOnly) {
    Write-Host " Select Python environment"
} else {
    Write-Host " Setup: Python + dependencies"
}
Write-Host "============================================"

$skipMenu = $false
if (Test-Path -LiteralPath $Cfg) {
    $cur = (Get-Content -LiteralPath $Cfg -Raw).Trim()
    if ($cur -and (Test-Path -LiteralPath $cur)) {
        Write-Host ""
        Write-Host "Current Python: $cur"
        $ans = Read-Host "Change environment? (y/N)"
        if ($ans -notmatch '^[yY]') { $skipMenu = $true }
    }
}

if (-not $skipMenu) {
    if (-not (Show-SelectMenu)) {
        if (-not $SelectOnly) { Read-Host "Press Enter" }
        exit 1
    }
}

$python = Resolve-PythonPath
if (-not $python) {
    Write-Host "[ERROR] Python not found. Install Python or pick from the list."
    if (-not $SelectOnly) { Read-Host "Press Enter" }
    exit 1
}

Write-Host ""
Write-Host "Using: $python"
& $python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python failed to run."
    if (-not $SelectOnly) { Read-Host "Press Enter" }
    exit 1
}

if ($SelectOnly) {
    Write-Host ""
    Write-Host "Done. run.bat and build_exe.bat will use this Python."
    Read-Host "Press Enter"
    exit 0
}

Write-Host ""
Write-Host "Installing packages from requirements.txt..."
& $python -m pip install -r (Join-Path $Root 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pip install failed."
    Read-Host "Press Enter"
    exit 1
}

Write-Host ""
Write-Host "Setup complete. You can run run.bat or build_exe.bat"
Read-Host "Press Enter"
