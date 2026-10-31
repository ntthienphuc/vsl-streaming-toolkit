[CmdletBinding(DefaultParameterSetName = 'Start')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Start')][string]$Bundle,
    [Parameter(ParameterSetName = 'Start')][string]$Config,
    [Parameter(ParameterSetName = 'Start')][string]$Python = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'),
    [Parameter(ParameterSetName = 'Start')][string]$OutputDir,
    [Parameter(ParameterSetName = 'Start')][string]$PoseModel = (Join-Path $PSScriptRoot '../clients/android/app/src/main/assets/pose_landmarker_lite.task'),
    [Parameter(ParameterSetName = 'Start')][string]$HandModel = (Join-Path $PSScriptRoot '../clients/android/app/src/main/assets/hand_landmarker.task'),
    [Parameter(ParameterSetName = 'Start')][string]$Adb = (Join-Path $env:LOCALAPPDATA 'Android/Sdk/platform-tools/adb.exe'),
    [Parameter(ParameterSetName = 'Start')][string]$DeviceSerial,
    [Parameter(ParameterSetName = 'Start')][switch]$Phone,
    [Parameter(Mandatory, ParameterSetName = 'Stop')][string]$StopManifest
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
function Quote-Argument([string]$Value) {
    '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
function Process-Record($Process, [string]$Role) {
    [pscustomobject]@{ id = [int]$Process.ProcessId; parent_id = [int]$Process.ParentProcessId; role = $Role
        created_utc = $Process.CreationDate.ToUniversalTime().ToString('o')
        executable = $Process.ExecutablePath; command_line = $Process.CommandLine }
}
function Same-Process($Record) {
    $found = Get-CimInstance Win32_Process -Filter "ProcessId = $($Record.id)"
    # PowerShell 7 can deserialize ISO JSON timestamps as DateTime; compare time,
    # not formatted strings, while retaining the executable and command checks.
    $recordedTime = if ($Record.created_utc -is [DateTime]) {
        $Record.created_utc.ToUniversalTime()
    } else {
        [DateTimeOffset]::Parse([string]$Record.created_utc, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
    }
    if ($found -and $found.CreationDate.ToUniversalTime().Ticks -eq $recordedTime.Ticks -and
        $found.ExecutablePath -eq $Record.executable -and $found.CommandLine -ceq $Record.command_line) { return $found }
    return $null
}
function Capture-Families($Manifest) {
    foreach ($record in @($Manifest.processes)) {
        if (-not (Same-Process $record)) { continue }
        foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($record.id)")) {
            if ($child.CommandLine -and $child.CommandLine.Contains($Manifest.output_dir) -and
                [IO.Path]::GetFileName($child.ExecutablePath) -eq 'python.exe' -and
                -not @($Manifest.processes | Where-Object { $_.id -eq $child.ProcessId }).Count) {
                $Manifest.processes += Process-Record $child $record.role
            }
        }
    }
}
function Stop-Owned($Manifest) {
    Capture-Families $Manifest
    $stopped = @(); $removed = @(); $skipped = @()
    foreach ($record in @($Manifest.processes | Sort-Object id -Descending)) {
        if ((Same-Process $record) -and $record.command_line.Contains($Manifest.output_dir)) {
            Stop-Process -Id $record.id -ErrorAction SilentlyContinue
            $stopped += $record.id
        } else { $skipped += $record.id }
    }
    if ($Manifest.adb -and $Manifest.device_serial) {
        foreach ($port in @($Manifest.owned_forwards)) {
            $lines = @(& $Manifest.adb -s $Manifest.device_serial reverse --list 2>&1)
            if ($LASTEXITCODE -ne 0) { Write-Warning 'Phone unavailable; its owned USB forwards could not be removed.'; break }
            if (@($lines | Where-Object { $_ -match "\s+tcp:$port\s+tcp:$port\s*$" }).Count) {
                & $Manifest.adb -s $Manifest.device_serial reverse --remove "tcp:$port" | Out-Null
                if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove owned USB port $port."; continue }
                $removed += $port
            }
            $Manifest.owned_forwards = @($Manifest.owned_forwards | Where-Object { $_ -ne $port })
        }
    }
    [pscustomobject]@{ stopped_pids = $stopped; skipped_pids = $skipped; removed_forwards = $removed }
}
function Save-Manifest($Manifest, [string]$Path) {
    [IO.File]::WriteAllText($Path, ($Manifest | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}
if ($PSCmdlet.ParameterSetName -eq 'Stop') {
    $manifest = Get-Content -LiteralPath $StopManifest -Raw | ConvertFrom-Json
    if ($manifest.kind -ne 'vsl-flutter-demo-v1' -or -not [IO.Path]::IsPathRooted($manifest.output_dir)) { throw 'Not a VSL launcher manifest.' }
    $cleanup = Stop-Owned $manifest
    $manifest.state = 'stopped'
    Save-Manifest $manifest ((Resolve-Path -LiteralPath $StopManifest).Path)
    $cleanup | ConvertTo-Json -Depth 5
    return
}
# Resolve and preflight before creating files, processes, or phone forwards.
$Python = (Resolve-Path -LiteralPath $Python).Path
$Bundle = (Resolve-Path -LiteralPath $Bundle).Path
$PoseModel = (Resolve-Path -LiteralPath $PoseModel).Path
$HandModel = (Resolve-Path -LiteralPath $HandModel).Path
if ($Config) { $Config = (Resolve-Path -LiteralPath $Config).Path }
foreach ($port in @(18081, 18082)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is occupied. Existing processes were left running." }
}
if ($Phone) {
    $Adb = (Resolve-Path -LiteralPath $Adb).Path
    $devices = @(& $Adb devices)
    if ($LASTEXITCODE -ne 0) { throw 'ADB device enumeration failed.' }
    $online = @($devices | Where-Object { $_ -match '^\S+\s+device\s*$' } | ForEach-Object { ($_ -split '\s+')[0] })
    if (-not $DeviceSerial -and $online.Count -eq 1) { $DeviceSerial = $online[0] }
    if (-not $DeviceSerial -or $online -notcontains $DeviceSerial) { throw 'Use -DeviceSerial for one authorized, online phone.' }
    $package = & $Adb -s $DeviceSerial shell pm path org.vslstream.flutterdemo
    if ($LASTEXITCODE -ne 0 -or -not ($package -match '^package:')) { throw 'Install the Flutter demo APK before using -Phone.' }
}
if (-not $OutputDir) { $OutputDir = Join-Path $repo ('artifacts/flutter-demo/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')) }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw 'OutputDir must be new; existing evidence is never overwritten.' }
[IO.Directory]::CreateDirectory($OutputDir) | Out-Null
$manifestPath = Join-Path $OutputDir 'launcher.json'
$manifest = [pscustomobject]@{ kind = 'vsl-flutter-demo-v1'; state = 'starting'; output_dir = $OutputDir
    started_utc = [DateTime]::UtcNow.ToString('o'); bundle = $Bundle; config = $Config
    websocket = 'ws://127.0.0.1:18081/v1/stream'; video = 'http://127.0.0.1:18082'
    adb = $(if ($Phone) { $Adb } else { $null }); device_serial = $DeviceSerial; owned_forwards = @(); processes = @() }
Save-Manifest $manifest $manifestPath
try {
    $shared = @('--bundle', $Bundle)
    if ($Config) { $shared += @('--config', $Config) }
    $commands = @(
        @{ role = 'websocket'; args = @('-m', 'vsl_streaming.cli', 'serve') + $shared + @('--host', '127.0.0.1', '--port', '18081', '--session-log-dir', (Join-Path $OutputDir 'session-logs')) },
        @{ role = 'video'; args = @((Join-Path $repo 'tools/serve_video_demo.py')) + $shared + @('--pose-model', $PoseModel, '--hand-model', $HandModel, '--output-dir', (Join-Path $OutputDir 'video-runs'), '--host', '127.0.0.1', '--port', '18082') }
    )
    foreach ($command in $commands) {
        $arguments = ($command.args | ForEach-Object { Quote-Argument $_ }) -join ' '
        $process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $OutputDir ($command.role + '-stdout.log')) -RedirectStandardError (Join-Path $OutputDir ($command.role + '-stderr.log'))
        $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
        if (-not $identity) { throw "$($command.role) exited before its process identity could be recorded; inspect stderr." }
        $manifest.processes += Process-Record $identity $command.role
        Capture-Families $manifest
        Save-Manifest $manifest $manifestPath
    }
    Add-Type -AssemblyName System.Net.Http
    $http = [Net.Http.HttpClient]::new()
    $timer = [Diagnostics.Stopwatch]::StartNew(); $ready = $false
    while ($timer.Elapsed.TotalSeconds -lt 15 -and -not $ready) {
        Capture-Families $manifest
        try {
            $health = @()
            foreach ($port in @(18081, 18082)) {
                $remaining = [int][Math]::Max(1, [Math]::Min(1000, 15000 - $timer.ElapsedMilliseconds))
                $cancel = [Threading.CancellationTokenSource]::new($remaining)
                try {
                    $response = $http.GetAsync("http://127.0.0.1:$port/health", $cancel.Token).GetAwaiter().GetResult()
                    $response.EnsureSuccessStatusCode() | Out-Null
                    $health += $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
                    $response.Dispose()
                } finally { $cancel.Dispose() }
            }
            $ready = @($health | Where-Object { $_.status -ne 'ready' }).Count -eq 0
        } catch { if ($timer.ElapsedMilliseconds -lt 14750) { Start-Sleep -Milliseconds 250 } }
    }
    $http.Dispose()
    if (-not $ready) { throw 'Servers did not become ready within 15 seconds; inspect their stderr logs.' }
    foreach ($port in @(18081, 18082)) {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen)
        if (@($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' -or $_.OwningProcess -notin $manifest.processes.id }).Count) { throw "Port $port is not owned by the recorded loopback server." }
    }
    if ($Phone) {
        foreach ($port in @(18081, 18082)) {
            $existing = @(& $Adb -s $DeviceSerial reverse --list)
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect USB forwarding.' }
            $matches = @($existing | Where-Object { $_ -match "\s+tcp:$port\s+" })
            if ($matches.Count -eq 0) {
                & $Adb -s $DeviceSerial reverse --no-rebind "tcp:$port" "tcp:$port" | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Could not create USB forwarding for $port." }
                $manifest.owned_forwards += $port
                Save-Manifest $manifest $manifestPath
            } elseif (-not @($matches | Where-Object { $_ -match "\s+tcp:$port\s+tcp:$port\s*$" }).Count) { throw "USB port $port already has a different mapping." }
        }
        & $Adb -s $DeviceSerial shell am start -n org.vslstream.flutterdemo/.MainActivity | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not open the Flutter demo.' }
    }
    $manifest.state = 'ready'
    Save-Manifest $manifest $manifestPath
    Write-Output "Ready. Live: $($manifest.websocket) | Video: $($manifest.video)"
    Write-Output "Manifest: $manifestPath"
    Write-Output "Stop: & '$PSCommandPath' -StopManifest '$manifestPath'"
} catch {
    $manifest.state = 'failed'
    $manifest | Add-Member -NotePropertyName failure -NotePropertyValue $_.Exception.Message
    $manifest | Add-Member -NotePropertyName cleanup -NotePropertyValue (Stop-Owned $manifest)
    Save-Manifest $manifest $manifestPath
    throw
}
