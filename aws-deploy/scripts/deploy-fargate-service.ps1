# Deploy RAG on ECS Fargate behind ALB (run setup-alb-fargate.ps1 first)
param(
    [string]$Region = "ap-south-1",
    [string]$Cluster = "rag-cluster",
    [string]$Service = "rag-service-fargate",
    [string]$Ec2Service = "rag-service",
    [switch]$SkipPush,
    [switch]$KeepEc2Service
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""
$Scripts = $PSScriptRoot
$DeployDir = Split-Path $Scripts -Parent
$EnvFile = Join-Path $DeployDir ".env.deploy"

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$TgArn = $env:ALB_TARGET_GROUP_ARN
$FargateSg = $env:FARGATE_SECURITY_GROUP_ID
$Subnets = $env:ALB_SUBNET_IDS
if (-not $Subnets) {
    $Subnets = "subnet-0de6b89539c0b2ef4,subnet-0c2ce4d189528a8e6"
}

if (-not $TgArn -or -not $FargateSg) {
    Write-Host "Run .\setup-alb-fargate.ps1 first (ALB_TARGET_GROUP_ARN / FARGATE_SECURITY_GROUP_ID missing)." -ForegroundColor Red
    exit 1
}

$subnetList = ($Subnets -split ",") | ForEach-Object { $_.Trim() }

if (-not $SkipPush) {
    & "$Scripts\push-ecr.ps1"
}

& "$Scripts\register-task-production.ps1" -Region $Region -Launch fargate -UsePlainEnv

$Family = "rag-task-fargate"
$Rev = aws ecs describe-task-definition --task-definition $Family --region $Region --query "taskDefinition.revision" --output text
$TaskDef = "$Family`:$Rev"

Write-Host "Stopping EC2 service $Ec2Service (free cluster capacity)..." -ForegroundColor Cyan
aws ecs update-service --cluster $Cluster --service $Ec2Service --desired-count 0 --region $Region 2>$null | Out-Null
Start-Sleep -Seconds 15
$oldTasks = aws ecs list-tasks --cluster $Cluster --service-name $Ec2Service --region $Region --query "taskArns" --output json 2>$null | ConvertFrom-Json
foreach ($t in $oldTasks) {
    if ($t) { aws ecs stop-task --cluster $Cluster --task $t --region $Region | Out-Null }
}
Start-Sleep -Seconds 20

$existing = aws ecs describe-services --cluster $Cluster --services $Service --region $Region --query "services[0].status" --output text 2>$null
if ($existing -eq "ACTIVE") {
    Write-Host "Updating existing Fargate service $Service ..." -ForegroundColor Cyan
    aws ecs update-service `
        --cluster $Cluster `
        --service $Service `
        --task-definition $TaskDef `
        --desired-count 1 `
        --force-new-deployment `
        --region $Region | Out-Null
} else {
    Write-Host "Creating Fargate service $Service ..." -ForegroundColor Cyan
    $netJson = @{
        awsvpcConfiguration = @{
            subnets = $subnetList
            securityGroups = @($FargateSg)
            assignPublicIp = "ENABLED"
        }
    } | ConvertTo-Json -Compress
    $netFile = Join-Path $env:TEMP "rag-fargate-network.json"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($netFile, $netJson, $utf8NoBom)
    $netPath = $netFile -replace '\\', '/'
    aws ecs create-service `
        --cluster $Cluster `
        --service-name $Service `
        --task-definition $TaskDef `
        --desired-count 1 `
        --launch-type FARGATE `
        --network-configuration "file://$netPath" `
        --load-balancers "targetGroupArn=$TgArn,containerName=frontend,containerPort=3000" `
        --health-check-grace-period-seconds 120 `
        --region $Region | Out-Null
}

if (-not $KeepEc2Service) {
    Write-Host "EC2 service $Ec2Service left at desired-count 0." -ForegroundColor Yellow
}

$AlbDns = aws elbv2 describe-load-balancers --load-balancer-arns $env:ALB_ARN --region $Region --query "LoadBalancers[0].DNSName" --output text 2>$null
Write-Host ""
Write-Host "Deployed $TaskDef on Fargate. Wait 3-5 min for targets healthy." -ForegroundColor Green
Write-Host "Open: http://$AlbDns" -ForegroundColor Green
if ($env:DOMAIN_NAME -and $env:ACM_CERT_ARN) {
    Write-Host "HTTPS: https://$($env:DOMAIN_NAME) (after Route 53 alias to ALB)" -ForegroundColor Cyan
}
