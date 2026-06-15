# AWS Deploy — RAG Web UI (Fargate)

Deploy scripts for **ECS Fargate + ALB + RDS**. No EC2 task, no Terraform.

**Main project guide:** [../README.md](../README.md)

---

## Current stack

| Component | Value |
|-----------|--------|
| Launch type | ECS Fargate |
| Service | `rag-service-fargate` |
| Task family | `rag-task-fargate` |
| ALB | `rag-alb` |
| RDS schema | `rag_private` |
| Containers | `backend` (8000) + `frontend` (3000) |

---

## Quick deploy

**First time** (after `.env.deploy` is filled and IAM roles exist):

```powershell
cd F:\Axis_aws
.\aws-deploy\scripts\deploy-fargate.ps1
```

**Code update only:**

```powershell
.\aws-deploy\scripts\push-ecr.ps1
.\aws-deploy\scripts\deploy-fargate-service.ps1 -SkipPush
```

---

## Step-by-step (first deploy)

```powershell
# From Axis_aws project root
.\aws-deploy\scripts\setup-iam-production.ps1
.\aws-deploy\scripts\setup-rds.ps1
.\aws-deploy\scripts\setup-secrets.ps1

aws ecs create-cluster --cluster-name rag-cluster --region ap-south-1
aws logs create-log-group --log-group-name /ecs/rag-task-fargate --region ap-south-1

.\aws-deploy\scripts\push-ecr.ps1
.\aws-deploy\scripts\setup-alb-fargate.ps1
.\aws-deploy\scripts\register-task-production.ps1 -Region ap-south-1 -Launch fargate -UsePlainEnv
.\aws-deploy\scripts\deploy-fargate-service.ps1 -SkipPush
```

---

## Config file

```powershell
copy aws-deploy\.env.deploy.example aws-deploy\.env.deploy
notepad aws-deploy\.env.deploy
```

Required: `AWS_ACCOUNT_ID`, `OPENAI_API_KEY`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `VPC_ID`, `ALB_SUBNET_IDS`, `RDS_ENDPOINT` (after RDS setup).

**Never commit `.env.deploy`.**

---

## Scripts

| Script | Purpose |
|--------|---------|
| `push-ecr.ps1` | Build and push images to ECR |
| `setup-rds.ps1` | Create RDS PostgreSQL |
| `setup-secrets.ps1` | Secrets Manager entries |
| `setup-iam-production.ps1` | Secrets read policy on execution role |
| `setup-alb-fargate.ps1` | ALB, target group, security groups |
| `register-task-production.ps1 -Launch fargate` | Register task definition |
| `deploy-fargate-service.ps1` | Create/update Fargate service |
| `deploy-fargate.ps1` | Full pipeline |
| `check-deploy.ps1` | Status checks |

---

## IAM files

| File | Used when |
|------|-----------|
| `iam/ecs-execution-secrets-policy.json` | **Required** — ECS reads Secrets Manager |
| `iam/rag-ecs-task-role-policy.json` | Only if using S3 uploads (`setup-s3.ps1`) |

---

## HTTPS (optional)

Add to `.env.deploy`:

```env
ACM_CERT_ARN=arn:aws:acm:ap-south-1:ACCOUNT:certificate/xxxxx
DOMAIN_NAME=uat.example.com
```

Re-run `setup-alb-fargate.ps1`, then point DNS (Route 53 or CNAME) to the ALB.
