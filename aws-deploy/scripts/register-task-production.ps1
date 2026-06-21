# Register production task (RDS + optional Secrets Manager)
param(
    [string]$AccountId,
    [string]$Region = "ap-south-1",
    [ValidateSet("ec2", "fargate")]
    [string]$Launch = "ec2",
    [switch]$UsePlainEnv
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""
$DeployDir = Join-Path $PSScriptRoot ".."
$EnvFile = Join-Path $DeployDir ".env.deploy"
$TaskFile = if ($Launch -eq "fargate") {
    Join-Path $DeployDir "ecs\task-definition.fargate.json"
} else {
    Join-Path $DeployDir "ecs\task-definition.production.json"
}
$OutFile = Join-Path $env:TEMP "rag-task-production.json"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Missing $EnvFile" -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

if (-not $AccountId) {
    $AccountId = $env:AWS_ACCOUNT_ID
    if (-not $AccountId) {
        $AccountId = (aws sts get-caller-identity --query Account --output text)
    }
}

$Rds = $env:RDS_ENDPOINT
if (-not $Rds) {
    Write-Host "Set RDS_ENDPOINT in .env.deploy (run setup-rds.ps1 first)." -ForegroundColor Red
    exit 1
}

$Bucket = $env:S3_UPLOAD_BUCKET
$UploadStorage = if ($Bucket) { "s3" } else { "local" }
if (-not $Bucket) { $Bucket = "" }

$content = Get-Content $TaskFile -Raw
$content = $content -replace "ACCOUNT_ID", $AccountId
$content = $content -replace "ap-south-1", $Region
$content = $content -replace "RDS_ENDPOINT", $Rds
$content = $content -replace "S3_BUCKET_NAME", $Bucket
$content = $content -replace '"UPLOAD_STORAGE", "value": "s3"', "`"UPLOAD_STORAGE`", `"value`": `"$UploadStorage`""

$useSecrets = -not $UsePlainEnv
if ($useSecrets) {
    function Get-SecretArn($Name) {
        aws secretsmanager describe-secret --secret-id $Name --region $Region --query ARN --output text 2>$null
    }
    $arnPg = Get-SecretArn "rag/production/postgres-password"
    if (-not $arnPg) {
        Write-Host "Secrets Manager not available; using plain env from .env.deploy (-UsePlainEnv)" -ForegroundColor Yellow
        $useSecrets = $false
    }
}

$obj = $content | ConvertFrom-Json

if (-not $useSecrets) {
    $backend = $obj.containerDefinitions | Where-Object { $_.name -eq "backend" }
    if ($backend.PSObject.Properties.Name -contains "secrets") {
        $backend.PSObject.Properties.Remove("secrets")
    }
    $extra = @(
        @{ name = "POSTGRES_PASSWORD"; value = $env:POSTGRES_PASSWORD },
        @{ name = "OPENAI_API_KEY"; value = $env:OPENAI_API_KEY },
        @{ name = "SECRET_KEY"; value = $env:SECRET_KEY }
    )
    $backend.environment = @($backend.environment) + $extra
    # task role only needed for S3
    if ($UploadStorage -ne "s3") {
        $obj.PSObject.Properties.Remove("taskRoleArn")
    }
}

if ($useSecrets) {
    function Get-SecretArn($Name) {
        aws secretsmanager describe-secret --secret-id $Name --region $Region --query ARN --output text
    }
    $secretMap = @{
        "arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:rag/production/postgres-password" = (Get-SecretArn "rag/production/postgres-password")
        "arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:rag/production/openai-api-key" = (Get-SecretArn "rag/production/openai-api-key")
        "arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:rag/production/secret-key" = (Get-SecretArn "rag/production/secret-key")
    }
    $json = $obj | ConvertTo-Json -Depth 20
    foreach ($placeholder in $secretMap.Keys) {
        $arn = $secretMap[$placeholder] -replace "ACCOUNT_ID", $AccountId -replace "ap-south-1", $Region
        $json = $json -replace [regex]::Escape($placeholder), $arn
    }
    $content = $json
} else {
    $content = $obj | ConvertTo-Json -Depth 20 -Compress:$false
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($OutFile, $content, $utf8NoBom)

$logGroup = if ($Launch -eq "fargate") { "/ecs/rag-task-fargate" } else { "/ecs/rag-task-prod" }
try { aws logs create-log-group --log-group-name $logGroup --region $Region 2>$null } catch {}

Write-Host "Registering production task ($UploadStorage uploads)..."
$regPath = $OutFile -replace '\\','/'
aws ecs register-task-definition --cli-input-json "file://$regPath"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Task JSON written to $OutFile for debugging" -ForegroundColor Yellow
    exit $LASTEXITCODE
}
