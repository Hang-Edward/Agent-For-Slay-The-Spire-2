# Slay the Spire AI Agent — Windows 启动脚本
#
# 用法:
#   .\run.ps1                          # 使用 DEEPSEEK_API_KEY 环境变量运行
#   .\run.ps1 -ApiKey "sk-..."         # 指定 API Key
#   .\run.ps1 -Help                    # 查看所有选项

param(
    [string]$ApiKey = "",
    [switch]$Help = $false,
    [string]$Model = "",
    [string]$HostName = "",
    [int]$Port = 0,
    [string]$Backend = "",
    [switch]$Mock = $false,
    [string]$MockFile = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$EngineDir = Join-Path $ScriptDir "engine"
$ConfigDir = Join-Path $ScriptDir "config"

# 切换到 engine 目录（Python import 依赖工作目录）
Set-Location $EngineDir

# 从 config/api_key.yaml 中读取 API Key
$ApiKeyFile = Join-Path $ConfigDir "api_key.yaml"
if (Test-Path $ApiKeyFile) {
    $yaml = Get-Content $ApiKeyFile -Raw
    if ($yaml -match 'api_key\s*:\s*"([^"]+)"') {
        $key = $Matches[1]
        if ($key -and $key -ne "sk-your-deepseek-api-key-here") {
            $env:DEEPSEEK_API_KEY = $key
        }
    }
}

# CLI 参数优先级高于配置文件
if ($ApiKey) {
    $env:DEEPSEEK_API_KEY = $ApiKey
}

# 检查 API Key 是否可用
if (-not $env:DEEPSEEK_API_KEY -and -not $Help) {
    Write-Host "错误: 未配置 DeepSeek API Key。" -ForegroundColor Red
    Write-Host "设置 DEEPSEEK_API_KEY 环境变量，或使用 -ApiKey 参数指定" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "示例:" -ForegroundColor Cyan
    Write-Host "  .\run.ps1 -ApiKey ""sk-你的key""" -ForegroundColor Cyan
    exit 1
}

if ($Help) {
    & python main.py --help
    exit 0
}

# 查找可用的 Python（跳过 WindowsApps 占位符）
$pythonCmd = ""
$pythonCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "C:\Program Files\Python313\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe"
)
# 先检查 PATH 中排除 WindowsApps 后的 python
$pathPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($pathPython -and $pathPython -notlike "*WindowsApps*") {
    $pythonCmd = $pathPython
} else {
    foreach ($candidate in $pythonCandidates) {
        if (Test-Path $candidate) {
            $pythonCmd = $candidate
            break
        }
    }
}
if (-not $pythonCmd) {
    # 最后再尝试 python3
    $pathPython3 = (Get-Command python3 -ErrorAction SilentlyContinue).Source
    if ($pathPython3 -and $pathPython3 -notlike "*WindowsApps*") {
        $pythonCmd = $pathPython3
    }
}
if (-not $pythonCmd) {
    Write-Host "错误: 找不到 Python。请安装 Python 3.10+。" -ForegroundColor Red
    Write-Host "下载: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host "使用 Python: $pythonCmd" -ForegroundColor Cyan

# 创建虚拟环境（如不存在）
$VenvDir = Join-Path $EngineDir "venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "正在创建 Python 虚拟环境..." -ForegroundColor Cyan
    & $pythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 虚拟环境创建失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "正在安装依赖..." -ForegroundColor Cyan
    & "$VenvDir\Scripts\python.exe" -m pip install -r (Join-Path $EngineDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "警告: 部分依赖安装失败" -ForegroundColor Yellow
    }
}

# 构建 Python 参数
$PyArgs = @()
if ($Model) { $PyArgs += "--model"; $PyArgs += $Model }
if ($HostName) { $PyArgs += "--host"; $PyArgs += $HostName }
if ($Port -gt 0) { $PyArgs += "--port"; $PyArgs += $Port }
if ($Backend) { $PyArgs += "--backend"; $PyArgs += $Backend }
if ($Mock) { $PyArgs += "--mock" }
if ($MockFile) { $PyArgs += "--mock-file"; $PyArgs += $MockFile }

# 启动 AI Agent
Write-Host "正在启动 Slay the Spire AI Agent..." -ForegroundColor Green
& "$VenvDir\Scripts\python.exe" main.py @PyArgs
