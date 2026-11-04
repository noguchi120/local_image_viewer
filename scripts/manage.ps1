param(
    [ValidateSet('setup', 'start', 'develop', 'build')]
    [string]$Mode = 'start'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

# Run a native command and stop the workflow if the command fails.
function Invoke-Checked {
    param([string]$Executable, [string[]]$CommandArguments)
    & $Executable @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable $($CommandArguments -join ' ')"
    }
}

# Create the project-only Python environment and install the server dependencies.
function Install-Backend {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
        $uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
        if (Test-Path -LiteralPath $uvPath) {
            Invoke-Checked $uvPath @('--cache-dir', '.cache/uv', 'venv', '--python', '>=3.12', '.venv')
        } else {
            $pyCommand = Get-Command py -ErrorAction SilentlyContinue
            if (-not $pyCommand) { throw 'Install Python 3.12 or newer (python.org), or uv, then run setup.cmd again.' }
            Invoke-Checked $pyCommand.Source @('-3', '-m', 'venv', '.venv')
        }
    }
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
    if (Test-Path -LiteralPath $uvPath) {
        Invoke-Checked $uvPath @('--cache-dir', '.cache/uv', 'pip', 'install', '--python', $pythonPath, '-r', 'requirements.txt')
    } else {
        Invoke-Checked $pythonPath @('-m', 'pip', 'install', '-r', 'requirements.txt')
    }
}

# Install the frontend packages when needed and build the files served by FastAPI.
function Build-Frontend {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) { throw 'Install Node.js 22 LTS or newer, then run setup.cmd again.' }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules'))) {
        $installCommand = if (Test-Path -LiteralPath 'package-lock.json') { 'ci' } else { 'install' }
        Invoke-Checked $npmCommand.Source @($installCommand)
    }
    Invoke-Checked $npmCommand.Source @('run', 'build')
}

try {
    if ($Mode -eq 'setup') {
        Install-Backend
        Build-Frontend
        Write-Host "`nSetup complete. Double-click start.cmd to open Local Gallery."
        exit 0
    }
    if ($Mode -eq 'build') {
        Build-Frontend
        Write-Host "`nBuild complete. Restart Local Gallery to use the updated files."
        exit 0
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) { Install-Backend }
    if ($Mode -eq 'develop') {
        if (-not (Test-Path -LiteralPath 'node_modules\vite\bin\vite.js')) { Build-Frontend }
        New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'data') | Out-Null
        $nodeCommand = Get-Command node.exe -ErrorAction Stop
        $viteProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '0.0.0.0') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput 'data/vite.log' -RedirectStandardError 'data/vite-error.log' -PassThru
        try {
            Start-Sleep -Milliseconds 700
            if ($viteProcess.HasExited) { throw 'Vite could not start. See data/vite-error.log (port 5173 may be in use).' }
            Invoke-Checked $pythonPath @('-m', 'backend.launcher', '--dev')
        } finally {
            if (-not $viteProcess.HasExited) { Stop-Process -Id $viteProcess.Id -ErrorAction SilentlyContinue }
        }
    } else {
        if (-not (Test-Path -LiteralPath 'dist\index.html')) { Build-Frontend }
        Invoke-Checked $pythonPath @('-m', 'backend.launcher')
    }
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
