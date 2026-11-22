param(
    [switch]$Preview,
    [switch]$Studio,
    [switch]$Monitor,
    [switch]$Test
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyW = Join-Path $Root "venv\Scripts\pythonw.exe"
$Py = Join-Path $Root "venv\Scripts\python.exe"
$Exe = if ($Test -or -not (Test-Path $PyW)) { $Py } else { $PyW }
$Entry = Join-Path $Root "main.py"

$ArgList = @("`"$Entry`"")
if ($Preview) { $ArgList += "--preview" }
if ($Studio) { $ArgList += "--studio" }
if ($Monitor) { $ArgList += "--monitor" }
if ($Test) { $ArgList += "--test" }

Start-Process -FilePath $Exe -ArgumentList ($ArgList -join " ") -WorkingDirectory $Root
Write-Host "IAWallpaper iniciado via $Exe ($($ArgList -join ' '))"
