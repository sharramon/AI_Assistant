# Relaunch the app: stop it, then start it again the usual way (as in the app-update skill).
# Safe to run from inside the app (e.g. by the Main Assistant): it first re-runs itself as
# a detached, hidden process, so it survives the app and its claude sessions being stopped.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\relaunch.ps1
param([switch]$Detached)

$repo = Split-Path -Parent $PSScriptRoot

if (-not $Detached) {
    Start-Process powershell -WindowStyle Hidden -WorkingDirectory $repo -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Detached'
    "Relaunch started in the background; the app restarts in a few seconds."
    exit
}

New-Item -ItemType Directory -Force (Join-Path $repo "logs") | Out-Null
Start-Transcript -Path (Join-Path $repo "logs\relaunch.log") | Out-Null
Start-Sleep -Seconds 2  # let the caller's tool call return first

$app = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match "python" -and $_.CommandLine -match "-m assistant") -or ($_.Name -eq "powershell.exe" -and $_.CommandLine -match "Assistant: talk here") }
$claude = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "claude.exe" -and $app.ProcessId -contains $_.ParentProcessId }
(@($app) + @($claude)) | Where-Object { $_ } | ForEach-Object { "Stopping $($_.Name) $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2  # let the temp UI port free up
Start-Process powershell -WorkingDirectory $repo -ArgumentList '-NoExit', '-Command', '$host.UI.RawUI.WindowTitle = ''Assistant: talk here''; .\.venv\Scripts\python -m assistant'
"Started the app."
Stop-Transcript | Out-Null
