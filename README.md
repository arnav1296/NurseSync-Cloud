# NurseSync

**A cloud-native nurse shift-handoff and patient status platform on AWS.**

NurseSync gives nurses a structured place to log patient status through the shift and a way to hand each patient to a named colleague, who must **Accept**, **Decline** or **Report an issue** before care changes hands. Doctors get alerts and the full patient log; administrators manage staff, admissions and assignments and watch handoff metrics.

> UCS531 Cloud Computing project · Thapar Institute of Engineering and Technology

---

## Architecture

```
Browser / Tauri app
        │ HTTPS
   Amazon CloudFront ──── /*  ──────▶ Amazon S3 (React build)
        │ /api/*
   Application Load Balancer
        │
   Auto Scaling Group: Amazon EC2 (FastAPI in Docker, image from Amazon ECR)
        ├──▶ Amazon RDS for PostgreSQL (private subnet)
        ├──▶ Amazon Cognito (verifies the sign-in token)
        ├──▶ Amazon S3 (photos, PDFs, shift reports)
        └──▶ Amazon SNS ──▶ email to the doctor / incoming nurse

Amazon EventBridge Scheduler (07:00, 19:00 IST) ──▶ AWS Lambda ──▶ /api/internal/shift-change
```

| Cloud concept | AWS service | What it does here |
|---|---|---|
| IaaS compute | **EC2** (t3.micro) | Runs the FastAPI container |
| Elasticity | **Auto Scaling Group** | 1–2 instances: CPU target tracking, plus scheduled scale-out before each shift change; replaces unhealthy instances |
| Load balancing | **Application Load Balancer** | Health-checks and spreads traffic; only accepts requests from CloudFront |
| Containers | **ECR** | Stores the API image |
| DBaaS | **RDS PostgreSQL** | All records; encrypted, private, constraints enforce the handoff rules |
| Identity (IDaaS) | **Cognito** | Sign-in and nurse / doctor / admin groups |
| Object storage | **S3** | Wound photos and charts (presigned uploads), shift reports, the website |
| CDN | **CloudFront** | One HTTPS address for site and API, cached static files |
| Serverless (FaaS) | **Lambda** + **EventBridge Scheduler** | Shift-change job: report to S3, reminder emails |
| Pub/sub messaging | **SNS** | Real-time alert, handoff and alarm emails |
| Configuration | **SSM Parameter Store** | Database URL and API keys, read by the instances at boot |
| Monitoring | **CloudWatch** | Container and Lambda logs, alarms, dashboard |
| Networking | **VPC** | Public subnets for ALB and API, private subnets for the database |
| Cost control | **AWS Budgets** | Emails if the month's bill passes $1 |
| Infrastructure as code | **Terraform** | Everything above, created and destroyed with one command |

Everything is sized for the AWS free tier.

## Repository

```
backend/    FastAPI API — routes/, services/ (db, auth, storage, notify, identity), sql/, tests/
frontend/   React 19 + Vite app (Tauri shell for desktop/iOS)
lambda/     shift_change/ — the scheduled AWS Lambda
infra/      Terraform for all AWS resources
scripts/    deploy-backend.ps1, deploy-frontend.ps1, seed-demo.ps1
```

## Deploy

**You need:** an AWS account (IAM user with `AdministratorAccess`, MFA on), and on your machine the **AWS CLI**, **Terraform**, **Docker Desktop** and **Node 20+**.

```powershell
aws configure                       # access key of your IAM user, region ap-south-1

# 1. create the infrastructure (~15 minutes; RDS and CloudFront are the slow parts)
cd infra
copy terraform.tfvars.example terraform.tfvars   # set budget_email, notification_email, API keys
terraform init
terraform apply
cd ..

# 2. build and ship the API, then the website
.\scripts\deploy-backend.ps1
.\scripts\deploy-frontend.ps1

# 3. once the API is healthy (EC2 > Target groups shows "healthy"): load the demo ward
.\scripts\seed-demo.ps1 -Password "nursesync123"
```

Open the `app_url` that Terraform prints and sign in with any seeded login (e.g. `priya.sharma@carebridge.demo`).
Confirm the SNS subscription email that arrives at `notification_email` to receive alerts.

**Tear down** after evaluation: `cd infra; terraform destroy`.

## Demo checklist

- **Auth:** sign in as a nurse, a doctor and the admin (Cognito).
- **Attachments:** attach a photo to a patient (S3 presigned upload), then view it as the doctor.
- **SNS:** raise an alert, and the doctor's email arrives.
- **Lambda:** Lambda console > `nursesync-shift-change` > Test, then check the report in S3 under `reports/` and the reminder email.
- **Self-healing:** EC2 console > terminate the API instance; the Auto Scaling Group launches a replacement.
- **Monitoring:** CloudWatch > Dashboards > `nursesync`, and Log groups > `/nursesync/api`.

## Local development

```powershell
cd backend
python -m venv venv; venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # DATABASE_URL to any Postgres, Cognito ids from terraform output
uvicorn main:app --reload --port 8000

cd ..\frontend
npm install
copy .env.example .env
npm run dev                 # http://localhost:1420
```

Tests: `cd backend; venv\Scripts\python -m pytest tests -q` (117 tests).

## Team

| Name | Roll No. |
|---|---|
| Arnav Sharma | 1024170251 |
| Rohin | 1024170193 |
| Kushagra | 1024170200 |
