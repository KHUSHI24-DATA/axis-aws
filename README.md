# Axis AWS — RAG Web UI

Document-based AI chatbot: upload PDF/DOCX files, build a knowledge base, and chat with answers grounded in your documents (RAG).

**Stack:** FastAPI + Next.js + PostgreSQL (pgvector) + OpenAI  
**AWS deploy:** ECS Fargate + Application Load Balancer + RDS  
**Region:** `ap-south-1` (Mumbai)  
**No Terraform** — PowerShell scripts + AWS Console

---

## What this project does

1. **Upload documents** (PDF, DOCX, TXT, etc.) to a Knowledge Base  
2. **Process** them into chunks and vector embeddings (OpenAI + pgvector)  
3. **Chat** — the app retrieves relevant chunks and generates answers with citations  

User feedback (thumbs up/down) is stored in the `messages` table in PostgreSQL.

---

## Project structure

```
Axis_aws/
├── rag-web-ui/                 Application source code
│   ├── backend/                FastAPI (API, RAG, document processing)
│   ├── frontend/               Next.js (web UI)
│   ├── docker-compose.yml      Local development
│   └── .env.example            Local environment template
│
└── aws-deploy/                 AWS deployment kit
    ├── .env.deploy.example     AWS deploy config template
    ├── ecs/
    │   └── task-definition.fargate.json
    ├── iam/                    IAM policy JSON files
    └── scripts/                PowerShell deploy scripts
```

| Folder | Purpose |
|--------|---------|
| `rag-web-ui` | App code (backend + frontend) |
| `aws-deploy` | Build images, push to ECR, deploy Fargate + ALB |

Keep this **sibling layout** — deploy scripts expect `rag-web-ui` and `aws-deploy` at the same level.

---

## Architecture (AWS / UAT)

```
Internet
    │
    ▼
Application Load Balancer (rag-alb)
    │  HTTP :80
    ▼
ECS Fargate (rag-service-fargate)
    ├── frontend :3000   (Next.js)
    └── backend  :8000   (FastAPI)
            │
            ├── RDS PostgreSQL (rag_private schema + pgvector)
            ├── Secrets Manager (OpenAI key, DB password)
            └── OpenAI API
```

| AWS resource | Default name |
|--------------|--------------|
| ECS cluster | `rag-cluster` |
| ECS service | `rag-service-fargate` |
| Task definition | `rag-task-fargate` |
| ALB | `rag-alb` |
| RDS | `rag-postgres` |
| ECR repos | `rag-backend`, `rag-frontend` |
| Log group | `/ecs/rag-task-fargate` |

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Local dev + ECR image build |
| [AWS CLI v2](https://awscli.amazonaws.com/AWSCLIV2.msi) | Deploy to AWS |
| [Git](https://git-scm.com/) | Clone / version control |
| AWS account | ECS, ECR, RDS, ALB |
| OpenAI API key | Chat + embeddings |

**IAM deploy user** (minimum policies):

- `AmazonECS_FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`
- `AmazonEC2FullAccess`
- `AmazonRDSFullAccess`
- `SecretsManagerReadWrite`

**IAM roles** (create once in AWS Console):

- `ecsTaskExecutionRole` — with `AmazonECSTaskExecutionRolePolicy`
- `ragEcsTaskRole` — ECS task role (no extra policy for current setup)

---

## Local development (optional)

Local run is **not required** for UAT deploy. Use it to test code on your machine.

```powershell
cd rag-web-ui
copy .env.example .env
# Edit .env — set OPENAI_API_KEY, AUTH_ENABLED=false

docker compose up -d
```

Open: **http://localhost** or **http://localhost:3000**

Stop:

```powershell
docker compose down
```

Local data (DB, uploads) is **separate** from AWS RDS.

---

## AWS / UAT deployment

### 1. Configure AWS CLI

```powershell
aws configure
# Region: ap-south-1, Output: json

aws sts get-caller-identity
```

### 2. Create deploy config

```powershell
cd aws-deploy
copy .env.deploy.example .env.deploy
notepad .env.deploy
```

Minimum values:

```env
AWS_REGION=ap-south-1
AWS_ACCOUNT_ID=YOUR_12_DIGIT_ACCOUNT_ID
ECR_REGISTRY=YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com

OPENAI_API_KEY=sk-...
SECRET_KEY=long-random-string
POSTGRES_USER=ragwebui
POSTGRES_PASSWORD=strong-password
POSTGRES_DATABASE=ragwebui
POSTGRES_SCHEMA=rag_private

VPC_ID=vpc-xxxxxxxx
ALB_SUBNET_IDS=subnet-aaa,subnet-bbb
```

**Never commit `.env.deploy`** — it contains secrets.

### 3. One-time AWS setup

From project root (`Axis_aws`):

```powershell
.\aws-deploy\scripts\setup-iam-production.ps1
.\aws-deploy\scripts\setup-rds.ps1
.\aws-deploy\scripts\setup-secrets.ps1

aws ecs create-cluster --cluster-name rag-cluster --region ap-south-1
aws logs create-log-group --log-group-name /ecs/rag-task-fargate --region ap-south-1
```

Wait until RDS status is **Available** (~10–15 min).

### 4. Deploy application

**Full deploy (ALB + images + Fargate service):**

```powershell
.\aws-deploy\scripts\deploy-fargate.ps1
```

**Or step by step:**

```powershell
.\aws-deploy\scripts\push-ecr.ps1
.\aws-deploy\scripts\setup-alb-fargate.ps1
.\aws-deploy\scripts\register-task-production.ps1 -Region ap-south-1 -Launch fargate -UsePlainEnv
.\aws-deploy\scripts\deploy-fargate-service.ps1 -SkipPush
```

### 5. Open the app

Get ALB URL:

```powershell
aws elbv2 describe-load-balancers --names rag-alb --region ap-south-1 --query "LoadBalancers[0].DNSName" --output text
```

Open in browser: `http://<alb-dns-name>`

Health check: `http://<alb-dns-name>/api/health`

### 6. Verify deployment

```powershell
.\aws-deploy\scripts\check-deploy.ps1
```

**Functional test:**

1. Create a Knowledge Base  
2. Upload a document → **Process** → status **completed**  
3. **New Chat** → select KB → ask a question about the document  

---

## Redeploy after code changes

```powershell
.\aws-deploy\scripts\push-ecr.ps1
.\aws-deploy\scripts\deploy-fargate-service.ps1 -SkipPush
```

Force ECS restart (optional):

```powershell
aws ecs update-service --cluster rag-cluster --service rag-service-fargate --force-new-deployment --region ap-south-1
```

---

## Deploy scripts reference

| Script | When to run |
|--------|-------------|
| `push-ecr.ps1` | Build Docker images and push to ECR |
| `setup-rds.ps1` | Create RDS PostgreSQL (first time) |
| `setup-secrets.ps1` | Store secrets in Secrets Manager (first time) |
| `setup-iam-production.ps1` | Attach secrets policy to execution role (first time) |
| `setup-alb-fargate.ps1` | Create ALB + security groups (first time) |
| `register-task-production.ps1 -Launch fargate` | Register ECS task definition |
| `deploy-fargate-service.ps1` | Create or update Fargate service |
| `deploy-fargate.ps1` | Full deploy (ALB + push + service) |
| `check-deploy.ps1` | Verify AWS resources and status |

More detail: [aws-deploy/README.md](./aws-deploy/README.md)

---

## Environment files

| File | Location | Committed? |
|------|----------|------------|
| `.env` | `rag-web-ui/` | **No** — local secrets |
| `.env.example` | `rag-web-ui/` | Yes — template |
| `.env.deploy` | `aws-deploy/` | **No** — AWS secrets |
| `.env.deploy.example` | `aws-deploy/` | Yes — template |

---

## AWS Console quick reference

| Check | Where |
|-------|-------|
| App running | ECS → `rag-cluster` → `rag-service-fargate` → Running = 1 |
| Public URL | EC2 → Load Balancers → `rag-alb` → DNS name |
| Docker images | ECR → `rag-backend`, `rag-frontend` |
| Database | RDS → `rag-postgres` → Available |
| Secrets | Secrets Manager → `rag/production/*` |
| Logs | CloudWatch → `/ecs/rag-task-fargate` |

---

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| `push-ecr` fails | Docker Desktop running? |
| Task won't start | `setup-secrets.ps1` + `setup-iam-production.ps1`; CloudWatch logs |
| 502 / unhealthy target | Wait 3–5 min; check ECS task and target group health |
| DB connection error | RDS security group allows Fargate SG on port 5432; re-run `setup-alb-fargate.ps1` |
| Upload / process fails | CloudWatch backend logs → `document_processor` |
| Chat wrong / empty answers | Re-upload documents on AWS; confirm processing **completed**; use **New Chat** |

---

## Security notes

- Do not commit `.env` or `.env.deploy`  
- Use strong `POSTGRES_PASSWORD` and `SECRET_KEY`  
- Keep RDS **public access disabled** in production/UAT  
- Enable `AUTH_ENABLED=true` in task definition before go-live  
- Add HTTPS via ACM certificate + ALB when a domain is available  

---

## Handoff to another machine

1. Clone or copy the full `Axis_aws` folder (both `rag-web-ui` and `aws-deploy`)  
2. Copy `.env.deploy` separately (secure channel)  
3. Install Docker Desktop + AWS CLI  
4. Run `aws configure`  
5. Deploy: `.\aws-deploy\scripts\deploy-fargate-service.ps1` (if infra exists) or full first-time steps above  

**Cursor IDE is not required** — PowerShell + Docker + AWS CLI are enough.

---

## Upstream application

Application based on [rag-web-ui](https://github.com/khursheed33/rag-web-ui) (`optimizations` branch), with AWS-specific changes for:

- RDS + `rag_private` schema  
- Fargate-compatible document upload storage  
- ALB + Next.js API proxy routes  

---

## License

See the upstream rag-web-ui repository for license terms.
