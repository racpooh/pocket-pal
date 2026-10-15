# Deploying the sandbox to Google Cloud (proposed — NOT yet executed)

Status: instructions written 15 Oct 2026; no deployment exists yet. Nothing in the security self-assessment may claim TLS or encryption at rest until these steps have actually been run and the resulting configuration is captured as evidence.

## Target shape
- **Cloud Run** service `finassist-api` (container from `backend/Dockerfile`), `min-instances=1`, CPU always allocated, `FINASSIST_EMBEDDED_WORKER=true` so the job loop runs in the same service (simplest; one service to secure).
- **Cloud SQL for PostgreSQL 16**, private IP or the Cloud SQL connector; no public IP.
- **Cloud Storage** private bucket for retained images, uniform bucket-level access, public access prevention enforced, lifecycle rule for retention.
- **Secret Manager** for `FINASSIST_DATABASE_URL` and `FINASSIST_MODEL_API_KEY`.
- Region `asia-southeast1` (Singapore).

## What this gives us to evidence (and what it does not)
- TLS: Cloud Run serves HTTPS on its `run.app` URL. Evidence: `curl -vI` output.
- Encryption at rest: Google documents default encryption at rest for Cloud SQL and Cloud Storage with Google-managed keys (https://cloud.google.com/docs/security/encryption/default-encryption). Evidence: bucket/instance describe output. We would claim *provider default encryption*, not customer-managed keys.
- Not provided by this setup: MFA, WAF, DDoS tuning, key rotation policy of our own, backups deletion guarantees beyond Cloud SQL's retention settings.

## Commands (fill in PROJECT_ID; run by the account owner)

```bash
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com storage.googleapis.com
REGION=asia-southeast1

# Database
gcloud sql instances create finassist-db --database-version=POSTGRES_16 --region=$REGION --tier=db-f1-micro --storage-auto-increase
gcloud sql databases create finassist --instance=finassist-db
gcloud sql users create finassist_owner --instance=finassist-db --password="$(openssl rand -base64 24)"   # migrations only
# apply backend/db/migrations/*.sql in order as finassist_owner (Cloud SQL Studio or `gcloud sql connect`), then:
#   CREATE ROLE finassist_app LOGIN PASSWORD '...' NOBYPASSRLS;           -- API (RLS applies)
#   CREATE ROLE finassist_worker_login LOGIN PASSWORD '...' NOBYPASSRLS IN ROLE finassist_worker;
#   GRANT USAGE ON SCHEMA public TO finassist_app, finassist_worker;
#   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO finassist_app, finassist_worker;
#   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finassist_app, finassist_worker;

# Bucket
gcloud storage buckets create gs://PROJECT_ID-finassist-uploads --location=$REGION --uniform-bucket-level-access --public-access-prevention
# optional retention: delete objects after 30 days
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}' > lifecycle.json
gcloud storage buckets update gs://PROJECT_ID-finassist-uploads --lifecycle-file=lifecycle.json

# Secrets
printf 'postgresql://finassist_app:PASSWORD@/finassist?host=/cloudsql/PROJECT_ID:asia-southeast1:finassist-db' | gcloud secrets create finassist-db-url --data-file=-
printf 'postgresql://finassist_worker_login:PASSWORD@/finassist?host=/cloudsql/PROJECT_ID:asia-southeast1:finassist-db' | gcloud secrets create finassist-worker-db-url --data-file=-
printf '%s' "$ANTHROPIC_KEY" | gcloud secrets create finassist-model-key --data-file=-

# Service account with least privilege
gcloud iam service-accounts create finassist-run
SA=finassist-run@PROJECT_ID.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding PROJECT_ID --member=serviceAccount:$SA --role=roles/cloudsql.client
gcloud storage buckets add-iam-policy-binding gs://PROJECT_ID-finassist-uploads --member=serviceAccount:$SA --role=roles/storage.objectAdmin
for s in finassist-db-url finassist-worker-db-url finassist-model-key; do gcloud secrets add-iam-policy-binding $s --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor; done

# Build and deploy
gcloud run deploy finassist-api --source backend --region=$REGION --service-account=$SA \
  --add-cloudsql-instances=PROJECT_ID:$REGION:finassist-db --min-instances=1 --no-cpu-throttling \
  --set-env-vars=FINASSIST_ENV=sandbox,FINASSIST_STORAGE_BACKEND=gcs,FINASSIST_GCS_BUCKET=PROJECT_ID-finassist-uploads,FINASSIST_MODEL_PROVIDER=anthropic,FINASSIST_EMBEDDED_WORKER=true \
  --set-secrets=FINASSIST_DATABASE_URL=finassist-db-url:latest,FINASSIST_WORKER_DATABASE_URL=finassist-worker-db-url:latest,FINASSIST_MODEL_API_KEY=finassist-model-key:latest \
  --allow-unauthenticated   # app-level auth protects /v1/*; only /v1/health is public
```

## Evidence to capture after deploying
`gcloud run services describe`, `gcloud sql instances describe` (no public IP, backups), `gcloud storage buckets describe` (public access prevention, lifecycle), `curl -vI https://…/v1/health`, and one sandbox scenario run against the deployed URL.
