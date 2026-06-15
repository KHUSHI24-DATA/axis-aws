# ALB for ECS Fargate (target-type ip). HTTP always; HTTPS if ACM_CERT_ARN is set in .env.deploy
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

$VpcId = $env:VPC_ID
$Subnets = $env:ALB_SUBNET_IDS
if (-not $Subnets) {
    $Subnets = "subnet-0de6b89539c0b2ef4,subnet-0c2ce4d189528a8e6"
}

if (-not $VpcId) {
    Write-Host "VPC_ID required in .env.deploy" -ForegroundColor Red
    exit 1
}

$subnetList = ($Subnets -split ",") | ForEach-Object { $_.Trim() }
$AlbName = "rag-alb"
$TgName = "rag-fargate-tg"

function Get-OrCreate-Sg($Name, $Description) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $sg = aws ec2 create-security-group --group-name $Name --description $Description --vpc-id $VpcId --region $Region --query GroupId --output text 2>$null
    if (-not $sg -or $sg -eq "None") {
        $sg = aws ec2 describe-security-groups --filters "Name=group-name,Values=$Name" "Name=vpc-id,Values=$VpcId" --region $Region --query "SecurityGroups[0].GroupId" --output text
    }
    $ErrorActionPreference = $prev
    return $sg
}

Write-Host "Creating security groups..." -ForegroundColor Cyan
$AlbSg = Get-OrCreate-Sg "rag-alb-sg" "RAG ALB HTTP/HTTPS"
$FargateSg = Get-OrCreate-Sg "rag-fargate-sg" "RAG Fargate ECS tasks"

$ErrorActionPreference = "SilentlyContinue"
aws ec2 authorize-security-group-ingress --group-id $AlbSg --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $Region 2>$null | Out-Null
aws ec2 authorize-security-group-ingress --group-id $AlbSg --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $Region 2>$null | Out-Null
aws ec2 authorize-security-group-ingress --group-id $FargateSg --protocol tcp --port 3000 --source-group $AlbSg --region $Region 2>$null | Out-Null
$ErrorActionPreference = "Stop"

# RDS: allow Fargate tasks on 5432
$RdsSg = $env:RDS_SECURITY_GROUP_ID
if ($RdsSg) {
    $ErrorActionPreference = "SilentlyContinue"
    aws ec2 authorize-security-group-ingress --group-id $RdsSg --protocol tcp --port 5432 --source-group $FargateSg --region $Region 2>$null | Out-Null
    $ErrorActionPreference = "Stop"
    Write-Host "RDS SG $RdsSg allows rag-fargate-sg on 5432" -ForegroundColor Green
}

Write-Host "Creating ALB $AlbName ..." -ForegroundColor Cyan
$AlbArn = aws elbv2 create-load-balancer --name $AlbName --subnets $subnetList --security-groups $AlbSg --scheme internet-facing --type application --region $Region --query "LoadBalancers[0].LoadBalancerArn" --output text 2>$null
if (-not $AlbArn -or $AlbArn -eq "None") {
    $AlbArn = aws elbv2 describe-load-balancers --names $AlbName --region $Region --query "LoadBalancers[0].LoadBalancerArn" --output text
}

$TgArn = aws elbv2 create-target-group `
    --name $TgName `
    --protocol HTTP `
    --port 3000 `
    --vpc-id $VpcId `
    --target-type ip `
    --health-check-path "/" `
    --health-check-interval-seconds 30 `
    --healthy-threshold-count 2 `
    --unhealthy-threshold-count 3 `
    --region $Region `
    --query "TargetGroups[0].TargetGroupArn" --output text 2>$null
if (-not $TgArn -or $TgArn -eq "None") {
    $TgArn = aws elbv2 describe-target-groups --names $TgName --region $Region --query "TargetGroups[0].TargetGroupArn" --output text
}

# HTTP listener
$listeners = aws elbv2 describe-listeners --load-balancer-arn $AlbArn --region $Region --output json | ConvertFrom-Json
$hasHttp = $listeners.Listeners | Where-Object { $_.Port -eq 80 }
if (-not $hasHttp) {
    aws elbv2 create-listener --load-balancer-arn $AlbArn --protocol HTTP --port 80 --default-actions "Type=forward,TargetGroupArn=$TgArn" --region $Region | Out-Null
    Write-Host "HTTP listener on port 80 created." -ForegroundColor Green
}

# HTTPS listener (optional)
if ($env:ACM_CERT_ARN) {
    $hasHttps = $listeners.Listeners | Where-Object { $_.Port -eq 443 }
    if (-not $hasHttps) {
        aws elbv2 create-listener --load-balancer-arn $AlbArn --protocol HTTPS --port 443 --certificates "CertificateArn=$($env:ACM_CERT_ARN)" --default-actions "Type=forward,TargetGroupArn=$TgArn" --region $Region | Out-Null
        Write-Host "HTTPS listener on port 443 created." -ForegroundColor Green
    }
} else {
    Write-Host "ACM_CERT_ARN not set - HTTP only. Add cert later for HTTPS." -ForegroundColor Yellow
}

$Dns = aws elbv2 describe-load-balancers --load-balancer-arns $AlbArn --region $Region --query "LoadBalancers[0].DNSName" --output text

# Persist ARNs for deploy script
$lines = Get-Content $EnvFile | Where-Object { $_ -notmatch '^(ALB_ARN|ALB_TARGET_GROUP_ARN|FARGATE_SECURITY_GROUP_ID|ALB_SUBNET_IDS)=' }
$lines += "ALB_SUBNET_IDS=$Subnets"
$lines += "ALB_ARN=$AlbArn"
$lines += "ALB_TARGET_GROUP_ARN=$TgArn"
$lines += "FARGATE_SECURITY_GROUP_ID=$FargateSg"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($EnvFile, ($lines -join "`r`n") + "`r`n", $utf8NoBom)

Write-Host ""
Write-Host "ALB DNS: http://$Dns" -ForegroundColor Green
Write-Host "Target group: $TgArn" -ForegroundColor Green
Write-Host "Fargate SG: $FargateSg" -ForegroundColor Green
if ($env:DOMAIN_NAME) {
    Write-Host "When ready: Route 53 A-alias $($env:DOMAIN_NAME) to ALB $AlbName" -ForegroundColor Cyan
}
