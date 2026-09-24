#!/usr/bin/env powershell

param (
  [Parameter(Position = 0)]
  [string]$BuildRoot,
  [Parameter(Position = 1)]
  [string]$SourceRoot
)

$InstallerDir = Join-Path $SourceRoot "packages\win_installer" | Resolve-Path
$DepsDir = Join-Path $BuildRoot "installer-deps"
if (!(Test-Path $DepsDir)) {
	New-Item -ItemType Directory -Path $DepsDir
}

$Env:BUILD_ROOT = $BuildRoot
$Env:SOURCE_ROOT = $SourceRoot

Set-Location $DepsDir

$GitHeaders = @{}
if (Test-Path 'Env:GITHUB_TOKEN') {
	$GitHeaders = @{ 'Authorization' = 'Bearer ' + $Env:GITHUB_TOKEN }
}

# DepCtrl
if (!(Test-Path DependencyControl)) {
	git clone https://github.com/TypesettingTools/DependencyControl.git
	Set-Location DependencyControl
	git checkout v0.6.3-alpha
	Set-Location $DepsDir
}

# YUtils
if (!(Test-Path YUtils)) {
	git clone https://github.com/TypesettingTools/YUtils.git
}

# luajson
if (!(Test-Path luajson)) {
	git clone https://github.com/harningt/luajson.git
}

# Avisynth
if (!(Test-Path AviSynthPlus64)) {
	$avsUrl = "https://github.com/AviSynth/AviSynthPlus/releases/download/v3.7.3/AviSynthPlus_3.7.3_20230715-filesonly.7z"
	Invoke-WebRequest $avsUrl -OutFile AviSynthPlus.7z -UseBasicParsing
	7z x AviSynthPlus.7z
	Rename-Item (Get-ChildItem -Filter "AviSynthPlus_*" -Directory) AviSynthPlus64
	Remove-Item AviSynthPlus.7z
}

# VSFilter
if (!(Test-Path VSFilter)) {
	$vsFilterDir = New-Item -ItemType Directory VSFilter
	Set-Location $vsFilterDir
	$vsFilterReleases = Invoke-WebRequest "https://api.github.com/repos/pinterf/xy-VSFilter/releases/latest" -Headers $GitHeaders -UseBasicParsing | ConvertFrom-Json
	$vsFilterUrl = $vsFilterReleases.assets[0].browser_download_url
	Invoke-WebRequest $vsFilterUrl -OutFile VSFilter.7z -UseBasicParsing
	7z x VSFilter.7z
	Remove-Item VSFilter.7z
	Set-Location $DepsDir
}

### VapourSynth plugins

# L-SMASH-Works
if (!(Test-Path L-SMASH-Works)) {
	New-Item -ItemType Directory L-SMASH-Works
	$lsmasReleases = Invoke-WebRequest "https://api.github.com/repos/AkarinVS/L-SMASH-Works/releases/latest" -Headers $GitHeaders -UseBasicParsing | ConvertFrom-Json
	$lsmasUrl = "https://github.com/AkarinVS/L-SMASH-Works/releases/download/" + $lsmasReleases.tag_name + "/release-x86_64-cachedir-cwd.zip"
	Invoke-WebRequest $lsmasUrl -OutFile release-x86_64-cachedir-cwd.zip -UseBasicParsing
	Expand-Archive -LiteralPath release-x86_64-cachedir-cwd.zip -DestinationPath L-SMASH-Works
	Remove-Item release-x86_64-cachedir-cwd.zip
}

# BestSource
if (!(Test-Path BestSource)) {
	$bsDir = New-Item -ItemType Directory BestSource
	Set-Location $bsDir
	$basReleases = Invoke-WebRequest "https://api.github.com/repos/vapoursynth/bestsource/releases/latest" -Headers $GitHeaders -UseBasicParsing | ConvertFrom-Json
	$bsAsset = $basReleases.assets | Where-Object { $_.name -like "BestSource-*-win64-clang-vs-only.zip" } | Select-Object -First 1
	Invoke-WebRequest $bsAsset.browser_download_url -OutFile $bsAsset.name -UseBasicParsing
	Expand-Archive -LiteralPath $bsAsset.name -DestinationPath .
	Rename-Item ($bsAsset.name -replace '\.zip$', '.dll') BestSource.dll
	Remove-Item $bsAsset.name
	Set-Location $DepsDir
}

# SCXVid
if (!(Test-Path SCXVid)) {
	$scxDir = New-Item -ItemType Directory SCXVid
	Set-Location $scxDir
	$scxUrl = "https://github.com/dubhatervapoursynth/vapoursynth-scxvid/releases/download/v1/vapoursynth-scxvid-v1-win64.7z"
	Invoke-WebRequest $scxUrl -OutFile vapoursynth-scxvid-v1-win64.7z -UseBasicParsing
	7z x vapoursynth-scxvid-v1-win64.7z
	Remove-Item vapoursynth-scxvid-v1-win64.7z
	Set-Location $DepsDir
}

# WWXD
# The repository moved to dubhatervapoursynth. Its old API endpoint answers with a
# redirect that drops the Authorization header, so the release lookup randomly hit
# anonymous rate limits and left the DLL missing. v1.0 is the only release.
$wwxdDll = Join-Path $DepsDir "WWXD\libwwxd64.dll"
if (!(Test-Path $wwxdDll)) {
	New-Item -ItemType Directory -Force WWXD
	$wwxdUrl = "https://github.com/dubhatervapoursynth/vapoursynth-wwxd/releases/download/v1.0/libwwxd64.dll"
	$wwxdSha256 = "4DE8D4B887FF43B2AF42B13D2D51D1490ACC40F25E490EE1BAD2EAFCECC5B3CC"
	for ($attempt = 1; $attempt -le 4; $attempt++) {
		try {
			Invoke-WebRequest $wwxdUrl -OutFile $wwxdDll -UseBasicParsing -ErrorAction Stop
			# Get-FileHash is not always available to Windows PowerShell on CI runners
			$sha256 = [System.Security.Cryptography.SHA256]::Create()
			$wwxdHash = [BitConverter]::ToString($sha256.ComputeHash([IO.File]::ReadAllBytes($wwxdDll))) -replace '-', ''
			if ($wwxdHash -eq $wwxdSha256) { break }
			Write-Warning "WWXD download has an unexpected SHA256 hash"
		} catch {
			Write-Warning "WWXD download attempt $attempt failed: $($_.Exception.Message)"
		}
		Remove-Item $wwxdDll -ErrorAction SilentlyContinue
		if ($attempt -lt 4) { Start-Sleep -Seconds ([math]::Pow(2, $attempt)) }
	}
	if (!(Test-Path $wwxdDll)) {
		Write-Error "Could not download $wwxdUrl"
		Exit 1
	}
}


# ffi-experiments
if (!(Test-Path ffi-experiments)) {
	Get-Command "moonc" # check to ensure Moonscript is present
	git clone https://github.com/arch1t3cht/ffi-experiments.git
	Set-Location ffi-experiments
	meson build -Ddefault_library=static
	if(!$?) { Exit $LASTEXITCODE }
	meson compile -C build
	if(!$?) { Exit $LASTEXITCODE }
	Set-Location $DepsDir
}

# VC++ redistributable
if (!(Test-Path VC_redist)) {
	$redistDir = New-Item -ItemType Directory VC_redist
	Invoke-WebRequest https://aka.ms/vs/17/release/VC_redist.x64.exe -OutFile "$redistDir\VC_redist.x64.exe" -UseBasicParsing
}

# XAudio2 redistributable
if (!(Test-Path XAudio2_redist)) {
	New-Item -ItemType Directory XAudio2_redist
	Invoke-WebRequest https://www.nuget.org/api/v2/package/Microsoft.XAudio2.Redist/1.2.11 -OutFile XAudio2Redist.zip
	Expand-Archive -LiteralPath XAudio2Redist.zip -DestinationPath XAudio2_redist
	Remove-Item XAudio2Redist.zip
}

# dictionaries
if (!(Test-Path dictionaries)) {
	New-Item -ItemType Directory dictionaries
	Invoke-WebRequest https://raw.githubusercontent.com/TypesettingTools/Aegisub-dictionaries/master/dicts/en_US.aff -OutFile dictionaries/en_US.aff -UseBasicParsing
	Invoke-WebRequest https://raw.githubusercontent.com/TypesettingTools/Aegisub-dictionaries/master/dicts/en_US.dic -OutFile dictionaries/en_US.dic -UseBasicParsing
}

# localization
Set-Location $BuildRoot
meson compile aegisub-gmo
if(!$?) { Exit $LASTEXITCODE }

# Invoke InnoSetup
$IssUrl = Join-Path $InstallerDir "aegisub_depctrl.iss"
iscc $IssUrl
if(!$?) { Exit $LASTEXITCODE }