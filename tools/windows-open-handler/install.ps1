<#
.SYNOPSIS
    Registers (or removes) the bayanat-open: protocol handler for this user.

.DESCRIPTION
    Writes to HKCU:\Software\Classes, so no administrator rights are needed and
    nothing changes for other accounts on the machine.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
    powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
#>

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'

$scheme  = 'bayanat-open'
$root    = "HKCU:\Software\Classes\$scheme"
$handler = Join-Path $PSScriptRoot 'open-path.ps1'

if ($Uninstall) {
    if (Test-Path $root) {
        Remove-Item -Path $root -Recurse -Force
        Write-Host "Removed the $scheme handler." -ForegroundColor Green
    } else {
        Write-Host "The $scheme handler was not registered." -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path -LiteralPath $handler)) {
    throw "open-path.ps1 was not found next to this script (expected at $handler)."
}

# Full path to Windows PowerShell, so the association does not depend on the
# PATH seen by whichever browser launches it. $PSHOME is not used: under
# PowerShell 7 it points at pwsh.exe's directory, which has no powershell.exe.
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $psExe)) {
    $psExe = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
}
if (-not $psExe) { throw 'Could not locate powershell.exe on this system.' }

$command = '"{0}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" "%1"' -f $psExe, $handler

New-Item -Path $root -Force | Out-Null
Set-ItemProperty -Path $root -Name '(Default)' -Value 'URL:Bayanat Open Folder'
# Presence of this empty value is what marks the key as a URL scheme.
Set-ItemProperty -Path $root -Name 'URL Protocol' -Value ''

$commandKey = "$root\shell\open\command"
New-Item -Path $commandKey -Force | Out-Null
Set-ItemProperty -Path $commandKey -Name '(Default)' -Value $command

Write-Host "Registered the $scheme handler for $env:USERNAME." -ForegroundColor Green
Write-Host "Handler script: $handler"
Write-Host ''
Write-Host 'Restart your browser, then use Open on a location or site link.'
Write-Host 'The browser will ask once for permission to open the helper - allow it.'
