# HealPipe Deployment

This guide deploys a low-cost pilot while keeping the application portable to paid infrastructure later.

## Architecture

### Free pilot

```text
Cloudflare Pages (React/Vite)
        |
        v
Google Cloud Run (FastAPI, HEALPIPE_PROCESS_ROLE=all)
        |
        v
Supabase PostgreSQL
```

The free pilot uses one Cloud Run instance that runs the API and delivery worker together. This is suitable for demos, internal users, and low-volume design partners. Cloud Run can scale to zero, so it is not an SLA-backed production delivery system.

### Paid production upgrade

```text
Cloudflare Pages (frontend)
        |
        v
Cloud Run API (HEALPIPE_PROCESS_ROLE=api, multiple instances)
        |
        v
Supabase or Cloud SQL PostgreSQL
        ^
        |
Dedicated worker service (HEALPIPE_PROCESS_ROLE=worker)
```

The API and worker use the same image, database schema, and environment variables. The worker claims durable jobs from PostgreSQL, so moving it to a separate service does not require changing webhook records or customer data.

## Before deployment

1. Rotate any credentials that have ever been placed in a local `.env` file or chat message.
2. Create separate Google OAuth clients for `local`, `staging`, and `production`.
3. Create separate Supabase projects or databases for staging and production. Do not use the development database for customer data.
4. Push the repository to GitHub.
5. Install the Google Cloud CLI if you plan to use Cloud Build commands.

## 1. Create the Supabase database

1. Open https://supabase.com/dashboard.
2. Click **New project**.
3. Choose an organization.
4. Enter:

```text
Name: healpipe-production
Database password: generate a new strong password
Region: choose the region closest to your users and Cloud Run
Pricing plan: Free for the pilot
```

5. Click **Create new project** and wait for it to finish.
6. In the left menu, click **Project Settings**.
7. Click **Database**.
8. Find **Connection string** and choose the **URI** or **Session pooler** connection string.
9. Copy it and convert it to the application format if necessary:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/postgres
```

Use the pooler connection string for serverless or scaled services. URL-encode special characters in the database password.

The application creates its tables with:

```powershell
.\.venv\Scripts\python.exe -m database.init_db
```

For production, run that command once as a migration task before starting the API and worker services.

## 2. Create Google OAuth credentials

Use a separate OAuth client for each environment.

1. Open https://console.cloud.google.com/.
2. Use the project selector at the top.
3. Click **New Project**.
4. Enter `HealPipe Production`.
5. Click **Create**, then select the new project.
6. Open https://console.cloud.google.com/auth/branding.
7. Configure the OAuth branding:

```text
App name: HealPipe
Support email: your support email
Audience: External
Scopes: openid, email, profile only
```

8. Open **Audience** and add pilot users under **Test users** while the app is in testing.
9. Open https://console.cloud.google.com/auth/clients.
10. Click **Create client**.
11. Select **Web application**.
12. Enter `HealPipe Production Web`.
13. Under **Authorized JavaScript origins**, add the final frontend origin, for example:

```text
https://app.healpipe.example
```

14. Do not add a redirect URI for the current Google Identity Services button flow.
15. Click **Create**.
16. Copy the **Client ID**, not the client secret.

For the pilot before you have a custom domain, temporarily add the Cloudflare Pages URL as an authorized JavaScript origin. Add the custom domain later and remove the temporary origin when ready.

## 3. Create the Google Cloud project

1. Open https://console.cloud.google.com/projectcreate.
2. Enter:

```text
Project name: HealPipe Production
```

3. Click **Create**.
4. Select the project.
5. Open **Billing** and attach a billing account. Google Cloud may require billing even when the pilot stays within free quotas.
6. Open **APIs & Services** and enable:

```text
Cloud Run Admin API
Cloud Build API
Artifact Registry API
```

## 4. Prepare production environment values

Create a private deployment note or secret manager entries. Do not commit these values.

```text
DATABASE_URL=postgresql+asyncpg://...
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=5
CORS_ORIGINS=https://app.healpipe.example
HEALPIPE_PROCESS_ROLE=all
DELIVERY_WORKER_COUNT=2
WORKER_POLL_INTERVAL_SECONDS=5
GOOGLE_CLIENT_ID=production-client-id.apps.googleusercontent.com
AUTH_SESSION_SECRET=long-random-production-secret
AUTH_SESSION_TTL_SECONDS=28800
ANTHROPIC_API_KEY=production-anthropic-key
ANTHROPIC_MODEL=claude-haiku-4-5
ACCOUNT_AUTH_REQUIRED=true
REQUIRE_IDEMPOTENCY_KEY=true
AUDIT_EXPORT_MAX_ROWS=5000
HEALPIPE_DASHBOARD_URL=https://app.healpipe.example
```

Generate the session secret locally:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

For the free pilot, leave SMTP variables unset if email is not ready. Alerts will be logged and skipped rather than blocking webhook processing.

## 5. Deploy the backend to Cloud Run

### Build the image

Open PowerShell in the repository root and set your values:

```powershell
$PROJECT_ID = "your-google-cloud-project-id"
$REGION = "us-central1"
$IMAGE = "gcr.io/$PROJECT_ID/healpipe-api"
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud builds submit --tag $IMAGE .
```

### Deploy the free pilot

The pilot deliberately uses `HEALPIPE_PROCESS_ROLE=all` so worker delivery continues inside the same service.

```powershell
gcloud run deploy healpipe-api `
  --image $IMAGE `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --port 8000 `
  --memory 1Gi `
  --cpu 1 `
  --min-instances 0 `
  --max-instances 1 `
  --set-env-vars "HEALPIPE_PROCESS_ROLE=all,DB_POOL_SIZE=3,DB_MAX_OVERFLOW=5,ACCOUNT_AUTH_REQUIRED=true,REQUIRE_IDEMPOTENCY_KEY=true" `
  --set-env-vars "DATABASE_URL=REPLACE_ME,GOOGLE_CLIENT_ID=REPLACE_ME,AUTH_SESSION_SECRET=REPLACE_ME,CORS_ORIGINS=https://REPLACE_ME.pages.dev"
```

For secrets, prefer Secret Manager instead of putting values in shell history:

```powershell
gcloud secrets create healpipe-database-url --replication-policy=automatic
gcloud secrets versions add healpipe-database-url --data-file=-
gcloud secrets create healpipe-auth-session-secret --replication-policy=automatic
gcloud secrets versions add healpipe-auth-session-secret --data-file=-
```

Paste each secret only when the terminal is waiting for input. Then deploy with `--set-secrets`.

After deployment, copy the Cloud Run service URL and verify:

```text
https://YOUR-CLOUD-RUN-URL/health
```

The response should be:

```json
{"status":"ok"}
```

### Cloud Console equivalent

1. Open **Cloud Run**.
2. Click **Deploy container**.
3. Choose **Existing container image**.
4. Select the image from Artifact Registry or Container Registry.
5. Set the service name to `healpipe-api`.
6. Choose the region.
7. Set container port to `8000`.
8. Under **Container(s), Volumes, Networking, Security**, open **Variables & Secrets**.
9. Add the environment variables from the production list.
10. Under **Authentication**, choose **Allow unauthenticated invocations**. Webhook sources must be able to reach the signed ingress; application APIs still require account authentication.
11. Under **Autoscaling**, set maximum instances to `1` for the pilot.
12. Click **Create**.

## 6. Deploy the frontend to Cloudflare Pages

1. Open https://dash.cloudflare.com/.
2. Select an account.
3. Open **Workers & Pages**.
4. Click **Create application**.
5. Choose **Pages** and **Connect to Git**.
6. Authorize GitHub and select the `healpipe` repository.
7. Configure the build:

```text
Framework preset: Vite
Production branch: main
Build command: npm run build
Build output directory: dist
Root directory: /
```

8. Add these Pages environment variables:

```text
VITE_API_BASE_URL=https://YOUR-CLOUD-RUN-URL
VITE_GOOGLE_CLIENT_ID=production-client-id.apps.googleusercontent.com
```

9. Click **Save and Deploy**.
10. Open the generated `pages.dev` URL.
11. Add that exact URL to Google Cloud Console under **Authorized JavaScript origins**.
12. Test Google sign-in, onboarding, bridge creation, and dashboard loading.

### Add a custom domain later

1. In Cloudflare Pages, open the project.
2. Click **Custom domains**.
3. Click **Set up a custom domain**.
4. Enter `app.yourdomain.com`.
5. Follow the DNS instructions.
6. Replace the Pages URL in:

```text
CORS_ORIGINS
HEALPIPE_DASHBOARD_URL
Google Authorized JavaScript origins
VITE_API_BASE_URL remains the Cloud Run API URL
```

## 7. Run the database initializer

For the first deployment, run the initializer from a trusted environment with the production `DATABASE_URL`:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://..."
.\.venv\Scripts\python.exe -m database.init_db
```

Do not run schema initialization concurrently from multiple API instances. Later, use a one-off migration job before each release.

## 8. Test the deployed pilot

Check these flows:

1. Open the Pages URL.
2. Click **Sign up**.
3. Complete Google authentication.
4. Complete all five onboarding questions.
5. Create a data bridge.
6. Copy the ingestion URL and signature secret.
7. Send a signed test webhook.
8. Confirm the event appears in the dashboard.
9. Confirm the worker delivers or retries it.
10. Sign out and confirm the modal.
11. Sign in again with **Login**.
12. Verify the account email appears in the account menu.

Use the health endpoint and Cloud Run logs for diagnosis:

```powershell
gcloud run services logs read healpipe-api --region $REGION --limit 100
```

## 9. Safe upgrade to paid production

Keep the same repository, Dockerfile, environment names, and database schema.

1. Deploy the same image with `HEALPIPE_PROCESS_ROLE=api`.
2. Set API instances to at least `1` and configure autoscaling.
3. Deploy the same image as a dedicated always-on worker using:

```text
HEALPIPE_PROCESS_ROLE=worker
DELIVERY_WORKER_COUNT=4
WORKER_POLL_INTERVAL_SECONDS=2
```

4. Scale the worker independently from the API.
5. Move `DATABASE_URL` and other secrets to Secret Manager.
6. Upgrade Supabase or migrate PostgreSQL using `pg_dump` and `pg_restore`.
7. Add monitoring, backups, rate limits, and a staging environment.
8. Change Google OAuth origins from pilot URLs to the production domain.
9. Load test webhook ingress and retry recovery before accepting critical traffic.

The durable `delivery_jobs`, `delivery_attempts`, and lifecycle tables are the migration boundary. The worker claims due jobs from PostgreSQL, so moving the worker does not require replaying or rewriting existing events.

## Free-tier expectations

The free pilot is for low-volume use. Expect scale-to-zero cold starts, provider quotas, limited logs, and no delivery SLA. Do not connect business-critical webhooks until the worker is always-on, database backups are enabled, and monitoring is configured.
