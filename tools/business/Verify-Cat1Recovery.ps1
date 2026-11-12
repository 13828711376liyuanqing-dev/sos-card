# SAM | 2026-10-20 17:49 +08:00 | Run offline recovery checks and verify the published source set without serial access, device resets or repackaging.
param([string]$PythonPath = 'C:\Users\SamLi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python not found: $PythonPath" }
$taskReportDir = Join-Path $taskRoot 'logs\cat1_recovery_checks'
New-Item -ItemType Directory -Path $taskReportDir -Force | Out-Null
$taskReport = Join-Path $taskReportDir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
Push-Location $taskRoot
try {
    "Offline checks; no serial, flash, power or network operations. $(Get-Date -Format o)" | Set-Content -LiteralPath $taskReport -Encoding utf8
    foreach ($taskTest in @('tools/business/test_sim_recovery.py', 'tools/business/test_cat_business.py', 'tools/ota/test_mqtt_ack.py', 'tools/business/test_gr_business.py')) {
        # Capture stdout/stderr together: unittest reports its result on stderr even on success.
        $taskStart = [System.Diagnostics.ProcessStartInfo]::new()
        $taskStart.FileName = $PythonPath
        $taskStart.Arguments = '"' + (Join-Path $taskRoot $taskTest) + '"'
        $taskStart.WorkingDirectory = $taskRoot
        $taskStart.UseShellExecute = $false
        $taskStart.CreateNoWindow = $true
        $taskStart.RedirectStandardOutput = $true
        $taskStart.RedirectStandardError = $true
        $taskProcess = [System.Diagnostics.Process]::new()
        $taskProcess.StartInfo = $taskStart
        try {
            [void]$taskProcess.Start()
            $taskStdout = $taskProcess.StandardOutput.ReadToEndAsync()
            $taskStderr = $taskProcess.StandardError.ReadToEndAsync()
            $taskProcess.WaitForExit()
            $taskText = $taskTest + [Environment]::NewLine + $taskStdout.Result + $taskStderr.Result
            $taskText | Add-Content -LiteralPath $taskReport -Encoding utf8
            Write-Output $taskText
            if ($taskProcess.ExitCode -ne 0) { throw "Check failed: $taskTest; see $taskReport" }
        } finally { $taskProcess.Dispose() }
    }
    # The manifest verifies source provenance only; it does not read module Flash.
    $taskReady = Get-Content -LiteralPath (Join-Path $taskRoot 'Air780EGH\_luatools_release\latest_ready.json') -Raw | ConvertFrom-Json
    foreach ($taskSourceHash in $taskReady.source_sha256.PSObject.Properties) {
        $taskCurrent = Join-Path (Join-Path $taskRoot 'Air780EGH') $taskSourceHash.Name
        if ((Get-FileHash -LiteralPath $taskCurrent -Algorithm SHA256).Hash -ne $taskSourceHash.Value) { throw "Source differs from published manifest: $($taskSourceHash.Name)" }
    }
    $taskFinal = "PASS offline checks and source manifest; release=$($taskReady.release_directory). Physical SIM hotplug remains unverified."
    $taskFinal | Add-Content -LiteralPath $taskReport -Encoding utf8
    Write-Output $taskFinal
    Write-Output "Report: $taskReport"
} finally { Pop-Location }
