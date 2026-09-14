param(
    [string]$OutputDirectory = "build-youtube-win-x64"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$output = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
}
$rootPrefix = $root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (!$output.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must be inside the repository."
}

$sha = "b186a40bc21e58a8c9651cf616cbb5e80425dfc6"
$sourceRoot = Join-Path $root ".deps/src"
$archive = Join-Path $sourceRoot "YTSubConverter-$sha.tar.gz"
$source = Join-Path $sourceRoot "YTSubConverter-$sha"
$patched = Join-Path $root "tools/youtube/obj/upstream"
$project = Join-Path $root "tools/youtube/Aegisub.Youtube.csproj"

function Assert-Sha256([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) {
        throw "SHA-256 mismatch for $Path. Expected $Expected, got $actual."
    }
}

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command exited with code $LASTEXITCODE."
    }
}

New-Item -ItemType Directory -Force -Path $sourceRoot | Out-Null
if (!(Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/arcusmaximus/YTSubConverter/archive/$sha.tar.gz" -OutFile $archive
}
Assert-Sha256 $archive "9ef9a800669ce64cb5249bd662d898b95715e9af443aecbbeed1806f6983ad69"
if (!(Test-Path -LiteralPath $source)) {
    Invoke-Checked "tar" @("-xf", $archive, "-C", $sourceRoot)
}

$independentPatch = Join-Path $root "tools/youtube/patches/independent-justification.patch"
$assPatch = Join-Path $root "tools/youtube/patches/ass-justification.patch"
$assHandler = Join-Path $root "tools/youtube/upstream-support/AssJustificationTagHandler.cs"
Assert-Sha256 $independentPatch "b7c89b0744bf16e1997ca3ac3036a925a90c94ef6f7b0570950784e2b23390cf"
Assert-Sha256 $assPatch "f3f031790aa51761731c96c7641e00215571ea796274a261de1b23d0097ebfb4"
Assert-Sha256 $assHandler "34d27228fc056fd69667b9a7785d220e3341dd08b579e33492b36090ff37e850"

if (Test-Path -LiteralPath $patched) {
    Remove-Item -LiteralPath $patched -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $patched | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $patched "YTSubConverter.Shared") | Out-Null
Copy-Item -Path (Join-Path $source "YTSubConverter.Shared/*") -Destination (Join-Path $patched "YTSubConverter.Shared") -Recurse -Force
Invoke-Checked "git" @("-C", $root, "apply", "--directory=tools/youtube/obj/upstream", "--whitespace=nowarn", $independentPatch)
Invoke-Checked "git" @("-C", $root, "apply", "--directory=tools/youtube/obj/upstream", "--whitespace=nowarn", $assPatch)
Copy-Item -LiteralPath $assHandler -Destination (Join-Path $patched "YTSubConverter.Shared/Formats/Ass/Tags/AssJustificationTagHandler.cs")

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Recurse -Force
}
Invoke-Checked "dotnet" @("restore", $project, "-p:RuntimeIdentifier=win-x64", "-p:RuntimeFrameworkVersion=10.0.9", "-p:RestoreLockedMode=true")
Invoke-Checked "dotnet" @(
    "publish", $project, "-c", "Release", "-r", "win-x64", "--self-contained", "true", "--no-restore",
    "-p:RuntimeFrameworkVersion=10.0.9", "-o", $output
)

$upstreamLicense = Join-Path $source "LICENSE"
Assert-Sha256 $upstreamLicense "62dc34f41630a659329368e0ba1464906ebe798791426ae025cec3b588a101d3"
Copy-Item -LiteralPath $upstreamLicense -Destination (Join-Path $output "YTSubConverter-LICENSE")
$dotnetLicense = Join-Path $output "DOTNET-LICENSE.txt"
$dotnetNotices = Join-Path $output "DOTNET-THIRD-PARTY-NOTICES.txt"
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/dotnet/runtime/v10.0.9/LICENSE.TXT" -OutFile $dotnetLicense
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/dotnet/runtime/v10.0.9/THIRD-PARTY-NOTICES.TXT" -OutFile $dotnetNotices
Assert-Sha256 $dotnetLicense "cfc21f5e8bd655ae997eec916138b707b1d290b83272c02a95c9f821b8c87310"
Assert-Sha256 $dotnetNotices "66f1d4e44973185519bb4aa8a9718eb22fc7af2cc532e3ae9cfc4c127ee7fc54"

if ([Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows)) {
    Invoke-Checked (Join-Path $output "aegisub-youtube.exe") @("--help")
} else {
    Write-Host "Cross-published Windows helper to $output"
}
