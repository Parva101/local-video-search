# Monitors Sol jobs listed in .codex-backups/sol-monitor/watch.json.
# Intended to run every 10 minutes from Windows Task Scheduler and manually.
# Appends one JSONL line per poll and writes ALERT.md whenever a watched job
# reaches a state that needs attention (FAILED, COMPLETED, or unknown).

$ErrorActionPreference = "Continue"
$workspace = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$monitorDir = Join-Path $workspace ".codex-backups\sol-monitor"
$watchPath = Join-Path $monitorDir "watch.json"
$logPath = Join-Path $monitorDir "monitor.jsonl"
$alertPath = Join-Path $monitorDir "ALERT.md"
$key = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$sshBase = @("-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=20", "-i", $key, "psheta12@sol.asu.edu")

New-Item -ItemType Directory -Force $monitorDir | Out-Null
if (-not (Test-Path $watchPath)) { exit 0 }

function Append-Json($obj) {
    $line = $obj | ConvertTo-Json -Compress -Depth 5
    [IO.File]::AppendAllText($logPath, $line + "`n")
}

try { $watch = Get-Content $watchPath -Raw | ConvertFrom-Json } catch { Append-Json @{ event = "watch_file_invalid" }; exit 1 }

$attention = @()
foreach ($entry in $watch.jobs) {
    $job = [string]$entry.job
    $jobName = [string]$entry.name
    $remoteLog = [string]$entry.log
    try {
        $raw = & ssh @sshBase "sacct -j $job --format=JobID,State,ExitCode,Elapsed -P -n" 2>$null
    } catch { $raw = $null }
    if (-not $raw) {
        Append-Json @{ event = "poll_failed"; job = $job; timestamp = (Get-Date).ToString("o") }
        continue
    }
    $first = ($raw | Where-Object { $_ -match "^\d+" } | Select-Object -First 1)
    if (-not $first) {
        Append-Json @{ event = "poll_failed"; job = $job; timestamp = (Get-Date).ToString("o") }
        continue
    }
    $parts = $first -split "\|"
    $state = $parts[1]
    $exitCode = $parts[2]
    $elapsed = $parts[3]
    Append-Json @{ event = "poll"; job = $job; name = $jobName; state = $state; exit_code = $exitCode; elapsed = $elapsed; timestamp = (Get-Date).ToString("o") }
    if ($state -in @("FAILED", "TIMEOUT", "CANCELLED", "COMPLETED", "OUT_OF_MEMORY", "NODE_FAIL")) {
        $detail = ""
        if ($remoteLog) {
            try { $detail = (& ssh @sshBase "tail -n 40 /scratch/psheta12/video-search-finetune-20261120/$remoteLog" 2>$null) -join "`n" } catch { $detail = "" }
        }
        $attention += [pscustomobject]@{ job = $job; name = $jobName; state = $state; exit_code = $exitCode; elapsed = $elapsed; detail = $detail }
    }
}

if ($attention.Count -gt 0) {
    $body = @("# Sol monitor alert", "")
    $body += "Raised: $((Get-Date).ToString('o'))"
    $body += ""
    foreach ($item in $attention) {
        $body += "## Job $($item.job) ($($item.name)) is $($item.state) (exit $($item.exit_code), elapsed $($item.elapsed))"
        if ($item.detail) { $body += ""; $body += "Log tail:"; $body += '```'; $body += $item.detail; $body += '```' }
        $body += ""
    }
    $body += "Action for any session reading this: diagnose from the log tail, fix the cause, and record the outcome in PLAN.md before resubmitting anything. Honor the two-failure rule."
    [IO.File]::WriteAllText($alertPath, ($body -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
} elseif (Test-Path $alertPath) {
    Remove-Item $alertPath
}
