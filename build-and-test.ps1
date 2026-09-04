# Build va test thu cong cho repo Claude-Agents (PowerShell)
# Chay tung khoi rieng: build/test luon chay; gateway + demo that la tuy chon.
#
# Cach chay:
#   powershell -ExecutionPolicy Bypass -File build-and-test.ps1
#   hoac trong PowerShell da mo san:  .\build-and-test.ps1
#
# Tham so tuy chon:
#   -Real       chay them demo voi provider that (Claude Code CLI + Antigravity gateway)
#   -SkipTests  bo qua pytest (chi build + lint)

param(
    [switch]$Real,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Step($title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

# ---------- 1. Dong bo workspace ----------
Step "uv sync (workspace goc)"
Set-Location $root
uv sync

# ---------- 2. Test tung package rieng (tranh dung ten module trung) ----------
if (-not $SkipTests) {
    foreach ($pkg in @("software-company", "Studio-creators", "gateway", "console")) {
        Step "pytest: $pkg"
        Set-Location (Join-Path $root $pkg)
        uv run pytest -q
    }
}

# ---------- 3. Lint + type-check cho software-company ----------
Step "ruff + mypy: software-company"
Set-Location (Join-Path $root "software-company")
uv run ruff check src tests
uv run mypy src/company --ignore-missing-imports

if ($Real) {
    # ---------- 4. Bat gateway (Antigravity) ----------
    Step "gateway start"
    Set-Location (Join-Path $root "gateway")
    uv run python -m gateway start
    uv run python -m gateway status

    # ---------- 5. Probe CLI claude ----------
    Step "probe CLI claude"
    Set-Location (Join-Path $root "software-company")
    uv run python -m company.probe

    # ---------- 6. Demo voi provider that ----------
    Step "demo --real"
    $env:PYTHONPATH = "src"
    uv run python examples/donghanhcungban_demo.py --real --out real-demo
    Remove-Item Env:\PYTHONPATH

    Write-Host ""
    Write-Host "Neu du an ket (gate escalation), quyet dinh bang:" -ForegroundColor Yellow
    Write-Host "  uv run python -m company.gate_cli approve <project_id> --by human:lead --db real-demo/company.sqlite"
    Write-Host "  (hoac 'reject' thay 'approve')"
}

Set-Location $root
Write-Host ""
Write-Host "Xong." -ForegroundColor Green
