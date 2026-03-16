# 🚀 SocialMediaApi
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

## 🌟 Features — Everything Inside

_This API packs **a lot**. For the full breakdown of every feature — async architecture, auth, chat, caching, media, DevOps, and more — see [`FEATURES.md`](./FEATURES.md)._

---

## 🚦 Getting Started — Simplified with Docker!

_Want to Run the Api or wanna test or make your own changes to the code here's [`SET-UP`](https://github.com/Shankar-105/Social-Media-Api/blob/main/SETUP.md) how you can 
clone the repositroy and set up the environment._

---

## 📖 How to Use the API — Complete Endpoint Reference

_Now that your setup is running, explore every endpoint this API has to offer! Check out [`API_GUIDE.md`](./API_GUIDE.md) for a detailed walkthrough of all **55 REST endpoints** and the **real-time WebSocket chat system**._

> 💡 **Quick Start:** Visit `http://localhost:8000/docs` for the built-in Swagger UI — test endpoints right from your browser!

---

## 🧪 Testing — Comprehensive Test Suite!

_Ready to verify everything works? Check out [`TESTS.md`](./TESTS.md) for a complete guide on running the test suite._

**Quick Test Run:**
- 🐳 **Inside Docker** (Recommended): `docker compose exec api pytest pytests/ -v`
- 💻 **Locally**: Install dependencies and run `pytest pytests/ -v`

_All tests use a separate test database—your dev data stays safe! 🛡️_

---

## 🤝 Contributing

_Backend developer? Frontend developer? Either, there's a clear path for you. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for role-specific setup guides, code conventions, and PR instructions._

---

## 👨‍💻 Built by Bhavani Shankar  
**ANITS College, Vizag**

> Thanks for checking out the project.
> If you use this API , let me know—would love to hear you 🚀 🎓
---