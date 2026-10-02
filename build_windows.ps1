$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name 'TanzimPedagogique' `
    --collect-binaries 'ortools' --add-data 'config;config' --add-data 'assets;assets' main.py

Write-Host "Application: $root\dist\TanzimPedagogique.exe"
