$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = "python.exe"
if (Test-Path "$Root\.venv311\Scripts\python.exe") {
    $Python = "$Root\.venv311\Scripts\python.exe"
} elseif (Test-Path "$Root\.venv\Scripts\python.exe") {
    $Python = "$Root\.venv\Scripts\python.exe"
}

& $Python "$Root\scripts\live_demo_check.py" $args
