# Azure Deployment Story

This is the story of how I took my FastAPI Social Media API from local development to a real Azure deployment. I kept it simple, practical, and close to how a real app would run in production. 🚀

## Live Deployment ☁️

The app is deployed on an Azure Linux virtual machine in Central India and is publicly reachable at:

- `https://fastapi-social-vm.centralindia.cloudapp.azure.com`

## BenchMark Proof 📷

Ran several tests against the deployed app and found infra bottlenecks and explained in clear what does that mean check that out here [`BENCHMARK.md`](./BENCHMARK.md)

## Modernized Architecture (Dockerized) 🐳

The production environment has been modernized from standalone systemd services to a **Docker Compose** managed stack. This ensures consistency between environments and simplifies service orchestration.

### 1. Azure Linux VM (The Host)
- Size: `Standard_B2ats_v2` (1GB RAM)
- OS: Ubuntu 22.04
- Purpose: Acts as the Docker host running our containerized application stack.

### 2. The Containerized Stack
The following services are orchestrated via `docker-compose.prod.yml`:
- **API**: FastAPI application running behind Gunicorn/Uvicorn.
- **Celery Worker & Beat**: Handles background tasks and scheduled jobs.
- **Redis**: Caching, rate limiting, and task result backend.
- **RabbitMQ**: Message broker for Celery.

### 3. Observability Update (Resource Management) ⚠️
Initially, a full **LGTM Stack** (Loki, Grafana, Tempo, Mimir/Prometheus) was deployed to provide advanced monitoring, logging, and tracing. 

**Current Status:** The LGTM stack is currently **Stopped/Disabled** in production.
- **Reason:** The `Standard_B2ats_v2` VM instance is highly resource-constrained with only 1GB of RAM. Running the full observability suite alongside the application stack pushed the system into frequent Out-Of-Memory (OOM) states.
- **Decision:** To prioritize application uptime and API responsiveness, observability has been scaled back to native `journald` logging. Tracing and metrics instrumentation are automatically bypassed in production mode to save memory.
- **Future:** If the infrastructure is upgraded to a tier with more RAM (e.g., 4GB+), the full observability stack can be re-enabled with a single configuration change.

## Managed Azure Services

### 1. Azure Database for PostgreSQL
- Tier: Flexible Server, `B1ms`
- Purpose: Persistent storage for users, posts, comments, messages, etc.

### 2. Azure Blob Storage
- Containers: `profilepics`, `posts-media`, `chat-media`
- Purpose: Scalable, durable storage for all user-generated media content.

## Deployment Stack ✅
- **Nginx (Host)**: Handles HTTPS (Certbot) and proxies traffic to the Dockerized API.
- **Docker Compose**: Manages the lifecycle of application services.
- **Journald**: Native system logging for container output.
- **GitHub Actions**: Automated CI/CD pipeline that builds and redeploys the Docker stack on every push to `main`.

## Why This Felt Like a Big Win
Moving to Docker while balancing resource constraints taught me the importance of **Infrastructure Right-Sizing**. The app is now portable, resilient, and optimized for the current Azure hardware limits.

- Code is isolated and consistent via containers.
- The system is protected against OOM crashes through strategic service selection.
- Deployments are seamless and handle container rebuilds automatically.

## For Frontend Contributors ✨
Start with the endpoint reference in [`API_GUIDE.md`](./API_GUIDE.md). Use the production URL for your base API endpoint.
