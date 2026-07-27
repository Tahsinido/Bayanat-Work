<#
.SYNOPSIS
    Handler for the bayanat-open: protocol. Opens a local folder in Explorer.

.DESCRIPTION
    Invoked by Windows when a bayanat-open: link is followed from the browser,
    because browsers refuse to navigate from an http:// page to file://.

    Security: this handler can be triggered by ANY web page, not just Bayanat.
    It is therefore restricted to *revealing* things in Explorer and will not
    launch anything:

      - a directory is opened in Explorer
      - a file is revealed via /select, so Explorer highlights it without
        running it (this matters for .exe, .bat, .lnk and similar)
      - anything that does not already exist on disk is refused

    It never uses Invoke-Expression, never passes the path to a shell, and
    never starts the target itself.
#>

param([Parameter(Position = 0)][string]$Uri)

Add-Type -AssemblyName System.Windows.Forms

function Show-Message {
    param([string]$Text, [string]$Icon = 'Information')
    [System.Windows.Forms.MessageBox]::Show(
        $Text, 'Bayanat', [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::$Icon
    ) | Out-Null
}

if ([string]::IsNullOrWhiteSpace($Uri)) {
    Show-Message 'No path was supplied.' 'Warning'
    exit 1
}

# Windows hands over the whole URI, e.g. bayanat-open:D%3A%5CProjects%5CVR
$raw = $Uri -replace '^bayanat-open:(//)?', ''

try {
    $path = [System.Uri]::UnescapeDataString($raw)
} catch {
    Show-Message "Could not decode the path:`n`n$raw" 'Warning'
    exit 1
}

$path = $path.Trim().Trim('"')
# Links may carry forward slashes; Explorer wants backslashes.
$path = $path -replace '/', '\'

if ([string]::IsNullOrWhiteSpace($path)) {
    Show-Message 'No path was supplied.' 'Warning'
    exit 1
}

# Refuse anything that is not a plain local or UNC path (no other schemes).
if ($path -notmatch '^([A-Za-z]:\\|\\\\)') {
    Show-Message "Not a local or network path:`n`n$path" 'Warning'
    exit 1
}

if (Test-Path -LiteralPath $path -PathType Container) {
    Start-Process -FilePath 'explorer.exe' -ArgumentList "`"$path`""
    exit 0
}

if (Test-Path -LiteralPath $path -PathType Leaf) {
    # /select highlights the file in its folder instead of opening it.
    Start-Process -FilePath 'explorer.exe' -ArgumentList "/select,`"$path`""
    exit 0
}

Show-Message "This folder was not found on this computer:`n`n$path`n`nCheck that the drive is connected and the path is correct." 'Warning'
exit 1
