param(
    [string]$Branch = "main",
    [string]$Remote = "origin"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -Path $ProjectRoot

# Stage everything except ignored files.
git add -A

# Exit if there is nothing staged.
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    exit 0
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "autosync: $timestamp"
if ($LASTEXITCODE -ne 0) {
    exit 1
}

# Rebase to avoid accidental merge commits in automation.
git pull --rebase $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    exit 1
}

git push $Remote $Branch
exit $LASTEXITCODE
