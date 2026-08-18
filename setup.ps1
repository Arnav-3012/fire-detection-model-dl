# FireWatch environment setup (Windows).
# Creates a Python 3.11 venv and installs requirements.txt.
$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$pythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py" }
$pythonArgs = if ($pythonBin -eq "py") { @("-3.11") } else { @() }

$versionCheck = & $pythonBin @pythonArgs -c "import sys; print(sys.version_info[:2])" 2>$null
if (-not $versionCheck -or -not ($versionCheck -match "\(3, 1[01]\)")) {
    Write-Error "Python 3.11 not found. Install Python 3.10 or 3.11 (plan.md section 4.1 -- not 3.12)."
    exit 1
}

& $pythonBin @pythonArgs -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete. Activate with: .\.venv\Scripts\Activate.ps1"
Write-Host "Then verify with: python scripts\verify_env.py"
