# Build and deploy Sts2AiMod through Slay the Spire 2's native local mods folder.

$ErrorActionPreference = "Stop"

$GameDir = "D:\Steam\steamapps\common\Slay the Spire 2"
$ModDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectPath = Join-Path $ModDir "Sts2AiMod.csproj"
$OutputDll = Join-Path $ModDir "bin\Debug\net9.0\Sts2AiMod.dll"
$ModsRoot = Join-Path $GameDir "mods"
$TargetModDir = Join-Path $ModsRoot "Sts2AiMod"
$TargetDll = Join-Path $TargetModDir "Sts2AiMod.dll"
$ManifestPath = Join-Path $TargetModDir "Sts2AiMod.json"
$AppIdPath = Join-Path $GameDir "steam_appid.txt"
$LauncherPath = Join-Path $GameDir "run_ai_agent.ps1"
$RuntimeConfig = Join-Path $GameDir "data_sts2_windows_x86_64\sts2.runtimeconfig.json"
$RuntimeConfigBackup = "$RuntimeConfig.codex-backup"

if (-not (Test-Path -LiteralPath $GameDir)) {
    Write-Host "Error: game directory not found: $GameDir" -ForegroundColor Red
    exit 1
}

Write-Host "Building Sts2AiMod..." -ForegroundColor Cyan
dotnet build $ProjectPath -nologo
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $TargetModDir | Out-Null
Copy-Item -LiteralPath $OutputDll -Destination $TargetDll -Force

$Manifest = [ordered]@{
    id = "Sts2AiMod"
    name = "STS2 AI Agent Bridge"
    author = "local"
    description = "Local HTTP bridge for the Python AI agent."
    version = "0.1.0"
    has_pck = $false
    has_dll = $true
    affects_gameplay = $true
    min_game_version = "0.0.0"
}
$Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

# Keep direct exe launches from failing Steam init during local development.
Set-Content -LiteralPath $AppIdPath -Value "2868840" -Encoding ASCII

# Restore the runtimeconfig if an earlier startup-hook experiment changed it.
if (Test-Path -LiteralPath $RuntimeConfigBackup) {
    Copy-Item -LiteralPath $RuntimeConfigBackup -Destination $RuntimeConfig -Force
}

$LauncherLines = @(
    '# Slay the Spire 2 AI Agent launcher',
    '# Starts the game with steam_appid.txt present; the mod is loaded from mods\Sts2AiMod.',
    '',
    '$GameDir = Split-Path -Parent $MyInvocation.MyCommand.Definition',
    '$SteamAppId = Join-Path $GameDir "steam_appid.txt"',
    'Set-Content -LiteralPath $SteamAppId -Value "2868840" -Encoding ASCII',
    'Write-Host "Steam appid set to 2868840" -ForegroundColor Cyan',
    'Write-Host "Starting game..." -ForegroundColor Green',
    'Start-Process -FilePath (Join-Path $GameDir "SlayTheSpire2.exe") -WorkingDirectory $GameDir',
    '',
    'Write-Host ""',
    'Write-Host "After the game starts, run the Python AI engine:"',
    'Write-Host "  cd D:\Desktop\projects\Agent-For-Slay-The-Spire-2\engine"',
    'Write-Host "  py main.py --dry-run"'
)
Set-Content -LiteralPath $LauncherPath -Value $LauncherLines -Encoding UTF8

Write-Host "Deployed mod DLL: $TargetDll" -ForegroundColor Green
Write-Host "Wrote manifest: $ManifestPath" -ForegroundColor Green
Write-Host "Launcher created: $LauncherPath" -ForegroundColor Green
