# Restart the assistant app: find this repo's running app, stop it and what it started, then
# launch it again the usual way (a new "Assistant: talk here" window), as in the app-update skill.
#
# Finds ONLY this repo's app: a process running this repo's .venv\Scripts\python.exe with
# `-m assistant`. It stops that process tree (the base python the venv launcher runs, the
# claude sessions, the html_viewer companion, the assistant_view console, Edge windows it
# opened), the "Assistant: talk here" window hosting it, and Edge windows on the app's own
# profiles (temp_ui_window, html_viewer_window). Nothing else. If no app is running, it only
# prints the launch command, so it never starts a second copy.
#
# Safe to start from inside the app (detached, e.g. with Start-Process): it waits a few
# seconds first and never stops itself. A log goes to logs\restart_app.log.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart_app.ps1

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $repo '.venv\Scripts\python.exe'
$title = 'Assistant: talk here'
$launchCmd = "`$host.UI.RawUI.WindowTitle = '$title'; & '.\.venv\Scripts\python.exe' -m assistant"
$profiles = @('temp_ui_window', 'html_viewer_window') | ForEach-Object {
    '--user-data-dir=' + (Join-Path $env:LOCALAPPDATA "AI_Assistant\$_")
}

New-Item -ItemType Directory -Force (Join-Path $repo 'logs') | Out-Null
try { Start-Transcript -Path (Join-Path $repo 'logs\restart_app.log') | Out-Null } catch {}

function Show($p) { "  {0,-16} {1,6}  {2}" -f $p.Name, $p.ProcessId, $p.CommandLine }

"Restart: repo $repo"
"Waiting 4 s so the caller can finish..."
Start-Sleep -Seconds 4

$all = @(Get-CimInstance Win32_Process)
$roots = @($all | Where-Object {
    $_.Name -like 'python*.exe' -and $_.ExecutablePath -and
    ($_.ExecutablePath -ieq $venvPy) -and
    ($_.CommandLine -match '(^|\s)-m\s+assistant(\s|$)')
})

if ($roots.Count -eq 0) {
    "No running app found (no $venvPy -m assistant process). Not launching, to avoid a second copy."
    "To start it yourself, from $repo :"
    "  powershell -NoExit -Command `"$launchCmd`""
    try { Stop-Transcript | Out-Null } catch {}
    exit 0
}

"Found the app:"
$roots | ForEach-Object { Show $_ }

# The whole tree under each app process, never this script itself.
$byParent = @{}
foreach ($p in $all) {
    $key = [int]$p.ParentProcessId
    if (-not $byParent.ContainsKey($key)) { $byParent[$key] = @() }
    $byParent[$key] += $p
}
$targets = @{}
$queue = New-Object System.Collections.Queue
$roots | ForEach-Object { $queue.Enqueue($_) }
while ($queue.Count -gt 0) {
    $p = $queue.Dequeue()
    $id = [int]$p.ProcessId
    if ($id -eq $PID -or $targets.ContainsKey($id)) { continue }
    $targets[$id] = $p
    if ($byParent.ContainsKey($id)) { $byParent[$id] | ForEach-Object { $queue.Enqueue($_) } }
}

# The window hosting the app, only if it's the usual "talk here" window.
foreach ($r in $roots) {
    $host_ = $all | Where-Object { $_.ProcessId -eq $r.ParentProcessId -and $_.Name -eq 'powershell.exe' -and $_.CommandLine -match [regex]::Escape($title) }
    $host_ | Where-Object { $_.ProcessId -ne $PID } | ForEach-Object { $targets[[int]$_.ProcessId] = $_ }
}

# Edge windows on the app's own profiles (one may have outlived its parent).
foreach ($p in $all) {
    if ($p.Name -ne 'msedge.exe' -or -not $p.CommandLine) { continue }
    foreach ($prof in $profiles) {
        if ($p.CommandLine.IndexOf($prof, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $targets[[int]$p.ProcessId] = $p }
    }
}

"Stopping $($targets.Count) process(es):"
$targets.Values | Sort-Object ProcessId | ForEach-Object { Show $_ }
foreach ($id in $targets.Keys) {
    try { Stop-Process -Id $id -Force -ErrorAction Stop } catch { "  (couldn't stop $id`: $($_.Exception.Message))" }
}

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    $left = @($targets.Keys | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
} while ($left.Count -gt 0 -and (Get-Date) -lt $deadline)
if ($left.Count -gt 0) {
    "Still running after 20 s: $($left -join ', '). Not relaunching; stop them and launch by hand:"
    "  powershell -NoExit -Command `"$launchCmd`""
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
"All stopped."

Start-Sleep -Seconds 2  # let the temp UI and viewer ports free up
Start-Process powershell -WorkingDirectory $repo -ArgumentList '-NoExit', '-Command', $launchCmd
"Relaunched the app in a new '$title' window: .\.venv\Scripts\python.exe -m assistant (from $repo)."
try { Stop-Transcript | Out-Null } catch {}
