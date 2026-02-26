# Clinic HRM System – Deployment Guide

This document outlines how to set up, configure, and deploy the Clinic HRM System in different environments.

## Table of Contents

1. [Local Development](#local-development)
2. [Environment Configuration](#environment-configuration)
3. [Database Setup](#database-setup)
4. [Deploying to Google Cloud Run](#deploying-to-google-cloud-run)
5. [Using Google Secret Manager](#using-google-secret-manager)
6. [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- **Python 3.13+**
- **Git**
- **Cloudinary account** (for image uploads)
- **PostgreSQL** (optional, for production-like testing)

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd clinic_hrm_system
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

**Key variables to configure:**

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | SQLite for local (or PostgreSQL for production) | `sqlite:///./database.db` |
| `ENCRYPTION_KEY` | Fernet encryption key (generate with `python -m cryptography.fernet generate_key()`) | See below |
| `VAPID_PUBLIC_KEY` | Web push public key | See below |
| `VAPID_PRIVATE_KEY` | Web push private key | See below |
| `CLOUDINARY_*` | Image upload credentials | See Cloudinary setup |

### 5. Generate Required Keys

#### Encryption Key (Fernet)

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key().decode()
print(key)
```

Save this value to `ENCRYPTION_KEY` in `.env`.

#### VAPID Keys (Web Push)

```bash
python -m py_vapid --gen --format string
```

Copy both `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` to `.env`.

#### Cloudinary Setup

1. Create an account at [cloudinary.com](https://cloudinary.com/)
2. Go to **Settings → API Environment variable**
3. Copy:
   - `CLOUDINARY_CLOUD_NAME`
   - `CLOUDINARY_API_KEY`
   - `CLOUDINARY_API_SECRET`

### 6. Initialize the Database

The app automatically creates tables on first run. If needed, manually initialize:

```bash
python
>>> from app.database import Base, engine
>>> Base.metadata.create_all(bind=engine)
```

### 7. Run the Application

```bash
uvicorn app.main:app --reload
```

Visit: `http://localhost:8000`

---

## Environment Configuration

### Required Environment Variables

At startup, the application validates these critical variables:

```python
required = ["ENCRYPTION_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "DATABASE_URL"]
```

If any are missing, the app will **fail to start** with an error message.

### Configuration File

All environment variables are centralized in [`app/config.py`](app/config.py):

```python
from cryptography.fernet import Fernet
import os

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
CIPHER_SUITE = Fernet(ENCRYPTION_KEY.encode())
```

---

## Database Setup

### Local Development (SQLite)

SQLite is used by default. No additional setup required beyond `.env` configuration.

**Database file location:** `database.db` (in project root)

### PostgreSQL (Recommended for Production)

#### 1. Install PostgreSQL

```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# Windows
# Download from https://www.postgresql.org/download/windows/
```

#### 2. Create Database and User

```sql
CREATE USER hrm_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE clinic_hrm_db OWNER hrm_user;
GRANT ALL PRIVILEGES ON DATABASE clinic_hrm_db TO hrm_user;
```

#### 3. Update `.env`

```env
DATABASE_URL=postgresql://hrm_user:your_secure_password@localhost:5432/clinic_hrm_db
```

#### 4. Test Connection

```bash
psql postgresql://hrm_user:your_secure_password@localhost:5432/clinic_hrm_db
```

### Google Cloud SQL (Production)

See [Google Cloud SQL Configuration](#google-cloud-sql-configuration) below.

---

## Deploying to Google Cloud Run

### Prerequisites

- **Google Cloud Project** with billing enabled
- **gcloud CLI** installed and authenticated
- **Docker** installed locally
- **Google Cloud Service Account** with appropriate permissions

### 1. Create a GCP Project

```bash
gcloud projects create clinic-hrm --set-as-default
gcloud billing projects link clinic-hrm --billing-account=<BILLING_ACCOUNT_ID>
```

### 2. Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com
```

### 3. Create Cloud SQL Instance (PostgreSQL)

```bash
gcloud sql instances create clinic-hrm-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=asia-southeast1 \
  --availability-type=zonal
```

Create database and user:

```bash
gcloud sql databases create clinic_hrm_db \
  --instance=clinic-hrm-db

gcloud sql users create hrm_user \
  --instance=clinic-hrm-db \
  --password=<SECURE_PASSWORD>
```

### 4. Store Secrets in Secret Manager

```bash
# Encryption key
echo -n "your-fernet-key" | gcloud secrets create ENCRYPTION_KEY --data-file=-

# VAPID Public Key
echo -n "your-vapid-public-key" | gcloud secrets create VAPID_PUBLIC_KEY --data-file=-

# VAPID Private Key
echo -n "your-vapid-private-key" | gcloud secrets create VAPID_PRIVATE_KEY --data-file=-

# Cloudinary credentials
echo -n "your-cloud-name" | gcloud secrets create CLOUDINARY_CLOUD_NAME --data-file=-
echo -n "your-api-key" | gcloud secrets create CLOUDINARY_API_KEY --data-file=-
echo -n "your-api-secret" | gcloud secrets create CLOUDINARY_API_SECRET --data-file=-
```

### 5. Grant Cloud Run Service Account Access to Secrets

```bash
# Get the Cloud Run default service account
PROJECT_ID=$(gcloud config get-value project)
CLOUD_RUN_SA="${PROJECT_ID}@appspot.gserviceaccount.com"

# Grant access to all secrets
for secret in ENCRYPTION_KEY VAPID_PUBLIC_KEY VAPID_PRIVATE_KEY \
              CLOUDINARY_CLOUD_NAME CLOUDINARY_API_KEY CLOUDINARY_API_SECRET
do
  gcloud secrets add-iam-policy-binding $secret \
    --member=serviceAccount:$CLOUD_RUN_SA \
    --role=roles/secretmanager.secretAccessor
done
```

### 6. Deploy to Cloud Run

#### Using cloud-run-deployment.yml (Recommended)

Create `cloud-run-deployment.yml` in the root directory (see example in repo).

```bash
gcloud run deploy clinic-hrm-system \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=postgresql://hrm_user:PASSWORD@CLOUD_SQL_IP:5432/clinic_hrm_db"
```

#### Manual Docker Build

```bash
# Build
docker build -t clinic-hrm .

# Tag for Google Container Registry
docker tag clinic-hrm gcr.io/clinic-hrm/clinic-hrm:latest

# Push to registry
docker push gcr.io/clinic-hrm/clinic-hrm:latest

# Deploy
gcloud run deploy clinic-hrm-system \
  --image gcr.io/clinic-hrm/clinic-hrm:latest \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated
```

### 7. Configure Environment Variables in Cloud Run

Set environment variables in Cloud Run:

```bash
gcloud run services update clinic-hrm-system \
  --update-env-vars DATABASE_URL="postgresql://hrm_user:PASSWORD@CLOUD_SQL_IP:5432/clinic_hrm_db"
```

Or use the **Google Cloud Console** → Cloud Run → clinic-hrm-system → Edit & Deploy.

---

## Using Google Secret Manager

### Why Secret Manager?

Google Secret Manager is more secure than storing secrets in environment variables. It:
- **Centrally manages** all secrets
- **Audits access** to secrets
- **Rotates secrets** without redeployment
- **Integrates natively** with Cloud Run

### Publishing Secrets

```bash
# Create a secret
gcloud secrets create ENCRYPTION_KEY \
  --replication-policy="automatic" \
  --data-file=-

# Update a secret
echo -n "new-value" | gcloud secrets versions add ENCRYPTION_KEY --data-file=-

# View secret value (for debugging only)
gcloud secrets versions access latest --secret="ENCRYPTION_KEY"
```

### Accessing Secrets in Cloud Run

In `app/config.py`, you can modify to read from Secret Manager:

```python
from google.cloud import secretmanager

def access_secret_version(secret_id: str, version_id: str = "latest") -> str:
    """Access a secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv('GCP_PROJECT_ID')
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Usage
ENCRYPTION_KEY = access_secret_version("ENCRYPTION_KEY")
```

---

## Dockerfile Configuration

The repository includes a `Dockerfile` optimized for Cloud Run:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/').read()"

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Monitoring & Logging

### Local Development

Logs are printed to stdout with structured format:

```
2026-02-26 10:30:45,123 INFO clinic_hrm: Employee XYZ logged in
```

### Cloud Run

All container logs are automatically sent to **Google Cloud Logging**.

View logs:

```bash
gcloud run logs read clinic-hrm-system --region asia-southeast1 --limit 50
```

Or use the **Google Cloud Console** → Cloud Run → clinic-hrm-system → Logs.

---

## Troubleshooting

### Error: "ENCRYPTION_KEY environment variable is not set"

**Solution:** Ensure `ENCRYPTION_KEY` is set in `.env` or Cloud Run environment variables.

```bash
# Local
echo $ENCRYPTION_KEY

# Cloud Run
gcloud run services describe clinic-hrm-system --format="value(spec.template.spec.containers[0].env)"
```

### Error: "DATABASE_URL is not set"

**Solution:** Database URL is required. Set it before starting the app.

For Cloud SQL, use:

```
postgresql://user:password@CLOUD_SQL_PRIVATE_IP:5432/clinic_hrm_db
```

### Database Connection Timeout

**Solution:** On Cloud Run, enable Cloud SQL Connector:

```bash
gcloud run deploy clinic-hrm-system \
  --add-cloudsql-instances=clinic-hrm-db \
  --set-env-vars CLOUD_SQL_CONNECTION_NAME="project:region:instance"
```

---

## Quick Reference Checklists

### Pre-Deployment Checklist

- [ ] All environment variables in `.env.example` are documented
- [ ] `ruff check .` passes (no linting errors)
- [ ] `pytest` tests pass (if applicable)
- [ ] Secrets are stored in Google Secret Manager (not in code)
- [ ] Database migrations are up-to-date
- [ ] HTTPS is enforced in Cloud Run
- [ ] Monitoring/logging is configured

### Post-Deployment Checklist

- [ ] Cloud Run service is healthy (check logs)
- [ ] Database connection is working
- [ ] File uploads (Cloudinary) are functional
- [ ] Web push notifications are delivered
- [ ] Admin dashboard loads without errors

---

## Additional Resources

- **FastAPI Documentation:** https://fastapi.tiangolo.com/
- **SQLAlchemy ORM:** https://docs.sqlalchemy.org/
- **Google Cloud Run:** https://cloud.google.com/run/docs
- **Google Secret Manager:** https://cloud.google.com/secret-manager/docs
- **Docker Best Practices:** https://docs.docker.com/develop/dev-best-practices/

---

**Last Updated:** February 2026  
**Environment:** Python 3.13, FastAPI 0.128.5, PostgreSQL/SQLite
