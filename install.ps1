# ═══════════════════════════════════════════════════════════
# Weaver Write - installer (Windows PowerShell / Terminal)
# ═══════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"

$Repo = "https://github.com/basharbhassan336699-cell/Weaver-Write.git"
$InstallDir = if ($env:WEAVER_HOME) { $env:WEAVER_HOME } else { "$HOME\weaver-write" }

Write-Host "═══════════════════════════════════════"
Write-Host "   Weaver Write - Installer (Windows)"
Write-Host "═══════════════════════════════════════"

# 1. ensure python + git
function Ensure-Cmd($cmd, $winget) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Installing $cmd..."
        winget install --id $winget -e --source winget
    }
}
Ensure-Cmd python "Python.Python.3.12"
Ensure-Cmd git "Git.Git"

# 2. clone or update
if (Test-Path "$InstallDir\.git") {
    Write-Host "Updating existing install..."
    git -C $InstallDir pull --ff-only
} else {
    Write-Host "Cloning Weaver Write..."
    git clone $Repo $InstallDir
}
Set-Location $InstallDir

# 3. python deps
Write-Host "Installing Python libraries..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. optional: tesseract + node (via winget)
Write-Host "Installing optional tools (OCR, node)..."
winget install --id UB-Mannheim.TesseractOCR -e --source winget 2>$null
winget install --id OpenJS.NodeJS -e --source winget 2>$null

# 5. html2pptx node deps
if (Test-Path "engines\html2pptx-core") {
    Push-Location engines\html2pptx-core
    npm install --silent adm-zip cheerio css pptxgenjs
    Pop-Location
}

# 6. create 'weaver' command (function in profile)
$profileLine = "function weaver { python `"$InstallDir\weaver.py`" @args }"
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }
if (-not (Select-String -Path $PROFILE -Pattern "weaver.py" -Quiet)) {
    Add-Content $PROFILE $profileLine
}

Write-Host ""
Write-Host "═══════════════════════════════════════"
Write-Host "Installed. Restart PowerShell, then run:  weaver install"
Write-Host "═══════════════════════════════════════"
python weaver.py install
