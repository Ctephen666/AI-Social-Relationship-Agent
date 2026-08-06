$ErrorActionPreference = "Stop"

$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Virtual environment not found: $PythonExe"
}

& $PythonExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing. Install requirements-dev.txt first."
}

$BuildDir = Join-Path $BackendDir "build"
$DistDir = Join-Path $BackendDir "dist"
if (Test-Path -LiteralPath $BuildDir) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
if (Test-Path -LiteralPath $DistDir) { Remove-Item -LiteralPath $DistDir -Recurse -Force }

Push-Location $BackendDir
try {
    & $PythonExe -m PyInstaller --noconfirm --clean "spark_agent.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$ExePath = Join-Path $DistDir "StephenAgent\StephenAgent.exe"
if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Build finished but executable was not found: $ExePath"
}

# Microsoft Store Python may bundle an old VC++ runtime, while recent
# ONNX Runtime wheels require the current redistributable already installed in
# Windows. Overlay the system copies to prevent DLL initialization failures.
$InternalDir = Join-Path $DistDir "StephenAgent\_internal"
$RuntimeNames = @(
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "concrt140.dll"
)
foreach ($RuntimeName in $RuntimeNames) {
    $RuntimeSource = Join-Path $env:WINDIR "System32\$RuntimeName"
    if (Test-Path -LiteralPath $RuntimeSource) {
        Copy-Item -LiteralPath $RuntimeSource -Destination $InternalDir -Force
    }
}
Copy-Item -LiteralPath (Join-Path $BackendDir ".env.example") -Destination (Join-Path (Split-Path -Parent $ExePath) ".env.example") -Force
$VoiceModels = Join-Path (Split-Path -Parent $BackendDir) "data\voice_models"
if (Test-Path -LiteralPath $VoiceModels) {
    $PackagedModels = Join-Path (Split-Path -Parent $ExePath) "data\voice_models"
    New-Item -ItemType Directory -Force -Path $PackagedModels | Out-Null
    $VadModel = Join-Path $VoiceModels "silero_vad.onnx"
    if (Test-Path -LiteralPath $VadModel) {
        Copy-Item -LiteralPath $VadModel -Destination $PackagedModels -Force
    }
    Get-ChildItem -LiteralPath $VoiceModels -Directory |
        Where-Object { $_.Name -match "sense.?voice" } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $PackagedModels -Recurse -Force }
}
Write-Host "Build complete: $ExePath" -ForegroundColor Green
