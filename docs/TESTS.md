# Comprehensive Testing Guide 🧪

Welcome to the **FastAPI Social Media API** testing documentation. This guide is designed to be your one-stop resource for understanding, running, and expanding the test suite of this project. Whether you are running tests locally or inside a Dockerized environment, this document covers everything from basic commands to advanced debugging techniques.

---

## 📑 Table of Contents
- 🏗️ **Architecture & Philosophy**
- 🐳 **Quick Start (Docker)**
- 💻 **Local Testing Environment**
- 🗄️ **Test Database Management**
- ⌨️ **Pytest Command Reference**
- 📁 **Detailed Project Test Structure**
- 🛠️ **Fixtures & conftest.py**
- 🧪 **Advanced Test Scenarios**
- 🛡️ **Security & Stress Testing**
- 🔍 **Debugging & Troubleshooting**
- 📊 **Coverage & Quality Reports**
- 🎨 **Frontend Development**
- 🤝 **Best Practices for Contributors**
- 📝 **Step-by-Step: Adding a New Test**
- 📖 **Glossary of Terms**

## 🏗 Architecture & Philosophy

The testing strategy for this API focuses on **integration testing** using FastAPI's `TestClient` and a real PostgreSQL database. We believe in:

- **Isolation**: Every test run uses a dedicated test database (`fastapi_test`) to ensure no side effects on your production or development data.
- **Repeatability**: Tests are designed to be idempotent. The database is cleared and rebuilt for every session.
- **Automation**: Tests are designed to run seamlessly in CI/CD pipelines or locally within Docker containers.
- **Coverage**: Validating not just the "happy path" but also edge cases, validation errors, and security constraints.
- **Performance**: While these are primarily functional tests, we keep an eye on execution time to ensure a tight feedback loop.

---

## 🐳 Quick Start (Docker)

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
- **Consistency**: "It works on my machine" becomes "It works in our container."
- **Network Isolation**: Docker provides a clean bridge network where the API and DB communicate via service names.

---

## 💻 Local Testing Environment

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

### **Manual Reset**
If you suspect the database state is corrupt or data is "stuck":
```bash
# Docker method
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS fastapi_test;"

# Local method (Linux/macOS)
dropdb fastapi_test

# Local method (Windows psql)
psql -U postgres -c "DROP DATABASE fastapi_test;"
```

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

---

## 🧱 Fixtures & conftest.py

Fixtures are the building blocks of our tests. They provide clean, reusable data.

### **Essential Fixtures**
1. **`client`**: 
   - Type: `fastapi.testclient.TestClient`
   - Purpose: Makes HTTP requests to your app without starting a real server.
   - Usage: `response = client.get("/posts")`

2. **`create_test_user`**:
   - Purpose: Ensures a user exists for testing purposes.
   - Scoped: `session`, so it's created once per test run.

3. **`get_token`**:
   - Purpose: Provides a valid JWT token.
   - Usage:
     ```python
     def test_private_post(client, get_token):
         headers = {"Authorization": f"Bearer {get_token}"}
         client.post("/posts/", json=data, headers=headers)
     ```

4. **`setup_test_db`**:
   - Purpose: The "Magic Wand." It runs automatically (`autouse=True`) to clear and rebuild the database.

---

## 🏗 Advanced Test Scenarios

### **Testing WebSockets**
WebSockets are tested by bridging the `async` nature of connections with pytest's execution.
```python
def test_websocket_flow(client, get_token):
    with client.websocket_connect(f"/chat/ws?token={get_token}") as websocket:
        websocket.send_json({"to": 2, "content": "Hello!"})
        data = websocket.receive_json()
        assert data["content"] == "Hello!"
```

### **Testing File Uploads**
We simulate multi-part form data uploads for profile pictures and post media:
```python
def test_image_upload(client, get_token):
    file_data = {"file": ("test.png", b"fake-image-content", "image/png")}
    headers = {"Authorization": f"Bearer {get_token}"}
    resp = client.post("/user/profile/picture", files=file_data, headers=headers)
    assert resp.status_code == 200
```

---

## 🔐 Security & Stress Testing

1. **Authorization Checks**: Every endpoint that requires `get_current_user` is tested with and without a valid token.
2. **Ownership Validation**: Tests in `test_posts.py` and `test_comments.py` verify that User A cannot delete User B's content.
3. **Pydantic Validation**: By strictly enforcing schemas, we prevent "Mass Assignment" vulnerabilities.
4. **SQL Injection**: Since we use SQLAlchemy's ORM and parameterized queries, we are protected against standard SQL injection.

---

## 🐛 Debugging & Troubleshooting

### **The "Database already exists" Loop**
If you see `psycopg2.errors.DuplicateDatabase` even with the fix, it usually means two things:
1. Two test runs are trying to create it at the same time (Race Condition).
2. The check logic is failing due to casing.
**Fixed in conftest.py:** We now catch the `ProgrammingError` and verify if the message says "already exists".

### **Common Troubleshooting Steps**

| Symptom | Diagnosis | Fix |
| :--- | :--- | :--- |
| `pydantic.ValidationError` | Request/Response doesn't match schema. | Check for missing fields or type mismatches. |
| `ConnectionRefusedError` | DB is not reachable on the host/port. | Validate `.env` and Docker container status. |
| `module 'app' not found` | Python can't see the project root. | Run from root or set `PYTHONPATH=.`. |
| `AssertionError: 401 == 200` | Token is invalid or expired. | Refresh the `get_token` fixture. |

---

## 📊 Coverage & Quality Reports

Understanding what code is **NOT** tested is more important than knowing what is.

### **Terminal Coverage**
```bash
# Inside container
docker compose exec api pytest pytests/ --cov=app --cov-report=term-missing
```

### **Interactive HTML Report**
```bash
# Generate HTML
docker compose exec api pytest pytests/ --cov=app --cov-report=html
```
This creates an `htmlcov/` directory.

---

## 🌐 Frontend Dev Quick-Guide

If you are a frontend developer working with this API:
- **Run the API**: `docker compose up -d`.
- **Verify your changes**: Before you push frontend code, run `docker compose exec api pytest pytests/`.
- **Contract Verification**: If you change a field name in the frontend, check `test_schema_validation.py`.

---

## 🎯 Best Practices for Contributors

Please follow these conventions:

1. **Keep it atomic**: Each test should verify exactly one piece of logic.
2. **Use descriptive names**: Rename `test_user_1` to `test_user_registration_fails_with_duplicate_username`.
3. **Assert specifically**: Instead of `assert resp.status_code != 200`, use `assert resp.status_code == 400`.
4. **Mock external APIs**: If you add an email service, don't send real messages.
5. **Clean up media**: If your test uploads files, ensure they are handled in `.gitignore`.
6. **Independence**: Tests should not depend on the order of execution.

---

## 📝 Step-by-Step: Adding a New Test

Want to contribute a new test? Follow these steps:

1. **Create/Open a file**: Choose an existing file in `pytests/` or create `pytests/test_new_feature.py`.
2. **Import Fixtures**: You don't need to import fixtures explicitly; pytest finds them in `conftest.py`.
3. **Write the function**:
   ```python
   def test_new_endpoint(client, get_token):
       # 1. Arrange
       payload = {"data": "test"}
       # 2. Act
       headers = {"Authorization": f"Bearer {get_token}"}
       resp = client.post("/new-endpoint", json=payload, headers=headers)
       # 3. Assert
       assert resp.status_code == 201
       assert resp.json()["status"] == "success"
   ```
4. **Run the specific test**:
   ```bash
   pytest pytests/test_new_feature.py::test_new_endpoint -v
   ```

---

## 📚 Glossary of Terms

- **`conftest.py`**: A special pytest file used for sharing fixtures and configuration.
- **Fixture**: A function that provides data or setup for a test.
- **TestClient**: A utility that allows you to make "fake" requests to your API.
- **Integration Test**: A test that verifies how multiple parts work together.
- **Idempotent**: An operation that can be run multiple times without changing the result.
- **Mocking**: The process of replacing a real component with a "fake" one.
- **Coverage**: Metric expressing what percentage of source code has been executed.

---

## **Need Help?**

If you encounter a bug or have questions about the tests:
- Open an Issue on the repository.
- 🐛 Review test output carefully for error details.
- 📋 Check existing tests in `pytests/` for examples
- 📚 Read [official pytest docs](https://docs.pytest.org/)
- Read the official [FastAPI Testing Documentation](https://fastapi.tiangolo.com/advanced/testing-database/).

---

**Thank you 🧪🚀**
