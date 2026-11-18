#Requires -Version 7.0
<#
.SYNOPSIS
  Builds the ChumpEditor MSI installer.

.DESCRIPTION
  Packages the PyInstaller one-file exes (dist\ChumpEditor.exe and
  dist\ChumpEditorCli.exe) into a per-user MSI with WiX v5.  Build the exes
  first (python build.py --only exe).  Requires the WiX command-line tool:

    dotnet tool install --global wix
    wix extension add -g WixToolset.UI.wixext

.PARAMETER Version
  Override the version baked into the MSI.  Default: the version from
  pyproject.toml.
#>
param(
    [string]$Version
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$distDir = Join-Path $root 'dist'

if (-not $Version) {
    $match = Select-String -Path (Join-Path $root 'pyproject.toml') -Pattern '^version = "([^"]+)"' | Select-Object -First 1
    if (-not $match) { throw 'Could not read the version from pyproject.toml.' }
    $Version = $match.Matches[0].Groups[1].Value
}

# The MSI uses the same two-part Major.Minor version as the app artifacts
# (dist\ChumpEditor-1.0-windows.zip -> ChumpEditor-1.0.msi); a leading 'v'
# (release tags) is accepted and dropped.  MSI treats "1.0" and "1.0.0" as the
# same ProductVersion, so upgrades across the two spellings still work.
$parts = @(($Version.TrimStart('v') -split '\.') | Where-Object { $_ -match '^\d+$' })
if ($parts.Count -eq 0) { throw "Version '$Version' contains no numeric segments." }
$Version = ($parts[0..([Math]::Min(1, $parts.Count - 1))] -join '.')

foreach ($exe in 'ChumpEditor.exe', 'ChumpEditorCli.exe') {
    $path = Join-Path $distDir $exe
    if (-not (Test-Path $path)) {
        throw "$exe not found in $distDir. Build it first: python build.py --only exe"
    }
    # Don't ship an MSI whose version disagrees with the binaries inside it.
    # Compare the numeric prefix only: PyInstaller writes the full project
    # version (e.g. 1.0.0) while the MSI version is Major.Minor (1.0).
    $fileVersion = (Get-Item $path).VersionInfo.FileVersion
    $fileParts = @(($fileVersion -split '\.') | Where-Object { $_ -match '^\d+$' })
    $msiParts = @($Version -split '\.')
    if (-not $fileParts -or ($fileParts[0..([Math]::Min($fileParts.Count, $msiParts.Count) - 1)] -join '.') -ne ($msiParts[0..([Math]::Min($fileParts.Count, $msiParts.Count) - 1)] -join '.')) {
        throw "$exe is version $fileVersion, but the MSI version is $Version. Rebuild: python build.py --only exe"
    }
}

Write-Host "Building ChumpEditor-$Version.msi (MSI version $Version)"
Push-Location $root
try {
    wix build installer\Product.wxs `
        -arch x64 `
        -ext WixToolset.UI.wixext `
        -d "Version=$Version" `
        -d "DistDir=$distDir" `
        -d "AssetsDir=$(Join-Path $root 'assets')" `
        -o (Join-Path $distDir "ChumpEditor-$Version.msi")
    if ($LASTEXITCODE -ne 0) { throw "wix build failed ($LASTEXITCODE)" }
}
finally {
    Pop-Location
}

$msi = Join-Path $distDir "ChumpEditor-$Version.msi"
Write-Host "`nDone: $msi  ($([math]::Round((Get-Item $msi).Length / 1KB, 1)) KB)"
