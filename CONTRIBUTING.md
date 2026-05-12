# 🤝 Contributing to Repo

Welcome — contributions are open to everyone. Whether you're extending the backend or building a frontend on top of this API.

***

## 📑 Which one are you?

| I want to...                                | Go to                                            |
| ------------------------------------------- | ------------------------------------------------ |
| Add/fix backend features, routes, models    | [`Backend Contributor`](#-backend-contributor)   |
| Build a frontend (React, Vue, mobile, etc.) | [`Frontend Contributor`](#-frontend-contributor) |
| Submit a PR                                 | [`Submitting a PR`](#-submitting-a-pr)           |

***

## ⚙️ Backend Contributor

### 1. Get the project running locally

Follow [`SETUP.md`](./docs/SETUP.md) — the fastest way is Docker Compose (spins up API + PostgreSQL + Redis and all the other services in one command).

### 2. Adding a new feature — typical flow

This is optional all i need is a feature that makes sense and the ci check to pass, but a good practice to follow :

```
1. Add/update the model in app/models.py
2. Generate a migration: alembic revision --autogenerate -m "description"
3. Add request/response schemas in app/schemas.py
4. Write the route logic in app/routes/<filename_v2>.py
5. Register the router in the version aggregator (e.g., app/api/v2/api_router.py)
6. Write tests in pytests/ (Using versioned paths like /v2/...)
7. Run tests: docker compose exec api pytest pytests/ -v
```

### 🚦 API Versioning & Breaking Changes

The API uses **Router Composition** to manage versions. Do **not** hardcode `/v1 or /v2` in individual route files.

### How to add a NEW version (e.g., v2)

Suppose you want to make a breaking change to the GET /users/me endpoint. Here is how you do it without breaking the old version:

Step 1: Create the new logic You can create a new file app/routes/me\_v2.py OR just add a second router instance in the same file:

```bash:disable-run

# In app/routes/me.py
router_v2 = APIRouter(prefix="/users/me", tags=["Current User V2"])

@router_v2.get("/")
async def get_my_profile_v2():
    return {"message": "This is the NEW V2 response format!"}
```

Step 2: Create a V2 Aggregator Create app/api/v2/api\_router.py :

```bash:disable-run

from fastapi import APIRouter
from app.routes import me, posts # Reuse v1 posts if they haven't changed!

api_v2_router = APIRouter()
api_v2_router.include_router(me.router_v2) # Use the NEW V2 logic
api_v2_router.include_router(posts.router)    # Reuse the OLD V1 logic
```

Step 3: Mount it in main.py

```bash:disable-run

# app/main.py
from app.api.v1.api_router import api_v1_router
from app.api.v2.api_router import api_v2_router

app.include_router(api_v1_router, prefix="/v1")
app.include_router(api_v2_router, prefix="/v2")
```

This allows us to support multiple versions (v1, v2, v3) concurrently while reusing non-breaking code.

Tests use a separate `fastapi_test` database — your dev data is never touched. See [`TESTS.md`](./docs/TESTS.md) for the full guide.

***

## 🎨 Frontend Contributor

### Base URL — local or live, your choice

The backend is **already deployed on Azure** — you don't need to run anything locally to start building.

| Option         | Base URL                                                         |
| -------------- | ---------------------------------------------------------------- |
| Live (Azure)   | `https://fastapi-social-vm.centralindia.cloudapp.azure.com/docs` |
| Local (Docker) | `http://localhost:8000`                                          |

Both results the same response. So instead of `http://localhost:8000/v1/auth/login` you can just hit `https://fastapi-social-vm.centralindia.cloudapp.azure.com/v1/auth/login` — same endpoint, same response. Use whichever fits your workflow.

### Your API Reference

All endpoints are documented in [`API_GUIDE.md`](./docs/API_GUIDE.md) — every REST route and the WebSocket chat system with request/response examples.

> **Swagger UI** is live too use it as a reference if you would like too, click the link in Repo About.

***

## 🚀 Submitting a PR

1. Fork the repo, branch off `main` → `git checkout -b your-feature-name`
2. Make Sure all the tests pass before you push — broken tests won't be merged!

I'll review and comment directly on the PR. If it looks good, I'll merge it.

***

Questions? Open an issue or reach out via Gmail / LinkedIn (links on the profile).
