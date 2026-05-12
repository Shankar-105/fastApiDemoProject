## Easy Setup with Docker 🐋

### **📁 Fork and Clone the Repository**
To get started, **fork this repo first**, then clone your fork and set up your environment.

- **Fork the repository** on GitHub
  - This keeps your pushes going to your own fork instead of accidentally pushing to the original repo.

- **Clone your fork**
```bash:disable-run
git clone https://github.com/<your-username>/Social-Media-Api.git
```

- **Change into the project directory**
```bash:disable-run
cd Social-Media-Api
```

- **Rename the sample environment file to .env** (this keeps secrets/config out of version control)
```bash:disable-run
mv .env.sample .env
```
> Why: app reads configuration from `.env` so it must be `.env`. Also renaming `.env.sample` to `.env` ensures sensitive keys (DB password, email creds, JWT secret) are loaded locally and not committed (via .gitignore) when you later commit/push your changes of this clone.

---

### **⚙️ Prepare the .env File**

Now open your `.env` file and configure it field-by-field. Some fields need your attention, others can stay as-is.

#### Fields to leave as-is
- `DATABASE_HOST` — **keep as `db`** (this is the Docker Compose service name, and it protects you if the app reads `.env` before the container environment)
- `DATABASE_PORT, DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME` — usually leave these unless you intentionally changed your Postgres container
- `SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_TIME, REFRESH_TOKEN_EXPIRE_DAYS` — keep for local dev unless testing auth behavior
- `REDIS_HOST, REDIS_PORT, REDIS_DB` — keep as-is (Redis is already wired to the `redis` service with default cache DB `0`)
- `CELERY_BROKER_URL, CELERY_RESULT_BACKEND` — keep as-is (already the celery broker url is set to rabbitmq url and celery result in redis db 1)
- `RL_*` values — rate-limiting knobs; change if you want stricter/looser limits, but defaults are fine for local dev
- `MAX_EDIT_TIME` — maximum edit time of a chat message keep as-is unless you wanna test with other values.
#### Fields that need your attention
- `EMAIL_USERNAME` — set to your Gmail address (if you want OTP emails to work)
- `EMAIL_FROM` — usually the same Gmail as `EMAIL_USERNAME`
- `EMAIL_PASSWORD` — set to your Google App Password, **not** your regular Gmail password
  - **How to get an App Password:** Enable 2-Step Verification on your Google Account, then generate a 16-character app-specific password. Search for "How to Create App Password for Google Account" on youtube for a quick tutorial.
  - Why: Prevents exposing your main Gmail password and avoids blocking by Google.

#### Azure Blob Storage & Local Folders
- `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_STORAGE_ACCOUNT_NAME` — **leave these empty for local development**
  - When empty, the app stores media files locally in `profilepics/`, `posts_media/`, and `chat-media/` folders
  - This fallback is handled by [`app/services/blob_service.py`](../app/services/blob_service.py), which automatically switches to local file writes when Azure values are empty
  - Create these folders now before starting the app:
```bash
mkdir profilepics posts_media chat-media
```
  - These folders will store profile pictures, post media, and chat uploads locally and will not crash the app if empty Azure values are set

#### Benchmark Mode & Worker Count
- `BENCHMARK_MODE_ENABLED` — keep this `false` for normal development.
When `BENCHMARK_MODE_ENABLED=false`, the startup path is:

1. The Dockerfile entrypoint runs `docker_entrypoint.sh` which reads from `app.config.Settings` and sees `BENCHMARK_MODE_ENABLED=false`.
2. So `docker_entrypoint.sh` selects `startup_dev.sh`.
3. `startup_dev.sh` runs `alembic upgrade head` first.
4. It then starts single `uvicorn` process with hot reload.
5. `app/main.py` sees benchmark mode is disabled and triggers `configure_observability(...)`.
6. So FastAPI tracing, SQLAlchemy instrumentation, Prometheus instrumentation, and the request-timing middleware are added and logs will be printed to console.
7. `OTEL_CONSOLE_EXPORTER_ENABLED` — keep this also `false` unless you already know how OpenTelemetry console spans work and how to interpret them or to track each request response end to end.

- If you want to know what happens when this is `true` and how it relates to raw app performance testing, see [`docs/MONITORING_AND_LOAD_TESTING.md`](./MONITORING_AND_LOAD_TESTING.md).
---

### **Docker Setup & Running the Project** 🚀

Now that you've configured all the environment variables, you're ready to run the Docker containers.
This project uses **Docker Compose** for an easy multi-service setup with **docker volumes** that persist your data throughout development.

#### Services in the Docker Compose Stack

1. **API**  — FastAPI application (main code)
2. **PostgreSQL**  — Relational database for application data
3. **Redis**  — In-memory cache for sessions and rate-limiting
4. **RabbitMQ**  — Message broker for async task queues (Celery)
5. **Celery Worker**  — Background job processor
6. **Celery Beat**  — Scheduler for periodic jobs
7. **Flower**  — Celery task monitor (optional, for debugging async tasks)
8. **Prometheus**  — Metrics collection in its Time Series DB
9. **Grafana**  — Visualization and dashboards for collected metrics

#### Service Login Details

These are the credentials that matter when you open the local dashboards. Use them directly; they are the default local accounts for this stack.

| Service | URL | Login |
| --- | --- | --- |
| **Grafana** | `http://localhost:3000` | **username:** `admin`<br>**password:** `admin` |
| **RabbitMQ Management** | `http://localhost:15672` | **username:** `guest`<br>**password:** `guest` |

Prometheus does not require a login for the local setup, and Flower is typically opened directly without a separate login in this compose stack.

#### Prerequisites to use Docker
- Ensure Docker Desktop is installed and running.
  - Verify with:
```bash:disable-run
docker --version
```
  - Expected: a Docker version output (e.g., `Docker version 20.x.x` or newer).


<details>

<summary name ="install-k6"><b>k6 Installation</b></summary>

- Install k6 on your machine not required now while your in dev mode but must when you run k6 tests in benchmark mode.
  - k6 is not packaged in this repository's Docker Compose services so you need to manually download it.

- In Windows, Open PowerShell and run as adminstrator:

  - using winget:
  ```powershell:disable-run
  winget install k6 --source winget
  ```
  - using chocolatey :
  ```powershell:disable-run
  choco install k6
  ```
- In Linux:
```bash:disable-run
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt update
sudo apt install k6
```
- In macOS (Homebrew):
```bash:disable-run
brew install k6
```
</details>

### **Now Start All the Services (build -> compose -> verify)**
Follow these commands to bring everything up:

1. **Build images**
```bash:disable-run
docker compose build
```

2. **Start in detached mode**
```bash:disable-run
docker compose up -d
```
- What happens: Compose starts all the services. Alembic migrations run automatically on startup so the postgres tables are upto date.

3. **Verify** ✅
Lists all running services:
```bash:disable-run
docker compose ps
```

Now everything is running! You can make changes to your code, and thanks to **volumes and reload**, the app will automatically respond to your changes. 

For detailed usage of Grafana dashboards and k6 monitoring workflows, check out:
- [`MONITORING_AND_LOAD_TESTING.md`](./MONITORING_AND_LOAD_TESTING.md)

4. **Stop the Services** 🛑
When you're done with running the API, stop the stack gracefully:
```bash:disable-run
docker compose down
```
- The Data you have tested with persists after a restart too thanks to **docker volumes**. To remove data :
```bash:disable-run
docker compose down --volumes
```
- **_Warning:_** `--volumes` deletes the Postgres and other services data volumes (irreversible removal of DB data).

---

<details>
<summary><b>⚠️ Tips & Troubleshooting</b></summary>

**If a service is acting suspicious or just ghosting you, check the logs to see what it’s complaining about:**

```bash:disable-run
# See what the API is screaming about
docker compose logs -f api

# Check if the DB is actually awake
docker compose logs db

# For the Celery/Redis issues
docker compose logs celery
docker compose logs redis
```

**Sometimes you need to go inside the container to see what's actually happening:**

- Get into the API container for debugging:
```bash:disable-run
docker compose exec -it api bash
```

**If you updated a dependency or changed a config and Docker is ignoring your changes:**
- Rebuild the images and restart the services:
```bash:disable-run
docker compose build
docker compose up -d
```

**To restart a single service (instead of the whole stack), you can target just one. For example, to restart the FastAPI API service:**

```bash:disable-run
docker compose restart api
```

- **PostgreSQL connection errors:** Confirm `.env` values and that `DATABASE_HOST=db` is set. Use `docker compose logs db` to inspect DB startup errors.
- **SMTP/email issues:** Confirm the app password is correct, and your Gmail account allows SMTP access via App Passwords (2-Step Verification must be enabled).
</details>

---

**You're all set!** 🎉 The Dockerized backend should be running and reachable at:
- 🔗 **API Docs:** `http://localhost:8000/docs`
- 🐰 **RabbitMQ:** `http://localhost:15672`
- 🪻  **Flower:**   `http://localhost:5555`