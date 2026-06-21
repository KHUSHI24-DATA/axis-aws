# Axis AWS — RAG Web UI

Upload documents → chat with AI using your files (RAG).

**Stack:** FastAPI + Next.js + RDS (pgvector) on **ECS Fargate + ALB**  
**Region:** ap-south-1

## Structure
- `rag-web-ui/` — app
- `aws-deploy/` — deploy scripts

## Clone
git clone https://github.com/KHUSHI24-DATA/axis-aws.git
cd axis-aws

## Config (once)
copy aws-deploy\.env.deploy.example aws-deploy\.env.deploy
# Fill keys — never commit .env.deploy

## First deploy (once)
.\aws-deploy\scripts\deploy-fargate.ps1

## After code change
.\aws-deploy\scripts\push-ecr.ps1
.\aws-deploy\scripts\deploy-fargate-service.ps1 -SkipPush

## App URL
http://<alb-dns>   (ECS → rag-alb → DNS name)

## Local test (optional)
cd rag-web-ui && docker compose up -d
