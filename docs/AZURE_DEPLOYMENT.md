# Azure Deployment Story

This is the story of how I took my FastAPI Social Media API from local development to a real Azure deployment. I kept it simple, practical, and close to how a real app would run in production. 🚀

## Live Deployment ☁️

The app is deployed on an Azure Linux virtual machine in Central India and is publicly reachable at:

- `https://fastapi-social-vm.centralindia.cloudapp.azure.com`

## BenchMark Proof 📷

Ran several tests against the deployed app and found infra bottlenecks and explained in clear what does that mean check that out here [`BENCHMARK.md`](./BENCHMARK.md)

## What I Set Up

### 1. Azure Linux VM

- Size: `Standard_B2ats_v2`
- OS: Ubuntu 22.04
- Purpose: runs the FastAPI application, Gunicorn/Uvicorn workers, and Nginx
- **Update 1:**
  - **OS Disk Changed** `StandardSSD_LRS` E4 (30 GB class, migrated from `Premium_LRS` P4 in 23rd Apr 2026)
- **Update 2:** 
  - **OS Disk Changed:** May 4, 2026 — Migrated from `StandardSSD_LRS` to `Standard_LRS` (HDD) — 30 GB for cost optimization

### 2. Azure Database for PostgreSQL

- Tier: Flexible Server, `B1ms`
- Purpose: stores users, posts, comments, messages, refresh tokens, notifications, and all core app data

### 3. Azure Blob Storage

- Containers used:
  - `profilepics`
  - `posts-media`
  - `chat-media`
- Purpose: stores uploaded profile images, post media, and chat media outside the VM filesystem

### 4. Redis on the same VM

- Redis runs on the same Ubuntu VM
- Purpose: caching, rate limiting, token blacklisting, and real-time notification delivery support

### 5. RabbitMQ + Celery on the same VM

- RabbitMQ runs on the same Ubuntu VM and acts as the Celery broker
- Celery worker runs as a separate systemd service and executes background jobs
- Celery Beat runs as a separate systemd service and keeps scheduled jobs alive
- Purpose: email tasks, notification jobs, and periodic cleanup must keep working after a code deploy without relying on the web process

## Deployment Stack ✅

- Nginx handles HTTPS termination and reverse proxying
- Gunicorn runs the FastAPI app with Uvicorn workers
- systemd keeps the app service alive and restarts it automatically
- systemd also keeps Redis, RabbitMQ, Celery worker, and Celery Beat alive on the VM
- GitHub Actions handles CI/CD and deploys the latest code to the VM after a successful pipeline run

## Why This Felt Like a Big Win

Seeing the app live on Azure felt like a real milestone for me as a student devloper. This setup keeps the project production-ready without depending on a laptop or temporary local files.

- Code runs on a real public server
- The database is managed separately from the app server
- Media uploads stay safe in Blob Storage instead of disappearing on restart
- HTTPS is enabled for secure browser access
- Deployments can be repeated without manual rebuild steps

## For Frontend Contributors ✨

If you want to build a frontend on top of this API, start with the endpoint reference in [`API_GUIDE.md`](./API_GUIDE.md). It covers the REST routes, authentication flow, media handling, and WebSocket chat behavior.