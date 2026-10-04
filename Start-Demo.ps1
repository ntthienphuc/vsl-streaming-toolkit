param([string]$Python = "python", [string]$Output = "demo_run", [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create virtual environment." }
}
& ./.venv/Scripts/python.exe -m pip install ".[server,export]"
if ($LASTEXITCODE -ne 0) { throw "Could not install toolkit dependencies." }
if (-not (Test-Path -LiteralPath $Output)) {
    & ./.venv/Scripts/vsl-stream.exe demo --out $Output
    if ($LASTEXITCODE -ne 0) { throw "Demo generation failed." }
}
& ./.venv/Scripts/vsl-stream.exe inspect --bundle "$Output/bundle"
if ($LASTEXITCODE -ne 0) { throw "Demo bundle is invalid." }
Write-Host "Open http://127.0.0.1:$Port/ and select $Output/frames.json"
& ./.venv/Scripts/vsl-stream.exe serve --bundle "$Output/bundle" --config "$Output/server.json" --port $Port
if ($LASTEXITCODE -ne 0) { throw "Server failed." }
