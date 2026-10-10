# Instalador de CapCut MCP para Windows.
# Uso (PowerShell, desde la carpeta del repo o en cualquier lugar):
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Instala dependencias que falten (Python, Git, ffmpeg vía winget), clona/actualiza el repo en
# D:\CapCut_Studio\_mcp, crea el entorno virtual y registra el servidor en Claude Desktop.

param(
    [string]$StudioRoot = "D:\CapCut_Studio",
    [string]$RepoUrl = "https://github.com/TimothyArcher90/Capcut_MCP.git",
    [switch]$NoExtras
)

$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Test-Path ($StudioRoot.Substring(0, 3)))) {
    Write-Host "La unidad de $StudioRoot no existe. Usa -StudioRoot otra ruta." -ForegroundColor Red; exit 1
}

# 1) Dependencias
foreach ($dep in @(
    @{cmd = "git";    id = "Git.Git"},
    @{cmd = "ffmpeg"; id = "Gyan.FFmpeg"},
    @{cmd = "py";     id = "Python.Python.3.12"}
)) {
    if (-not (Has $dep.cmd)) {
        Step "Instalando $($dep.id) con winget"
        winget install --id $dep.id -e --accept-source-agreements --accept-package-agreements
        Refresh-Path
    }
}

# 2) Código
$McpDir = Join-Path $StudioRoot "_mcp"
New-Item -ItemType Directory -Force -Path $StudioRoot | Out-Null
if (Test-Path (Join-Path $McpDir ".git")) {
    Step "Actualizando repo en $McpDir"
    git -C $McpDir pull --ff-only
} else {
    Step "Clonando repo en $McpDir (si es privado, GitHub pedirá iniciar sesión)"
    git clone $RepoUrl $McpDir
}

# 3) Entorno virtual
Step "Creando entorno virtual e instalando paquetes"
$Venv = Join-Path $McpDir ".venv"
if (-not (Test-Path $Venv)) { py -3 -m venv $Venv }
$Pip = Join-Path $Venv "Scripts\pip.exe"
& $Pip install --upgrade pip | Out-Null
$target = if ($NoExtras) { "." } else { ".[all]" }
Push-Location $McpDir; & $Pip install -e $target; Pop-Location
$Exe = Join-Path $Venv "Scripts\capcut-mcp.exe"

# 4) Carpeta de borradores de CapCut
$Drafts = Join-Path $env:LOCALAPPDATA "CapCut\User Data\Projects\com.lveditor.draft"
if (-not (Test-Path $Drafts)) {
    Write-Host "No encontré la carpeta de borradores en $Drafts." -ForegroundColor Yellow
    Write-Host "Mírala en CapCut > Ajustes > Borradores y edita CAPCUT_DRAFTS_DIR en la config de Claude." -ForegroundColor Yellow
}

# 5) Registrar en Claude Desktop
Step "Registrando el servidor en Claude Desktop"
$CfgDir = Join-Path $env:APPDATA "Claude"
$Cfg = Join-Path $CfgDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $CfgDir | Out-Null
$json = if (Test-Path $Cfg) {
    Copy-Item $Cfg "$Cfg.bak" -Force
    Get-Content $Cfg -Raw | ConvertFrom-Json
} else { [pscustomobject]@{} }
if (-not $json.PSObject.Properties["mcpServers"]) {
    $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
}
$server = [pscustomobject]@{
    command = $Exe
    args    = @()
    env     = [pscustomobject]@{ CAPCUT_STUDIO_ROOT = $StudioRoot; CAPCUT_DRAFTS_DIR = $Drafts }
}
$json.mcpServers | Add-Member -NotePropertyName capcut -NotePropertyValue $server -Force
$json | ConvertTo-Json -Depth 10 | Set-Content $Cfg -Encoding UTF8

# 6) Prueba rápida
Step "Comprobando instalación"
& (Join-Path $Venv "Scripts\python.exe") -c "import capcut_mcp.server; print('capcut-mcp OK')"
if (Has "claude") {
    Step "Registrando también en Claude Code"
    claude mcp add capcut -- $Exe 2>$null
}

Write-Host ""
Write-Host "Listo. Cierra Claude Desktop por completo (también en la bandeja) y ábrelo de nuevo." -ForegroundColor Green
Write-Host "Luego escribe en Claude: 'Ejecuta capcut_status'." -ForegroundColor Green
