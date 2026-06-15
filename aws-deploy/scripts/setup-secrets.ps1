# Create Secrets Manager entries for production ECS (run once per account)
param(
    [string]$Region = "ap-south-1"
)

$ErrorActionPreference = "Stop"
$DeployDir = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $DeployDir ".env.deploy"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Create .env.deploy from .env.deploy.example first." -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$secrets = @{
    "rag/production/openai-api-key" = $env:OPENAI_API_KEY
    "rag/production/secret-key"       = $env:SECRET_KEY
    "rag/production/postgres-password" = $env:POSTGRES_PASSWORD
}

foreach ($name in $secrets.Keys) {
    $value = $secrets[$name]
    if (-not $value) {
        Write-Host "Missing value for $name in .env.deploy" -ForegroundColor Yellow
        continue
    }
    $exists = aws secretsmanager describe-secret --secret-id $name --region $Region 2>$null
    if ($exists) {
        Write-Host "Updating secret: $name" -ForegroundColor Cyan
        aws secretsmanager put-secret-value --secret-id $name --secret-string $value --region $Region | Out-Null
    } else {
        Write-Host "Creating secret: $name" -ForegroundColor Cyan
        aws secretsmanager create-secret --name $name --secret-string $value --region $Region | Out-Null
    }
    $arn = aws secretsmanager describe-secret --secret-id $name --region $Region --query ARN --output text
    Write-Host "  ARN: $arn" -ForegroundColor Green
}

Write-Host ""
Write-Host "Attach ecs-execution-secrets-policy.json to ecsTaskExecutionRole (replace ACCOUNT_ID)." -ForegroundColor Yellow
