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
$failedPolls = 0
foreach ($entry in $watch.jobs) {
    $job = [string]$entry.job
    $jobName = [string]$entry.name
    $remoteLog = [string]$entry.log
    try {
        $raw = & ssh @sshBase "sacct -j $job --format=JobID,State,ExitCode,Elapsed -P -n" 2>$null
    } catch { $raw = $null }
    if (-not $raw) {
        $failedPolls += 1
        Append-Json @{ event = "poll_failed"; job = $job; timestamp = (Get-Date).ToString("o") }
        continue
    }
    $first = ($raw | Where-Object { $_ -match "^\d+" } | Select-Object -First 1)
    if (-not $first) {
        $failedPolls += 1
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
} elseif ($failedPolls -gt 0) {
    # A failed poll is unknown state, never a clean bill of health: keep any
    # existing alert untouched, and after repeated failures announce blindness.
    if (Test-Path $logPath) {
        $recent = Get-Content $logPath -Tail 8 | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } }
        $consecutive = 0
        for ($i = $recent.Count - 1; $i -ge 0; $i--) {
            if ($recent[$i].event -eq "poll_failed") { $consecutive += 1 } else { break }
        }
        if ($consecutive -ge 3) {
            $body = @("# Sol monitor alert", "",
                "Raised: $((Get-Date).ToString('o'))", "",
                "## Monitor cannot reach Sol ($consecutive consecutive failed polls)",
                "",
                "The cluster SSH endpoint is not answering. Watched jobs may have ended unseen.",
                "Action: retry `ssh psheta12@sol.asu.edu` and run the playbook from monitor.jsonl's last known states.",
                "")
            [IO.File]::WriteAllText($alertPath, ($body -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
        }
    }
} elseif (Test-Path $alertPath) {
    # Every job was polled successfully and none needs attention: clear.
    Remove-Item $alertPath
}
