# RDS PostgreSQL 16 — full setup via AWS CLI (subnet group + instance + .env.deploy update)
# Prerequisite: IAM user must have RDS permissions (see iam/khushi-rds-policy.json or AmazonRDSFullAccess)
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

$DbId = if ($env:RDS_INSTANCE_ID) { $env:RDS_INSTANCE_ID } else { "rag-postgres" }
$SubnetGroupName = if ($env:RDS_SUBNET_GROUP) { $env:RDS_SUBNET_GROUP } else { "rag-db-subnets" }
$User = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "ragwebui" }
$Password = $env:POSTGRES_PASSWORD
$DbName = if ($env:POSTGRES_DATABASE) { $env:POSTGRES_DATABASE } else { "ragwebui" }
$VpcId = $env:VPC_ID
$EcsSg = "sg-04ffc6a9a1464848e"
$SubnetA = "subnet-0de6b89539c0b2ef4"
$SubnetB = "subnet-0c2ce4d189528a8e6"
$RdsSg = $env:RDS_SECURITY_GROUP_ID

if (-not $Password) {
    Write-Host "Set POSTGRES_PASSWORD in .env.deploy" -ForegroundColor Red
    exit 1
}

function Test-RdsAccess {
    try {
        aws rds describe-db-instances --region $Region --max-items 1 2>$null | Out-Null
        return $true
    } catch {
        return $false
    }
}

$test = aws rds describe-db-engine-versions --engine postgres --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "RDS API AccessDenied for user Khushi." -ForegroundColor Red
    Write-Host ""
    Write-Host "Admin must attach ONE of these to IAM user Khushi, then re-run:" -ForegroundColor Yellow
    Write-Host "  - AWS managed: AmazonRDSFullAccess" -ForegroundColor Yellow
    Write-Host "  - Or custom: aws-deploy/iam/khushi-rds-policy.json" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or run this script logged in as root/admin:" -ForegroundColor Yellow
    Write-Host "  aws configure   # use admin access keys" -ForegroundColor Cyan
    Write-Host "  .\aws-deploy\scripts\setup-rds.ps1" -ForegroundColor Cyan
    exit 1
}

# --- RDS security group (5432 from ECS EC2) ---
if (-not $RdsSg) {
    if (-not $VpcId) {
        $VpcId = "vpc-0c0c7b068e851bdf5"
    }
    $RdsSg = aws ec2 create-security-group `
        --group-name "rag-rds-sg" `
        --description "RDS Postgres for RAG" `
        --vpc-id $VpcId `
        --region $Region `
        --query GroupId --output text 2>$null
    if (-not $RdsSg) {
        $RdsSg = aws ec2 describe-security-groups `
            --filters "Name=group-name,Values=rag-rds-sg" "Name=vpc-id,Values=$VpcId" `
            --region $Region --query "SecurityGroups[0].GroupId" --output text
    }
    aws ec2 authorize-security-group-ingress `
        --group-id $RdsSg --protocol tcp --port 5432 `
        --source-group $EcsSg --region $Region 2>$null
    Write-Host "RDS security group: $RdsSg" -ForegroundColor Green
}

# --- DB subnet group (2 AZs) ---
$sgExists = $false
try {
    aws rds describe-db-subnet-groups --db-subnet-group-name $SubnetGroupName --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $sgExists = $true }
} catch { $sgExists = $false }
if (-not $sgExists) {
    Write-Host "Creating DB subnet group $SubnetGroupName ..." -ForegroundColor Cyan
    aws rds create-db-subnet-group `
        --db-subnet-group-name $SubnetGroupName `
        --db-subnet-group-description "RAG RDS subnets" `
        --subnet-ids $SubnetA $SubnetB `
        --region $Region | Out-Null
    Write-Host "Subnet group created." -ForegroundColor Green
} else {
    Write-Host "Subnet group $SubnetGroupName already exists." -ForegroundColor Green
}

# --- DB instance ---
$exists = aws rds describe-db-instances --db-instance-identifier $DbId --region $Region 2>$null
if ($exists) {
    Write-Host "RDS $DbId already exists." -ForegroundColor Green
} else {
    Write-Host "Creating RDS $DbId (10-15 min)..." -ForegroundColor Cyan
    aws rds create-db-instance `
        --db-instance-identifier $DbId `
        --db-instance-class db.t3.micro `
        --engine postgres `
        --engine-version 16.9 `
        --master-username $User `
        --master-user-password $Password `
        --allocated-storage 20 `
        --db-name $DbName `
        --vpc-security-group-ids $RdsSg `
        --db-subnet-group-name $SubnetGroupName `
        --backup-retention-period 1 `
        --storage-encrypted `
        --no-publicly-accessible `
        --region $Region | Out-Null
}

Write-Host "Waiting for RDS Available..." -ForegroundColor Cyan
aws rds wait db-instance-available --db-instance-identifier $DbId --region $Region

$endpoint = aws rds describe-db-instances `
    --db-instance-identifier $DbId --region $Region `
    --query "DBInstances[0].Endpoint.Address" --output text

Write-Host ""
Write-Host "RDS endpoint: $endpoint" -ForegroundColor Green

# Update .env.deploy RDS_ENDPOINT line
$lines = Get-Content $EnvFile
$updated = $false
$newLines = foreach ($line in $lines) {
    if ($line -match '^\s*RDS_ENDPOINT=') {
        $updated = $true
        "RDS_ENDPOINT=$endpoint"
    } else {
        $line
    }
}
if (-not $updated) {
    $newLines += "RDS_ENDPOINT=$endpoint"
}
if ($newLines -notmatch 'RDS_SECURITY_GROUP_ID=') {
    $newLines += "RDS_SECURITY_GROUP_ID=$RdsSg"
}
Set-Content -Path $EnvFile -Value $newLines -Encoding UTF8

Write-Host "Updated $EnvFile with RDS_ENDPOINT" -ForegroundColor Green
Write-Host ""
Write-Host "pgvector: backend entrypoint runs CREATE EXTENSION on first deploy." -ForegroundColor Cyan
Write-Host "Next: .\aws-deploy\scripts\register-task-production.ps1" -ForegroundColor Cyan
Write-Host "       .\aws-deploy\scripts\deploy-production.ps1" -ForegroundColor Cyan
