# Full Fargate deploy: ALB + security groups + Fargate service
param(
    [string]$Region = "ap-south-1",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$Scripts = $PSScriptRoot

& "$Scripts\setup-alb-fargate.ps1" -Region $Region

$params = @{ Region = $Region }
if ($SkipPush) { $params.SkipPush = $true }
& "$Scripts\deploy-fargate-service.ps1" @params
