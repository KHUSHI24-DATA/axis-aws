# Verify AWS deploy status (Phase 1-5) from terminal
# Usage:  .\aws-deploy\scripts\check-deploy.ps1

$ErrorActionPreference = "Continue"
$DeployDir = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $DeployDir ".env.deploy"
$Region = "ap-south-1"
$Cluster = "rag-cluster"
$TaskFamily = "rag-task"
$LogGroup = "/ecs/rag-task"

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
    $icon = if ($Ok) { "[OK]" } else { "[--]" }
    $color = if ($Ok) { "Green" } else { "Yellow" }
    $msg = "$icon $Label"
    if ($Detail) { $msg += " - $Detail" }
    Write-Host $msg -ForegroundColor $color
}

function Test-AwsCli {
    $aws = Get-Command aws -ErrorAction SilentlyContinue
    if (-not $aws) {
        Write-Host "[FAIL] AWS CLI not found. Install: https://awscli.amazonaws.com/AWSCLIV2.msi" -ForegroundColor Red
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
    Write-Host "[FAIL] aws sts get-caller-identity — run: aws configure" -ForegroundColor Red
    return $false
}

function Test-EnvDeploy {
    if (-not (Test-Path $EnvFile)) {
        Write-Status ".env.deploy" $false "missing — copy from .env.deploy.example"
        return
    }
    Load-DeployEnv
    $ok = [bool]$env:AWS_ACCOUNT_ID
    Write-Status ".env.deploy AWS_ACCOUNT_ID" $ok $(if ($ok) { $env:AWS_ACCOUNT_ID } else { "not set" })
    if ($ok -and $script:CallerAccount -and $env:AWS_ACCOUNT_ID -ne $script:CallerAccount) {
        Write-Host "[WARN] .env.deploy AWS_ACCOUNT_ID != sts caller account" -ForegroundColor Yellow
    }
    if ($env:ECR_REGISTRY -match "123456789012") {
        Write-Host "[WARN] ECR_REGISTRY still has placeholder 123456789012 — update .env.deploy" -ForegroundColor Yellow
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
        $images = aws ecr describe-images --repository-name $repo --region $Region --query "imageDetails | length(@)" --output text 2>$null
        $count = if ($images -and $images -ne "None") { [int]$images } else { 0 }
        Write-Status "ECR $repo" ($count -gt 0) "$(if ($count -gt 0) { "$count image(s)" } else { "no images - run push-ecr.ps1" })"
    }
}

function Test-SecurityGroup {
    $sgs = aws ec2 describe-security-groups --region $Region --output json 2>$null | ConvertFrom-Json
    $found = $false
    foreach ($sg in $sgs.SecurityGroups) {
        $ports = $sg.IpPermissions | Where-Object { $_.FromPort -in 3000, 8000, 22 } | ForEach-Object { $_.FromPort }
        if (($ports -contains 3000) -and ($ports -contains 8000)) {
            $found = $true
            Write-Status "Security group (3000+8000)" $true "$($sg.GroupName) $($sg.GroupId)"
            break
        }
    }
    if (-not $found) {
        Write-Status "Security group (3000+8000)" $false "no SG with both ports open"
    }
}

function Test-Ec2 {
    $inst = aws ec2 describe-instances --region $Region `
        --filters "Name=instance-state-name,Values=running,pending,stopped" `
        --query "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress,Tags[?Key=='Name'].Value|[0],IamInstanceProfile.Arn]" `
        --output json 2>$null | ConvertFrom-Json
    if (-not $inst -or $inst.Count -eq 0) {
        Write-Status "EC2 instances" $false "none found"
        return
    }
    foreach ($row in $inst) {
        $id, $state, $ip, $name, $profile = $row
        $hasEcsProfile = $profile -match "ecsInstanceRole|ecsInstance"
        Write-Status "EC2 $name ($id)" ($state -eq "running") "state=$state public_ip=$ip ecs_profile=$hasEcsProfile"
        if ($state -eq "running" -and $ip) {
            $script:PublicIp = $ip
        }
    }
}

function Test-EcsCluster {
    $c = aws ecs describe-clusters --clusters $Cluster --region $Region --include CONFIGURATIONS --output json 2>$null | ConvertFrom-Json
    $cluster = $c.clusters | Select-Object -First 1
    if (-not $cluster -or $cluster.status -ne "ACTIVE") {
        Write-Status "ECS cluster $Cluster" $false "missing or inactive"
        return
    }
    Write-Status "ECS cluster $Cluster" $true "status=$($cluster.status) registered=$($cluster.registeredContainerInstancesCount) running_tasks=$($cluster.runningTasksCount)"

    $containers = aws ecs list-container-instances --cluster $Cluster --region $Region --output json 2>$null | ConvertFrom-Json
    $n = if ($containers.containerInstanceArns) { $containers.containerInstanceArns.Count } else { 0 }
    Write-Status "Container instances in cluster" ($n -gt 0) "$n registered (need >= 1 to run tasks)"
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
    $hostOk = $def.networkMode -eq "host"
    Write-Status "Task definition $TaskFamily" $true "revision=$($def.revision) networkMode=$($def.networkMode)"
    Write-Status "  networkMode=host" $hostOk $(if (-not $hostOk) { "MUST be host" })
    foreach ($c in $def.containerDefinitions) {
        Write-Host "       container: $($c.name) image=$($c.image.Substring(0, [Math]::Min(60, $c.image.Length)))..."
    }
}

function Test-RunningTasks {
    $tasks = aws ecs list-tasks --cluster $Cluster --region $Region --desired-status RUNNING --output json 2>$null | ConvertFrom-Json
    $arns = $tasks.taskArns
    if (-not $arns -or $arns.Count -eq 0) {
        Write-Status "Running ECS tasks" $false "none — run task in Phase 5"
        return
    }
    $desc = aws ecs describe-tasks --cluster $Cluster --tasks $arns --region $Region --output json | ConvertFrom-Json
    foreach ($t in $desc.tasks) {
        Write-Status "Task $($t.taskArn.Split('/')[-1])" ($t.lastStatus -eq "RUNNING") "status=$($t.lastStatus) health=$($t.healthStatus)"
        foreach ($c in $t.containers) {
            Write-Host "         $($c.name): $($c.lastStatus)" 
        }
    }
}

function Show-Urls {
    if ($script:PublicIp) {
        Write-Host ""
        Write-Host "URLs (if task is RUNNING + SG open):" -ForegroundColor Cyan
        Write-Host "  App:  http://$($script:PublicIp):3000"
        Write-Host "  API:  http://$($script:PublicIp):8000/docs"
    }
}

Write-Host "`n=== RAG AWS Deploy Check (region=$Region) ===`n" -ForegroundColor Cyan

if (-not (Test-AwsCli)) { exit 1 }
Load-DeployEnv
if (-not (Test-AwsAuth)) { exit 1 }

Write-Host "`n--- Config ---" -ForegroundColor Cyan
Test-EnvDeploy

Write-Host "`n--- Phase 3: Infrastructure ---" -ForegroundColor Cyan
Test-IamRoles
Test-SecurityGroup
Test-Ec2
Test-EcsCluster
Test-LogGroup

Write-Host "`n--- Phase 2: ECR ---" -ForegroundColor Cyan
Test-EcrImages

Write-Host "`n--- Phase 4: Task definition ---" -ForegroundColor Cyan
Test-TaskDefinition

Write-Host "`n--- Phase 5: Running tasks ---" -ForegroundColor Cyan
Test-RunningTasks

Show-Urls
Write-Host "`nDone. Fix [--] items, then re-run this script.`n" -ForegroundColor Cyan
