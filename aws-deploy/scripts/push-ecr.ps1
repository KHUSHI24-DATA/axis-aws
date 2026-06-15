# Build and push rag-web-ui images to ECR (Windows PowerShell)
# Usage:
#   1. Copy aws-deploy\.env.deploy.example to aws-deploy\.env.deploy and set AWS_ACCOUNT_ID
#   2. aws configure   (once)
#   3. .\aws-deploy\scripts\push-ecr.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$DeployDir = Join-Path $RepoRoot "aws-deploy"
$EnvFile = Join-Path $DeployDir ".env.deploy"
$AppDir = Join-Path $RepoRoot "rag-web-ui"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Create $EnvFile from .env.deploy.example and set AWS_ACCOUNT_ID + AWS_REGION" -ForegroundColor Yellow
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }
$AccountId = $env:AWS_ACCOUNT_ID
if (-not $AccountId) {
    Write-Host "AWS_ACCOUNT_ID missing in .env.deploy" -ForegroundColor Red
    exit 1
}

$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"

Write-Host "Logging in to ECR ($Registry)..." -ForegroundColor Cyan
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $Registry

foreach ($repo in @("rag-backend", "rag-frontend")) {
    $exists = aws ecr describe-repositories --repository-names $repo --region $Region 2>$null
    if (-not $exists) {
        Write-Host "Creating ECR repo: $repo" -ForegroundColor Cyan
        aws ecr create-repository --repository-name $repo --region $Region | Out-Null
    }
}

Write-Host "Building backend..." -ForegroundColor Cyan
docker build -t rag-backend "$AppDir\backend"
docker tag rag-backend:latest "${Registry}/rag-backend:latest"
docker push "${Registry}/rag-backend:latest"

Write-Host "Building frontend..." -ForegroundColor Cyan
docker build -t rag-frontend "$AppDir\frontend"
docker tag rag-frontend:latest "${Registry}/rag-frontend:latest"
docker push "${Registry}/rag-frontend:latest"

Write-Host "Done. Images:" -ForegroundColor Green
Write-Host "  ${Registry}/rag-backend:latest"
Write-Host "  ${Registry}/rag-frontend:latest"
