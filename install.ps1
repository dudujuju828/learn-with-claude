# Installs a global `learn` command that launches the knowledge shell from any
# terminal (cmd, PowerShell, Git Bash). Run:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$launchPy = Join-Path $repo 'learn.py'
$bin = Join-Path $HOME '.local\bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null

# cmd / PowerShell launcher
$cmd = "@echo off`r`npython `"$launchPy`" %*`r`n"
[IO.File]::WriteAllText((Join-Path $bin 'learn.cmd'), $cmd)

# Git Bash launcher (LF line endings, forward-slash path)
$pyUnix = ($launchPy -replace '\\', '/')
$sh = "#!/bin/sh`nexec python `"$pyUnix`" `"`$@`"`n"
[IO.File]::WriteAllText((Join-Path $bin 'learn'), $sh)

Write-Host "Installed 'learn' -> $bin (points at $launchPy)"

if (($env:PATH -split ';' | ForEach-Object { $_.TrimEnd('\') }) -notcontains $bin.TrimEnd('\')) {
    Write-Warning "$bin is not on your PATH. Add it (User env var PATH) so 'learn' is found everywhere."
} else {
    Write-Host "Done. Open a new terminal and run:  learn"
}
