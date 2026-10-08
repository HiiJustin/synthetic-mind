$ErrorActionPreference = 'Stop'
$priorPath = $env:PYTHONPATH
Push-Location -LiteralPath $PSScriptRoot
try {
    $env:PYTHONPATH = (Join-Path $PSScriptRoot 'src') + [IO.Path]::PathSeparator + $priorPath
    & python -B -m synthetic_mind @args
    $resultCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $priorPath
    Pop-Location
}
exit $resultCode
