# Comprehensive Testing Guide 🧪

Welcome to the **FastAPI Social Media API** testing documentation. This guide is designed to be your one-stop resource for understanding, running, and expanding the test suite of this project. Whether you want to run tests locally or inside a Dockerized environment this guide explains you both, **Get Started** :

---

## 📑 Table of Contents

- 🏗️ **[Architecture of Test Suite](#-architecture)**
- 🐳 **[Quick Start (Docker)](#-quick-start-with-docker)**
- 💻 **[Local Testing Environment](#-local-testing-without-docker)**
- 🗄️ **[Test Database Management](#️-test-database-management)**
- ⌨️ **[Pytest Command Reference](#-pytest-command-reference)**
- 📁 **[Detailed Project Test Structure](#-detailed-project-test-structure)**
- 🛠️ **[Fixture Hooks & Test Doubles](#️-fixture-hooks--test-doubles)**
- 📝 **[Adding or Updating Tests](#-adding-or-updating-tests)**
- 🤝 **[Contributor Notes](#-contributor-notes)**

## 🏗 Architecture

The testing strategy for this API focuses on **integration testing** using FastAPI's `TestClient` and a real PostgreSQL database.

- **Isolation**: Every test run uses a dedicated test database (`fastapi_test`) to ensure no side effects on your production or development data.
- **Repeatability**: Tests are designed to be idempotent. The database is cleared and rebuilt for every session.
- **Automation**: Tests are designed to run seamlessly in CI/CD pipelines or locally within Docker containers.
- **Performance**: While these are primarily functional tests, i kept an eye on execution time and performed many actions to decrease it.

---

## 🐳 Quick Start with Docker

Docker is the **recommended** way to run tests. It ensures that the environment (Python version, OS libraries, PostgreSQL version) is identical for every developer.

### **1. Spin Up the Infrastructure**
Ensure your containers are built and running in the background:
```bash
docker compose build
docker compose up -d
```

### **2. Run All Tests**
Execute the full suite with standard verbose output:
```bash
docker compose exec api pytest pytests/ -v -s -W ignore
```

### **3. Why Run in Docker?**
- **Zero Local Configuration**: You don't need Python or PostgreSQL installed on your host machine.
- **Smart Detection**: The test suite detects the `/.dockerenv` file and automatically switches the `DATABASE_HOST` to `db`.
- **Network Isolation**: Docker provides a clean bridge network where the API and DB communicate via service names.

---

## 💻 Local Testing (without Docker)

For developers who prefer a native workflow, follow these steps to set up a local testing environment.

### **1. Virtual Environment**
Create and activate a Python virtual environment to keep your system Python clean:
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### **2. Install Dependencies**
Install all required packages, including testing utilities:
```bash
pip install -r requirements.txt
```

### **3. Local PostgreSQL Requirement**
> [!IMPORTANT]
> **Local PostgreSQL running** on `localhost:5432` is mandatory for Option 2.
> Ensure you have a user with permission to create databases (usually the `postgres` user).
> The password should match what is defined in your `.env` file (`DATABASE_PASSWORD`).

### **4. Local Redis Requirement**
> [!IMPORTANT]
> **Local Redis running** on `localhost:6379` is mandatory for local tests.
> On WSL/Ubuntu: `sudo service redis-server start`
> On macOS (Homebrew): `brew services start redis`
> Confirm it's up with: `redis-cli ping` — should respond `PONG`.
> The `.env` defaults (`REDIS_HOST=localhost`, `REDIS_PORT=6379`, `REDIS_DB=0`) match automatically.

### **5. Environment Setup**
Ensure your `.env` file reflects the local setup:
- `DATABASE_HOST=localhost`
- `DATABASE_PORT=5432`
- `DATABASE_USER=postgres`

Run tests locally:
```bash
pytest pytests/ -v
```

---

## ⚙️ Test Database Management

The test suite handles database lifecycle automatically through `pytests/conftest.py`. This is one of the most robust parts of our system.

### **Automated Lifecycle**
1. **Detection**: The code checks the `pg_database` table to see if `fastapi_test` exists.
2. **Creation**: If missing, it connects to the `postgres` default DB (which always exists) and executes `CREATE DATABASE fastapi_test`.
3. **Synchronization**: Standardizes names to lowercase. This is crucial because PostgreSQL often treats mixed-case identifiers as lowercase unless double-quoted.
4. **Setup**: Drops all existing tables (`Base.metadata.drop_all`) and rebuilds them (`Base.metadata.create_all`) from SQLAlchemy models to ensure a clean slate.

---

## 🚀 Pytest Command Reference

Pytest is a powerful tool with many flags. Below is an expanded reference:

| Flag | Full Name | Description |
| :--- | :--- | :--- |
| `-v` | `--verbose` | Shows the name of each test and its result (PASSED/FAILED). |
| `-vv` | `--extra-verbose` | Even more detail, helpful for complex assertions. |
| `-s` | `--capture=no` | Allows print statements to appear in the terminal during execution. |
| `-x` | `--exitfirst` | Stops execution immediately after the first failure. |
| `--lf` | `--last-failed` | Runs only the tests that failed in the previous run. |
| `--ff` | `--failed-first` | Runs failed tests first, then runs the rest of the suite. |
| `-k` | `--expression` | Filter tests by name (e.g., `-k "login"` or `-k "not token"`). |
| `--tb` | `--traceback` | Controls traceback style (`auto`, `long`, `short`, `line`, `no`). |
| `-W` | `--pythonwarnings` | Controls warning display (e.g., `-W ignore`). |
| `--maxfail` | `N` | Stop after N failures total. |
| `--durations` | `N` | Show the N slowest test cases in your suite. |

### **Filtering Strategies**
```bash
# Run tests for a specific file
pytest pytests/test_auth.py -v

# Run tests that match a specific string anywhere in the path or function name
pytest pytests/ -v -k "schema"

# Run tests EXCEPT for those containing "security"
pytest pytests/ -v -k "not security"

# Stop on first failure and drop into debugger
pytest pytests/ -x --pdb
```

---

## 📁 Detailed Project Test Structure

The `pytests/` directory is logically partitioned:

- **`conftest.py`**: The "Global Hub." It defines the `TestClient`, overrides the database dependency, and contains the critical database creation logic.
- **`test_auth.py`**: Tests the registration, login (JWT issuance), and password change flows.
- **`test_posts.py`**: Exhaustive testing of post creation, deletion, and editing, including file upload simulations.
- **`test_comments.py`**: Validates create/delete operations for comments, ensuring strict ownership controls.
- **`test_votes.py`**: Ensures that "likes" and "dislikes" correctly increment/decrement counts and prevent double-voting.
- **`test_users.py`**: Tests the user directory, followers, and the ability to find others by username.
- **`test_me.py`**: Focuses on the "Session User" profile, statistics, and personal settings.
- **`test_chat.py`**: Uses custom WebSocket testing utilities to simulate real-time chat messages and history retrieval.
- **`test_schema_validation.py`**: Validates the **JSON structure** of responses. We use this to ensure my recent refactoring didn't break field names (camelCase vs snake_case).
- **`test_edge_cases.py`**: Covers things like very long strings, special characters, and unauthorized access attempts.
- **`test_celery_infrastructure.py`**: Lightweight checks for Celery queue configuration, Beat schedule, Flower-adjacent task controls, and DLQ wiring.

---

## 🛠️ Fixture Hooks & Test Doubles

The test suite now depends on a few important hooks in `pytests/conftest.py` rather than ad-hoc setup in individual tests.

- `client` is the main HTTP test entry point.
- `create_test_user` creates the shared session-scoped user fixture.
- `get_token` performs the login flow once and reuses the access token for the session.
- `setup_test_db` clears and rebuilds the database automatically.
- `app.services.rate_limit_service._check` is patched to a no-op during tests so repeated login, signup, and comment calls do not trip the real Redis-backed limits.
- `app.services.redis_service.redis_client` is replaced with `fakeredis.FakeAsyncRedis` so tests do not need a live Redis instance.
- `app.services.email_service` and `app.services.otp_service` are patched so signup and password-reset flows remain deterministic.
- `app.utils.thread_helpers` is patched in tests for fast, predictable password hashing and verification.

## 📝 Adding or Updating Tests

When adding a new test, keep it close to the behavior it validates and reuse the existing fixture model.

1. Add the test to the closest existing file in `pytests/`.
2. Reuse `client`, `get_token`, and `create_test_user` where possible.
3. If the test hits auth, rate-limiting, Redis, or email code, patch the corresponding service in `conftest.py` instead of mocking inside each test.
4. Keep assertions specific so failures point to the real regression.
5. Run the focused test file first, then the full suite.

Example:

```python
def test_new_endpoint(client, get_token):
    headers = {"Authorization": f"Bearer {get_token}"}
    resp = client.post("/new-endpoint", json={"data": "test"}, headers=headers)
    assert resp.status_code == 201
```

## 🤝 Contributor Notes

If you are updating tests after a refactor, check these first:

- `pytests/conftest.py` for shared mocks and the database bootstrap flow.
- `app/services/rate_limit_service.py` if a test suddenly starts failing with `429`.
- `app/utils/thread_helpers.py` if auth-related tests fail after password helper changes.
- `app/utils/socket_manager.py` if websocket delivery tests stop seeing messages.

For the latest deployment-side performance context, see [`BENCHMARK.md`](./BENCHMARK.md) and [`MONITORING_AND_LOAD_TESTING.md`](./MONITORING_AND_LOAD_TESTING.md).

**Thank you for visiting 🧪**
