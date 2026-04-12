# 🚀 Social Media Api
**Modern Social Media Backend + Real-time Chat – Scalable, Fast, and Beginner-Friendly**

A **fully async, non-blocking** social media backend built to handle **thousands of concurrent connections** without breaking a sweat. Powered by FastAPI, asyncpg, Redis, and WebSockets — every route, every query, every cache hit runs on the event loop. Features **refresh token rotation** with family-based revocation, **real-time notifications** via Redis Pub/Sub, **IP & user-based rate limiting**, **Redis caching across 11+ endpoints** with automatic invalidation. CPU-heavy work (bcrypt, JWT) is offloaded to the thread pool so the server never stalls. Production-grade, real-time, and built for scale.

---

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.119+-green?logo=fastapi)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-yellow?logo=sqlalchemy)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue?logo=postgresql)
![WebSockets Badge](https://img.shields.io/badge/WebSockets-101010?style=for-the-badge&logo=socket.io&logoColor=white)
![JWT Badge](https://img.shields.io/badge/JWT-000000?style=for-the-badge&logo=JSON%20web%20tokens&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=plastic&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0+-red?logo=redis&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-Dashboarding-F46800?logo=grafana&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?logo=prometheus&logoColor=white)
![k6](https://img.shields.io/badge/k6-Load%20Testing-7D64FF?logo=k6&logoColor=white)

## 🌟 Features — Everything Inside

_This API packs **a lot**. For the full breakdown of every feature — async architecture, auth, chat, caching, media, DevOps, and more — see [`docs/FEATURES.md`](./docs/FEATURES.md)._ 

---

## 🚦 Getting Started — Simplified with Docker!

_Want to run the API, test it, or make your own changes? Start with [`docs/SETUP.md`](./docs/SETUP.md) to clone the repository and set up the environment._

---

## 📖 How to Use the API — Complete Endpoint Reference

_Now that your setup is running, explore every endpoint this API has to offer! Check out [`docs/API_GUIDE.md`](./docs/API_GUIDE.md) for a detailed walkthrough of all **61 REST endpoints** and the **real-time WebSocket chat system**._

> 💡 **Quick Start:** Visit `http://localhost:8000/docs` for the built-in Swagger UI — test endpoints right from your browser!

---

## ☁️ Azure Deployment — How the app is hosted

_Want to know how this project runs in the cloud? Read [`docs/AZURE_DEPLOYMENT.md`](./docs/AZURE_DEPLOYMENT.md) for the Azure VM, PostgreSQL, Blob Storage, Redis, and CI/CD setup behind the live deployment._

---

## 🧪 Testing — Comprehensive Test Suite!

_Ready to verify everything works? Check out [`docs/TESTS.md`](./docs/TESTS.md) for a complete guide on running the test suite._

**Quick Test Run:**
- 🐳 **Inside Docker** (Recommended): `docker compose exec api pytest pytests/ -v`
- 💻 **Locally**: Install dependencies and run `pytest pytests/ -v`

_All tests use a separate test database—your dev data stays safe! 🛡️_

---
## 📸 Benchmark Proof — RPS, P95 Graphs and What They Mean

_[`docs/BENCHMARK.md`](./docs/BENCHMARK.md)_

> Real benchmark evidence from deployed runs, with charts + clear conclusions.

**What you get inside:**
- 📈 _**smoke/load** behavior snapshots from **Grafana**_,
- ⏱️ _request rate, p95 latency, and top slow-endpoint patterns_,
- 🧠 _interpretation of whether limits are coming from **infrastructure saturation or endpoint-level defects**_.

--- 

## 📊 Monitoring and Load Testing

_Want to observe real-time performance and run synthetic traffic on API? Start with [`docs/MONITORING_AND_LOAD_TESTING.md`](./docs/MONITORING_AND_LOAD_TESTING.md) for Prometheus, Grafana, OpenTelemetry, and k6 setup._

---

## 🤝 Contributing

_Backend developer? Frontend developer? Either, there's a clear path for you. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for role-specific setup guides, code conventions, and PR instructions._

---

## 👨‍💻 Built by Bhavani Shankar Mukka 🎓
**ANITS College, Vizag**

> Thanks for checking out the project.
> If you use this API , let me know—would love to hear you ❤️
---