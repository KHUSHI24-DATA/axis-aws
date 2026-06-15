# Attach Secrets Manager read policy to ecsTaskExecutionRole
param(
    [string]$Region = "ap-south-1"
)

$ErrorActionPreference = "Stop"
$DeployDir = Split-Path $PSScriptRoot -Parent
$AccountId = (aws sts get-caller-identity --query Account --output text)

$PolicyFile = Join-Path $DeployDir "iam\ecs-execution-secrets-policy.json"
$policyDoc = (Get-Content $PolicyFile -Raw) -replace "ACCOUNT_ID", $AccountId -replace "ap-south-1", $Region

aws iam put-role-policy `
    --role-name ecsTaskExecutionRole `
    --policy-name ragSecretsManagerRead `
    --policy-document $policyDoc

Write-Host "Attached ragSecretsManagerRead to ecsTaskExecutionRole" -ForegroundColor Green
