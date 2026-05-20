# Sync alirezarezvani/claude-skills into .cursor/skills/ (Cursor Agent Skills format).
# Usage:
#   .\scripts\sync-cursor-skills.ps1
#   .\scripts\sync-cursor-skills.ps1 -Source C:\path\to\claude-skills
#   .\scripts\sync-cursor-skills.ps1 -Global   # install to %USERPROFILE%\.cursor\skills

param(
    [string]$Source = "",
    [switch]$Global,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DefaultSource = Join-Path $env:TEMP "claude-skills"

if (-not $Source) { $Source = $DefaultSource }

if (-not (Test-Path $Source)) {
    Write-Host "Cloning claude-skills to $DefaultSource ..."
    git clone --depth 1 https://github.com/alirezarezvani/claude-skills.git $DefaultSource 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Checkout may be partial (one file permission issue is OK on Windows)."
    }
}

$DestRoot = if ($Global) {
    Join-Path $env:USERPROFILE ".cursor\skills"
} else {
    Join-Path $ProjectRoot ".cursor\skills"
}

New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null

# Remove monolithic copy from agent-skills-cli if present
$Monolith = Join-Path $DestRoot "claude-skills"
if (Test-Path $Monolith) {
    Remove-Item -Recurse -Force $Monolith
}

function Get-SkillSlug {
    param([string]$SkillDir, [string]$RepoRoot)
    $rel = $SkillDir.Substring($RepoRoot.Length).TrimStart("\", "/")
    $slug = ($rel -replace "[\\/]", "-").ToLower()
    $slug = $slug -replace "[^a-z0-9\-]", "-"
    $slug = $slug -replace "-+", "-"
    $slug.Trim("-")
}

$skillFiles = Get-ChildItem -Path $Source -Recurse -Filter "SKILL.md" -File -ErrorAction SilentlyContinue
if (-not $skillFiles) {
    throw "No SKILL.md found under $Source"
}

$seen = @{}
$installed = 0
$skipped = 0

foreach ($f in $skillFiles) {
    $skillDir = $f.Directory.FullName
    $slug = Get-SkillSlug -SkillDir $skillDir -RepoRoot $Source
    if (-not $slug) { $slug = "skill-$installed" }

    if ($seen.ContainsKey($slug)) {
        $slug = "$slug-$($seen[$slug])"
        $seen[$slug]++
    } else {
        $seen[$slug] = 1
    }

    $dest = Join-Path $DestRoot $slug
    if ((Test-Path $dest) -and -not $Force) {
        $skipped++
        continue
    }
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Path $skillDir -Destination $dest -Recurse -Force
    $installed++
}

Write-Host "Source:  $Source"
Write-Host "Target:  $DestRoot"
Write-Host "Installed: $installed  Skipped (exists): $skipped  Total SKILL.md: $($skillFiles.Count)"
