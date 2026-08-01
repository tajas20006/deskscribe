param(
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "build"))
$distRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "dist"))
$stagedClient = [IO.Path]::GetFullPath(
    (Join-Path $buildRoot "packaging\flet_client")
)

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Child
    )

    $parentPrefix = $Parent.TrimEnd(
        [IO.Path]::DirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $Child.StartsWith($parentPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build path outside expected directory: $Child"
    }
}

Assert-ChildPath -Parent $repositoryRoot -Child $buildRoot
Assert-ChildPath -Parent $repositoryRoot -Child $distRoot
Assert-ChildPath -Parent $buildRoot -Child $stagedClient

Push-Location $repositoryRoot
try {
    if (-not $SkipChecks) {
        uv run pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed."
        }
        uv run ruff check deskscribe tests main.py
        if ($LASTEXITCODE -ne 0) {
            throw "Ruff check failed."
        }
    }

    $fletClientRoot = (
        uv run python -c "import flet_desktop; print(flet_desktop.ensure_client_cached())"
    ).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Flet desktop client preparation failed."
    }
    $fletClientBinaryDir = Join-Path $fletClientRoot "flet"
    if (-not (Test-Path (Join-Path $fletClientBinaryDir "flet.exe"))) {
        throw "Flet desktop client executable was not found: $fletClientBinaryDir"
    }

    if (Test-Path $stagedClient) {
        Remove-Item -LiteralPath $stagedClient -Recurse -Force
    }
    New-Item -ItemType Directory -Force $stagedClient | Out-Null
    Copy-Item -Path (Join-Path $fletClientBinaryDir "*") `
        -Destination $stagedClient -Recurse -Force

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    uv run pyinstaller --clean --noconfirm `
        "packaging\windows\DeskScribe.spec"
    $pyinstallerExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($pyinstallerExitCode -ne 0) {
        throw "PyInstaller build failed."
    }

    $version = (
        uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
    ).Trim()
    $releaseName = "DeskScribe-$version-windows-x64"
    $releaseDir = [IO.Path]::GetFullPath((Join-Path $distRoot $releaseName))
    $zipPath = [IO.Path]::GetFullPath((Join-Path $distRoot "$releaseName.zip"))
    Assert-ChildPath -Parent $distRoot -Child $releaseDir
    Assert-ChildPath -Parent $distRoot -Child $zipPath

    if (Test-Path $releaseDir) {
        Remove-Item -LiteralPath $releaseDir -Recurse -Force
    }
    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    New-Item -ItemType Directory -Force $releaseDir | Out-Null

    $executable = Join-Path $distRoot "DeskScribe.exe"
    if (-not (Test-Path $executable)) {
        throw "Built executable was not found: $executable"
    }
    Copy-Item -LiteralPath $executable -Destination $releaseDir
    Copy-Item -LiteralPath "WINDOWS_DISTRIBUTION.md" -Destination $releaseDir
    Copy-Item -LiteralPath "THIRD_PARTY_LICENSES.md" -Destination $releaseDir

    $releaseExecutable = Join-Path $releaseDir "DeskScribe.exe"
    $exeHash = (Get-FileHash -Algorithm SHA256 $releaseExecutable).Hash
    "$exeHash  DeskScribe.exe" | Set-Content `
        -LiteralPath (Join-Path $releaseDir "DeskScribe.exe.sha256") `
        -Encoding ascii

    Compress-Archive -Path (Join-Path $releaseDir "*") `
        -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash
    "$zipHash  $releaseName.zip" | Set-Content `
        -LiteralPath "$zipPath.sha256" -Encoding ascii

    Write-Host "Windows distribution created:"
    Write-Host "  $zipPath"
    Write-Host "  $zipPath.sha256"
}
finally {
    Pop-Location
}
