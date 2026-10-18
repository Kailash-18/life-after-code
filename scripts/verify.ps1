$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $RepoRoot "scripts\verify.py") @args
} else {
    python (Join-Path $RepoRoot "scripts\verify.py") @args
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
