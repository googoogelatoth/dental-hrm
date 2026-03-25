param(
    [Parameter(Mandatory = $true)]
    [string]$SqlFilePath,

    [Parameter(Mandatory = $true)]
    [string]$DbHost,

    [Parameter(Mandatory = $true)]
    [int]$DbPort,

    [Parameter(Mandatory = $true)]
    [string]$DbName,

    [Parameter(Mandatory = $true)]
    [pscredential]$DbCredential
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SqlFilePath)) {
    throw "SQL file not found: $SqlFilePath"
}

$workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DbCredential.Password)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$env:PGPASSWORD = $plainPassword
$env:DATABASE_URL = "postgresql://$($DbCredential.UserName)`:$plainPassword@$DbHost`:$DbPort/$DbName"

Write-Host "[1/3] Restoring backup to PostgreSQL..."
psql -h $DbHost -p $DbPort -U $DbCredential.UserName -d $DbName -f $SqlFilePath

Write-Host "[2/3] Applying latest Alembic migrations..."
& $pythonExe -m alembic upgrade head

Write-Host "[3/3] Done. Verify app env vars (DATABASE_URL, APP_STORAGE_ROOT, VAPID_*) and restart service."
