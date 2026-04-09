## Quick Start with Docker

### **📁 Cloning the Repository**
To get started, clone this repo and set up your environment.

- Clone the repository
```bash:disable-run
git clone https://github.com/Shankar-105/Social-Media-Api.git
```

- Change into the project directory
```bash:disable-run
cd Social-Media-Api
```

-  Rename the sample environment file to .env (this keeps secrets/config out of version control)
```bash:disable-run
mv .env.example .env
```
> Why: app reads configuration from `.env` so it must be `.env`. Also Renaming the `.env.example` to `.env` ensures sensitive keys (DB password,email creds,JWT secret) are loaded locally and not committed (via .gitignore) when you later commit/push your changes of this clone.

---
### Prepare Local Folders

```bash
mkdir profilepics posts_media chat-media
```

> These folders auto-store profile pictures, post media, and chat files locally. They'll be auto-created if missing.
---
### **⚙️ Docker Setup & Running the Project**
This project uses Docker Compose for an easy multi-service setup (API + Postgres). Containers isolate services and volumes persist your DB data while development.

#### Prerequisites
- Ensure Docker Desktop is installed and running.
  - Verify with:
```bash:disable-run
docker --version
```
  - Expected: a Docker version output (e.g., `Docker version 20.x.x` or newer).

#### Environment config (.env)
Open your `.env` and update only the values below that matter for container networking and email:

- EMAIL_USERNAME — set to your Gmail (e.g., your.email@gmail.com)  
- EMAIL_FROM — same Gmail address  
- EMAIL_PASSWORD — set to your Google App Password (NOT your regular Gmail password)
  - **Important:** App Passwords are 16-character codes you generate after enabling 2-Step Verification on your Google Account. They allow SMTP access for apps without sharing your main password.
  - If you’ve never created one, search for "How to Create App Password for Google Account | SMTP Configuration for Gmail Account" — a short tutorial/video will walk you through enabling 2FA and creating the app password step-by-step.

- Optional: tweak SECRET_KEY and other values for stronger security — defaults are fine for local development.

#### Why these env changes matter
- Using an App Password for email prevents exposing your main Google password and avoids blocking by Google.

---

### **Run (build -> start -> verify)**
Follow these commands to bring everything up:

1. Build images
```bash:disable-run
docker compose build
```

2. Start in detached mode (API + Postgres)
```bash:disable-run
docker compose up -d
```
- What happens: Compose starts the DB container first, then the API. If configured, Alembic migrations run automatically on startup.

3. Verify the API 
-  **In your Browser hit this url** http://localhost:8000/health

- **_you will seee {"message:"fine"}_**

4. View logs
```bash:disable-run
docker compose logs api
docker compose logs db
```

5. If your done with running the api Stop the stack gracefully
```bash:disable-run
docker compose down
```
- The Data you have tested with persists after a restart too thanks to **volumes**. To remove data :
```bash:disable-run
docker compose down --volumes
```
- **_Warning:_** `--volumes` deletes the Postgres data volume (irreversible removal of DB data).

---

<details>
<summary>⚠️ Advanced tips & troubleshooting</summary>

- Check running containers:
```bash:disable-run
docker compose ps
```
- Get into the API container for debugging:
```bash:disable-run
docker compose exec -it api bash
```
- If migrations don’t run automatically, run them manually inside the API container (**rare**):
```bash:disable-run
docker compose exec -it api alembic upgrade head
```
- If Postgres connection errors occur, confirm `.env` values and that `DATABASE_HOST=db` is set. Use `docker compose logs db` to inspect DB startup errors.
- If Redis connection errors occur, confirm `REDIS_HOST=redis` is set in the api environment. Use `docker compose logs redis` to inspect Redis startup errors.
- For SMTP/email issues: confirm the app password is correct, and your Gmail account allows SMTP access via App Passwords (2-Step Verification must be enabled).
</details>

You're all set — 🚀 your Dockerized backend should be running and reachable at http://localhost:8000/docs (**_if the containers are running_**).