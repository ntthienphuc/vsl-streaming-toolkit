param([string]$Python = "python", [string]$BindAddress = "127.0.0.1", [int]$Port = 8766)
& $Python (Join-Path $PSScriptRoot "host_readiness.py") --serve --host $BindAddress --port $Port
exit $LASTEXITCODE
