# 🤝 Contributing to Repo

Welcome — contributions are open to everyone. Whether you're extending the backend or building a frontend on top of this API.

---

## 📑 Which one are you?

| I want to... | Go to |
|---|---|
| Add/fix backend features, routes, models | [Backend Contributor](#-backend-contributor) |
| Build a frontend (React, Vue, mobile, etc.) | [Frontend Contributor](#-frontend-contributor) |
| Submit a PR | [Submitting a PR](#-submitting-a-pr) |

---

## ⚙️ Backend Contributor

### 1. Get the project running locally

Follow [`SETUP.md`](./docs/SETUP.md) — the fastest way is Docker Compose (spins up API + PostgreSQL + Redis and all the other services in one command).


### 2. Adding a new feature — typical flow

> [!IMPORTANT]
> **API Versioning Rule**: Always use versioned prefixes (e.g., `/v1`). If you are making a **breaking change** to an existing endpoint, do not update the current version. Instead, create a new versioned router (e.g., `/v2`) to maintain backward compatibility for existing clients.

```
1. Add/update the model in app/models.py
2. Generate a migration: alembic revision --autogenerate -m "description"
3. Add request/response schemas in app/schemas.py
4. Write the route in app/routes/<your_file>.py (Ensure prefix="/v1/...")
5. Register the router in app/main.py
6. Write tests in pytests/ (Using versioned paths)
7. Run tests: docker compose exec api pytest pytests/ -v
```

Tests use a separate `fastapi_test` database — your dev data is never touched. See [`TESTS.md`](./docs/TESTS.md) for the full guide.

---

## 🎨 Frontend Contributor

### Base URL — local or live, your choice

The backend is **already deployed on Azure** — you don't need to run anything locally to start building.

| Option | Base URL |
|---|---|
| Live (Azure) | `https://fastapi-social-vm.centralindia.cloudapp.azure.com/docs`  |
| Local (Docker) | `http://localhost:8000` |

Both results the same response. So instead of `http://localhost:8000/v1/auth/login` you can just hit `https://fastapi-social-vm.centralindia.cloudapp.azure.com/v1/auth/login` — same endpoint, same response. Use whichever fits your workflow.

### Your API Reference

All endpoints are documented in [`API_GUIDE.md`](./docs/API_GUIDE.md) — every REST route and the WebSocket chat system with request/response examples.

> **Swagger UI** is live too use it as a reference if you would like too, click the link in Repo About.

---

## 🚀 Submitting a PR

1. Fork the repo, branch off `main` → `git checkout -b your-feature-name`
2. Make Sure all the tests pass before you push — broken tests won't be merged!

I'll review and comment directly on the PR. If it looks good, I'll merge it.

---

Questions? Open an issue or reach out via Gmail / LinkedIn (links on the profile).
