param([int]$Port=8000,[switch]$Background,[switch]$Authenticate)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$ffmpegBin=Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '.tools/ffmpeg') -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ffmpegBin) { $env:PATH=(Join-Path $ffmpegBin.FullName 'bin')+[IO.Path]::PathSeparator+$env:PATH }
if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue) -or !(Get-Command ffprobe -ErrorAction SilentlyContinue)) { throw 'FFmpeg and FFprobe must be on PATH or in .tools/ffmpeg/<build>/bin.' }
$env:PYTHONPATH=(Join-Path $PSScriptRoot '.tools/python')+[IO.Path]::PathSeparator+$env:PYTHONPATH
$env:DATA_DIR=Join-Path $PSScriptRoot 'data'


if ($Authenticate) {
    $credentialPath=Join-Path $PSScriptRoot '.local-auth.json'
    if (Test-Path -LiteralPath $credentialPath) { $credentials=Get-Content -LiteralPath $credentialPath -Raw | ConvertFrom-Json }
    else {
        $random=[byte[]]::new(24)
        [Security.Cryptography.RandomNumberGenerator]::Fill($random)
        $credentials=@{user='creator';password=[Convert]::ToBase64String($random)}
        $credentials | ConvertTo-Json | Set-Content -LiteralPath $credentialPath
    }
    $env:AUTH_USER=$credentials.user
    $env:AUTH_PASSWORD=$credentials.password
    Write-Host 'Authentication enabled. Credentials are in .local-auth.json (gitignored).'
}
if ($Background) {
    New-Item -ItemType Directory -Force -Path logs | Out-Null
    $process=Start-Process -FilePath (Get-Command python).Source -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port",'--workers','1') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'logs/server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'logs/server-error.log') -PassThru
    $process.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'remixora.pid')
    Write-Host "REMIXORA started at http://127.0.0.1:$Port (PID $($process.Id))"
} else { python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1 }
