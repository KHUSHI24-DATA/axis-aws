# Verify AWS deploy status from terminal
# Usage:  .\aws-deploy\scripts\check-deploy.ps1

$ErrorActionPreference = "Continue"
$DeployDir = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $DeployDir ".env.deploy"
$Region = "ap-south-1"
$Cluster = "rag-cluster"
$Service = "rag-service-fargate"
$TaskFamily = "rag-task-fargate"
$LogGroup = "/ecs/rag-task-fargate"
$AlbName = "rag-alb"

function Load-DeployEnv {
    if (Test-Path $EnvFile) {
        Get-Content $EnvFile | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
            }
        }
        if ($env:AWS_REGION) { $script:Region = $env:AWS_REGION }
    }
}

function Write-Status($Label, $Ok, $Detail = "") {
    $icon = if ($Ok) { '[OK]' } else { '[--]' }
    $color = if ($Ok) { "Green" } else { "Yellow" }
    $msg = "$icon $Label"
    if ($Detail) { $msg += " - $Detail" }
    Write-Host $msg -ForegroundColor $color
}

function Test-AwsCli {
    $aws = Get-Command aws -ErrorAction SilentlyContinue
    if (-not $aws) {
        Write-Host '[FAIL] AWS CLI not found. Install: https://awscli.amazonaws.com/AWSCLIV2.msi' -ForegroundColor Red
        return $false
    }
    $ver = aws --version 2>&1
    Write-Status "AWS CLI" $true $ver
    return $true
}

function Test-AwsAuth {
    try {
        $id = aws sts get-caller-identity --output json 2>&1 | ConvertFrom-Json
        if ($id.Account) {
            Write-Status "AWS credentials" $true "Account=$($id.Account) User=$($id.Arn)"
            $script:CallerAccount = $id.Account
            return $true
        }
    } catch {}
    Write-Host '[FAIL] aws sts get-caller-identity - run: aws configure' -ForegroundColor Red
    return $false
}

function Test-EnvDeploy {
    if (-not (Test-Path $EnvFile)) {
        Write-Status ".env.deploy" $false "missing - copy from .env.deploy.example"
        return
    }
    Load-DeployEnv
    $ok = [bool]$env:AWS_ACCOUNT_ID
    Write-Status ".env.deploy AWS_ACCOUNT_ID" $ok $(if ($ok) { $env:AWS_ACCOUNT_ID } else { "not set" })
    if ($ok -and $script:CallerAccount -and $env:AWS_ACCOUNT_ID -ne $script:CallerAccount) {
        Write-Host '[WARN] .env.deploy AWS_ACCOUNT_ID != sts caller account' -ForegroundColor Yellow
    }
}

function Test-IamRoles {
    foreach ($role in @("ecsTaskExecutionRole", "ecsInstanceRole")) {
        $r = aws iam get-role --role-name $role --output json 2>$null | ConvertFrom-Json
        Write-Status "IAM role $role" ([bool]$r.Role)
    }
}

function Test-EcrImages {
    foreach ($repo in @("rag-backend", "rag-frontend")) {
        $images = aws ecr describe-images --repository-name $repo --region $Region --query 'imageDetails | length(@)' --output text 2>$null
        $count = if ($images -and $images -ne "None") { [int]$images } else { 0 }
        Write-Status "ECR $repo" ($count -gt 0) $(if ($count -gt 0) { "$count image(s)" } else { "no images - run push-ecr.ps1" })
    }
}

function Test-EcsCluster {
    $c = aws ecs describe-clusters --clusters $Cluster --region $Region --output json 2>$null | ConvertFrom-Json
    $clusterInfo = $c.clusters | Select-Object -First 1
    if (-not $clusterInfo -or $clusterInfo.status -ne "ACTIVE") {
        Write-Status "ECS cluster $Cluster" $false "missing or inactive"
        return
    }
    Write-Status "ECS cluster $Cluster" $true "status=$($clusterInfo.status) running_tasks=$($clusterInfo.runningTasksCount)"
}

function Test-LogGroup {
    $lg = aws logs describe-log-groups --log-group-name-prefix $LogGroup --region $Region --output json 2>$null | ConvertFrom-Json
    $exists = ($lg.logGroups | Where-Object { $_.logGroupName -eq $LogGroup }).Count -gt 0
    Write-Status "Log group $LogGroup" $exists $(if (-not $exists) { "aws logs create-log-group --log-group-name $LogGroup --region $Region" })
}

function Test-TaskDefinition {
    $td = aws ecs describe-task-definition --task-definition $TaskFamily --region $Region --output json 2>$null | ConvertFrom-Json
    if (-not $td.taskDefinition) {
        Write-Status "Task definition $TaskFamily" $false "not registered"
        return
    }
    $def = $td.taskDefinition
    Write-Status "Task definition $TaskFamily" $true "revision=$($def.revision)"
    foreach ($c in $def.containerDefinitions) {
        $img = $c.image
        if ($img.Length -gt 60) { $img = $img.Substring(0, 60) + "..." }
        Write-Host "       container: $($c.name) image=$img"
    }
}

function Test-FargateService {
    $svc = aws ecs describe-services --cluster $Cluster --services $Service --region $Region --output json 2>$null | ConvertFrom-Json
    $s = $svc.services | Select-Object -First 1
    if (-not $s -or $s.status -ne "ACTIVE") {
        Write-Status "Fargate service $Service" $false "missing or inactive"
        return
    }
    $ok = ($s.runningCount -eq $s.desiredCount) -and ($s.runningCount -gt 0)
    Write-Status "Fargate service $Service" $ok "running=$($s.runningCount)/$($s.desiredCount) rollout=$($s.deployments[0].rolloutState)"
}

function Test-RunningTasks {
    $tasks = aws ecs list-tasks --cluster $Cluster --service-name $Service --region $Region --desired-status RUNNING --output json 2>$null | ConvertFrom-Json
    $arns = $tasks.taskArns
    if (-not $arns -or $arns.Count -eq 0) {
        Write-Status "Running ECS tasks" $false "none - wait for deployment"
        return
    }
    $desc = aws ecs describe-tasks --cluster $Cluster --tasks $arns --region $Region --output json | ConvertFrom-Json
    foreach ($t in $desc.tasks) {
        $taskId = ($t.taskArn -split "/")[-1]
        Write-Status "Task $taskId" ($t.lastStatus -eq "RUNNING") "status=$($t.lastStatus) health=$($t.healthStatus)"
        foreach ($c in $t.containers) {
            Write-Host "         $($c.name): $($c.lastStatus)"
        }
    }
}

function Test-Alb {
    $alb = aws elbv2 describe-load-balancers --names $AlbName --region $Region --output json 2>$null | ConvertFrom-Json
    $lb = $alb.LoadBalancers | Select-Object -First 1
    if (-not $lb) {
        Write-Status "ALB $AlbName" $false "not found"
        return
    }
    $dns = $lb.DNSName
    $script:AlbUrl = "http://$dns"
    Write-Status "ALB $AlbName" $true $dns

    $tgArn = $env:ALB_TARGET_GROUP_ARN
    if (-not $tgArn -and (Test-Path $EnvFile)) {
        Load-DeployEnv
        $tgArn = $env:ALB_TARGET_GROUP_ARN
    }
    if ($tgArn) {
        $health = aws elbv2 describe-target-health --target-group-arn $tgArn --region $Region --output json 2>$null | ConvertFrom-Json
        foreach ($target in $health.TargetHealthDescriptions) {
            $state = $target.TargetHealth.State
            Write-Status "  Target $($target.Target.Id)" ($state -eq "healthy") "state=$state"
        }
    }
}

function Show-Urls {
    Write-Host ""
    Write-Host "URLs:" -ForegroundColor Cyan
    if ($script:AlbUrl) {
        Write-Host "  App:  $($script:AlbUrl)"
        Write-Host "  API:  $($script:AlbUrl)/api/health"
    } else {
        Write-Host "  App:  http://rag-alb-1377520658.ap-south-1.elb.amazonaws.com"
    }
}

Write-Host "`n=== RAG AWS Deploy Check (region=$Region) ===`n" -ForegroundColor Cyan

if (-not (Test-AwsCli)) { exit 1 }
Load-DeployEnv
if (-not (Test-AwsAuth)) { exit 1 }

Write-Host "`n--- Config ---" -ForegroundColor Cyan
Test-EnvDeploy

Write-Host "`n--- ECR ---" -ForegroundColor Cyan
Test-EcrImages

Write-Host "`n--- ECS / Fargate ---" -ForegroundColor Cyan
Test-IamRoles
Test-EcsCluster
Test-LogGroup
Test-TaskDefinition
Test-FargateService
Test-RunningTasks

Write-Host "`n--- ALB ---" -ForegroundColor Cyan
Test-Alb

Show-Urls
$doneMsg = [string]::Join('', @("`nDone. Fix ", '[--]', " items, then re-run this script.`n"))
Write-Host $doneMsg -ForegroundColor Cyan
