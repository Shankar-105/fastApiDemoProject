# Azure Deployment Story

This is the story of how I took my FastAPI Social Media API from local development to a real Azure deployment. I kept it simple, practical, and close to how a real app would run in production. 🚀

## Live Deployment ☁️

The app is deployed on an Azure Linux virtual machine in Central India and is publicly reachable at:

- `https://fastapi-social-vm.centralindia.cloudapp.azure.com`

## What I Set Up

### 1. Azure Linux VM

- VM name: `fastapi-social-vm`
- Size: `Standard_B2ats_v2`
- OS: Ubuntu 22.04
- OS disk: `StandardSSD_LRS` E4 (30 GB class, migrated from `Premium_LRS` P4 in 23rd Apr 2026)
- Purpose: runs the FastAPI application, Gunicorn/Uvicorn workers, and Nginx

### 2. Azure Database for PostgreSQL

- Server name: `fastapi-social-db`
- Tier: Flexible Server, `B1ms`
- Database name: `fastapi_db`
- Purpose: stores users, posts, comments, messages, refresh tokens, notifications, and all core app data

### 3. Azure Blob Storage

- Storage account: `fastsocialmedia`
- Containers used:
  - `profilepics`
  - `posts-media`
  - `chat-media`
- Purpose: stores uploaded profile images, post media, and chat media outside the VM filesystem

### 4. Redis on the VM

- Redis runs on the same Ubuntu VM
- Purpose: caching, rate limiting, token blacklisting, and real-time notification delivery support

## Deployment Stack ✅

- Nginx handles HTTPS termination and reverse proxying
- Gunicorn runs the FastAPI app with Uvicorn workers
- systemd keeps the app service alive and restarts it automatically
- GitHub Actions handles CI/CD and deploys the latest code to the VM after a successful pipeline run

## Why This Felt Like a Big Win

Seeing the app live on Azure felt like a real milestone for me as a student devloper. This setup keeps the project production-ready without depending on a laptop or temporary local files.

- Code runs on a real public server
- The database is managed separately from the app server
- Media uploads stay safe in Blob Storage instead of disappearing on restart
- HTTPS is enabled for secure browser access
- Deployments can be repeated without manual rebuild steps

## Why I Like This Setup

The backend is built to support real users, not just local testing. The Azure deployment gives the project a proper production environment with:

- a public URL
- managed database storage
- persistent file storage
- automated deployment
- a Linux server stack that is closer to real-world hosting

## For Frontend Contributors ✨

If you want to build a frontend on top of this API, start with the endpoint reference in [API_GUIDE.md](./API_GUIDE.md). It covers the REST routes, authentication flow, media handling, and WebSocket chat behavior.

## Re-Deployment Flow

When the backend changes, the deployment pipeline updates the VM by pulling the latest code, reinstalling dependencies if needed, running migrations, and restarting the service.

That means the VM always stays aligned with the code on the main branch, which makes the whole setup feel clean and reliable. ✅