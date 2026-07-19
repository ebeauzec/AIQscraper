#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Bump the app version and optionally commit changes.

.DESCRIPTION
    Follows Semantic Versioning (semver.org):
      MAJOR  – breaking changes or major architectural reworks
      MINOR  – new features, backward-compatible
      PATCH  – bug fixes, minor tweaks, performance improvements

    Reads from / writes to: version.json (source of truth)
    Also updates:           app.js (APP_VERSION constant)
    Also prepends to:       CHANGELOG.md

.PARAMETER Type
    One of: major | minor | patch   (default: patch)

.PARAMETER Message
    One-line description of the change for CHANGELOG.md.
    If omitted, prompts interactively.

.PARAMETER NoCommit
    If set, only updates files — does NOT run git add/commit.

.PARAMETER NoChangelog
    If set, skips prepending the CHANGELOG.md entry.

.EXAMPLE
    # Bug fix:
    .\bump_version.ps1 patch "Fix TAM tab browser hang on large fleets"

    # New feature:
    .\bump_version.ps1 minor "Add What's New startup modal"

    # Breaking release:
    .\bump_version.ps1 major "Rename to ARIA, overhaul API layer"
#>

param(
    [ValidateSet("major", "minor", "patch")]
    [string]$Type = "patch",

    [string]$Message = "",

    [switch]$NoCommit,
    [switch]$NoChangelog
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

# ── 1. Read current version ───────────────────────────────────────────────────
$vFile = Join-Path $Root "version.json"
$v     = Get-Content $vFile -Raw | ConvertFrom-Json

$major = [int]$v.major
$minor = [int]$v.minor
$patch = [int]$v.patch

Write-Host "`nCurrent version: $major.$minor.$patch" -ForegroundColor Cyan

# ── 2. Bump ───────────────────────────────────────────────────────────────────
switch ($Type) {
    "major" { $major++; $minor = 0; $patch = 0 }
    "minor" { $minor++;             $patch = 0 }
    "patch" {                       $patch++   }
}

$newVersion = "$major.$minor.$patch"
$today      = Get-Date -Format "yyyy-MM-dd"
Write-Host "New version:     $newVersion  ($Type bump)" -ForegroundColor Green

# ── 3. Prompt for message if not provided ─────────────────────────────────────
if (-not $Message) {
    $Message = Read-Host "Describe this change (one line, for CHANGELOG)"
}
if (-not $Message) { $Message = "$Type bump to $newVersion" }

# ── 4. Update version.json ───────────────────────────────────────────────────
$newV = [ordered]@{
    version = $newVersion
    major   = $major
    minor   = $minor
    patch   = $patch
    date    = $today
    notes   = $Message
}
$newV | ConvertTo-Json -Depth 2 | Set-Content $vFile -Encoding UTF8
Write-Host "  Updated: version.json" -ForegroundColor Gray

# ── 5. Update APP_VERSION in app.js ──────────────────────────────────────────
$appJs = Join-Path $Root "app.js"
$jsContent = [System.IO.File]::ReadAllText($appJs, [System.Text.Encoding]::UTF8)

# Replace the old APP_VERSION string (handles both date-style and semver-style)
$jsContent = $jsContent -replace 'const APP_VERSION\s*=\s*"[^"]*";', "const APP_VERSION = `"$newVersion`";"

# Also update the matching version in the top APP_CHANGELOG entry if it matches the old version
$oldVersion = "$($v.major).$($v.minor).$($v.patch)"
$jsContent = $jsContent -replace "version:\s*`"$([regex]::Escape($v.version))`"", "version: `"$newVersion`""

[System.IO.File]::WriteAllText($appJs, $jsContent, [System.Text.Encoding]::UTF8)
Write-Host "  Updated: app.js  (APP_VERSION = `"$newVersion`")" -ForegroundColor Gray

# ── 6. Prepend to CHANGELOG.md ───────────────────────────────────────────────
if (-not $NoChangelog) {
    $clFile = Join-Path $Root "CHANGELOG.md"
    $existing = [System.IO.File]::ReadAllText($clFile, [System.Text.Encoding]::UTF8)

    # Determine bump type label
    $changeType = switch ($Type) {
        "major" { "### Changed (Breaking)" }
        "minor" { "### Added"              }
        "patch" { "### Fixed"              }
    }

    $newEntry = @"
## [$newVersion] - $today

$changeType
- $Message

---

"@

    # Insert after the intro ---  but BEFORE the first ## [version] entry
    # Supports both CRLF and LF
    $marker1 = "---`r`n`r`n## ["
    $marker2 = "---`n`n## ["
    $insertIdx = $existing.IndexOf($marker1)
    if ($insertIdx -ge 0) {
        $splitAt    = $insertIdx + "---`r`n`r`n".Length
    } elseif (($insertIdx = $existing.IndexOf($marker2)) -ge 0) {
        $splitAt    = $insertIdx + "---`n`n".Length
    } else {
        $splitAt    = -1
    }
    if ($splitAt -ge 0) {
        $newContent = $existing.Substring(0, $splitAt) + $newEntry + $existing.Substring($splitAt)
    } else {
        $newContent = $existing + "`r`n`r`n" + $newEntry
    }

    [System.IO.File]::WriteAllText($clFile, $newContent, [System.Text.Encoding]::UTF8)
    Write-Host "  Updated: CHANGELOG.md" -ForegroundColor Gray
}

# ── 7. Git commit ─────────────────────────────────────────────────────────────
if (-not $NoCommit) {
    Write-Host "`nStaging and committing..." -ForegroundColor Cyan
    git -C $Root add version.json app.js CHANGELOG.md
    git -C $Root commit -m "chore: bump version to $newVersion — $Message"
    git -C $Root tag "v$newVersion" -m "Version $newVersion"
    Write-Host "  Committed and tagged: v$newVersion" -ForegroundColor Green
}

Write-Host "`nDone. Version is now $newVersion`n" -ForegroundColor Green
